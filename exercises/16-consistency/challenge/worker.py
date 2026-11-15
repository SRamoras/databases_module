"""Task 2: apply the outbox to Redis.

Loop: in one PostgreSQL transaction,
  1. claim up to 50 unprocessed rows with FOR UPDATE SKIP LOCKED;
  2. SADD the categories of each row's film to customer:{customer_id}:categories;
  3. set processed_at on those rows and COMMIT.

Redis is written BEFORE the commit. If the worker dies after writing Redis and
before the commit, the rows stay unprocessed and are applied again: harmless,
because SADD of a member that is already there changes nothing. The opposite
order (commit, then Redis) could mark rows as done that never reached Redis.

If Redis fails, the transaction is rolled back (the rows go back to the queue)
and the worker waits until Redis is back AND persists every write to disk
(appendonly yes, appendfsync always) before it writes again.

    uv run python worker.py                 # REDIS_URL must end in /1
    WORKER_DELAY=0.01 uv run python worker.py   # seconds per row, to make batches slow
"""

import os
import time
from datetime import datetime

import psycopg
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

BATCH = 50
DELAY = float(os.environ.get("WORKER_DELAY", "0.01"))
NAME = f"worker pid {os.getpid()}"

CLAIM = """
SELECT o.outbox_id, o.customer_id, o.film_id,
       coalesce((SELECT array_agg(c.name ORDER BY c.name)
                 FROM film_category fc JOIN category c ON c.category_id = fc.category_id
                 WHERE fc.film_id = o.film_id), '{}') AS categories
FROM outbox o
WHERE o.processed_at IS NULL
ORDER BY o.outbox_id
LIMIT %s
FOR UPDATE OF o SKIP LOCKED
"""

# no automatic retries: when Redis dies, the command must fail now
r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True, retry=Retry(NoBackoff(), 0))


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f" [{NAME}] {message}", flush=True)


def wait_for_durable_redis() -> None:
    """Block until Redis answers and is configured to fsync every write."""
    waiting_since = None
    while True:
        try:
            config = r.config_get("appendonly") | r.config_get("appendfsync")
            if config["appendonly"] == "yes" and config["appendfsync"] == "always":
                if waiting_since is not None:
                    log(f"redis is back with appendonly yes, appendfsync always "
                        f"(waited {time.perf_counter() - waiting_since:.1f}s)")
                return
            reason = f"appendonly {config['appendonly']}, appendfsync {config['appendfsync']}"
        except redis.RedisError as e:
            reason = f"{type(e).__name__}"
        if waiting_since is None:
            waiting_since = time.perf_counter()
            log(f"waiting for redis ({reason})")
        time.sleep(0.5)


def process_batch(pg: psycopg.Connection) -> int:
    with pg.transaction():
        rows = pg.execute(CLAIM, (BATCH,)).fetchall()
        if not rows:
            return 0
        first, last = rows[0][0], rows[-1][0]
        log(f"claimed {len(rows)} rows, outbox_id {first}..{last}")
        for i, (outbox_id, customer_id, film_id, categories) in enumerate(rows, 1):
            if categories:
                r.sadd(f"customer:{customer_id}:categories", *categories)
            if i == len(rows) // 2:
                log(f"  redis: {i} of {len(rows)} rows written (outbox_id up to {outbox_id})")
            time.sleep(DELAY)
        pg.execute(
            "UPDATE outbox SET processed_at = now() WHERE outbox_id = ANY(%s)",
            ([row[0] for row in rows],),
        )
    log(f"committed outbox_id {first}..{last}")
    return len(rows)


def main() -> None:
    log(f"started (batch {BATCH}, {DELAY}s per row)")
    wait_for_durable_redis()
    idle = False
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as pg:
        while True:
            try:
                n = process_batch(pg)
            except redis.RedisError as e:
                # the with pg.transaction() block rolled back: the rows are unprocessed again
                log(f"redis error ({type(e).__name__}): batch rolled back, rows go back to the queue")
                wait_for_durable_redis()
                continue
            if n == 0:
                if not idle:
                    log("nothing to do, waiting")
                idle = True
                time.sleep(0.5)
            else:
                idle = False


if __name__ == "__main__":
    main()

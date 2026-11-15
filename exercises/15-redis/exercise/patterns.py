"""Four Redis patterns on Pagila data.

Keys (see the table in the README):
    customer:{customer_id}:viewed        sorted set   recently viewed films
    cache:film:{film_id}                 string/JSON  film cache (cache-aside)
    lock:refresh:monthly_revenue         string       lock with expiry (refresh.py)
    ratelimit:{customer_id}:{minute}     string/int   requests of one customer in one minute
"""

import json
import os
import time
from collections import Counter
from decimal import Decimal

import psycopg
import redis

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

VIEWED_MAX = 20
VIEWED_TTL = 30 * 24 * 3600  # 30 days, in seconds
FILM_CACHE_TTL = 300
RATE_LIMIT = 10
RATE_WINDOW = 60

# how many get_film calls were served from Redis and how many from PostgreSQL
cache_stats: Counter = Counter()


def pg() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


# ---------- 1. recently viewed films ----------


def viewed_key(customer_id: int) -> str:
    return f"customer:{customer_id}:viewed"


def record_view(customer_id: int, film_id: int, now: float | None = None) -> None:
    """Add (or move to the front) a film, keep the 20 most recent, expire 30 days after this view."""
    key = viewed_key(customer_id)
    pipe = r.pipeline(transaction=True)  # MULTI/EXEC: the three commands run together
    pipe.zadd(key, {film_id: now if now is not None else time.time()})
    pipe.zremrangebyrank(key, 0, -(VIEWED_MAX + 1))  # remove all but the 20 highest scores
    pipe.expire(key, VIEWED_TTL)
    pipe.execute()


def recent_views(customer_id: int) -> list[int]:
    """Film IDs, most recent first."""
    return [int(f) for f in r.zrange(viewed_key(customer_id), 0, -1, desc=True)]


# ---------- 2. cache-aside ----------


def film_key(film_id: int) -> str:
    return f"cache:film:{film_id}"


def get_film(film_id: int) -> dict | None:
    key = film_key(film_id)
    cached = r.get(key)
    if cached is not None:
        cache_stats["hit"] += 1
        return json.loads(cached)

    cache_stats["miss"] += 1
    with pg() as conn:
        row = conn.execute(
            "SELECT title, rating::text, length, rental_rate FROM film WHERE film_id = %s",
            (film_id,),
        ).fetchone()
    if row is None:
        return None
    title, rating, length, rate = row
    # money as a string, so 0.99 never becomes 0.9899999...
    data = {"title": title, "rating": rating, "length": length, "rental_rate": str(rate)}
    r.set(key, json.dumps(data), ex=FILM_CACHE_TTL)
    return data


def update_film_rate(film_id: int, rate: Decimal | str | float) -> None:
    """Update the source of truth first, then delete the cache key (never the other way round)."""
    with pg() as conn:
        conn.execute("UPDATE film SET rental_rate = %s WHERE film_id = %s", (Decimal(str(rate)), film_id))
    # the transaction is committed when the with block ends; only then is the cache dropped
    r.delete(film_key(film_id))


# ---------- 3. lock with expiry (used by refresh.py) ----------

# Deletes the lock only if it still holds our token. GET and DEL run inside Redis as
# one atomic step, so nobody can take the lock between the check and the delete.
release_lock = r.register_script("""
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
""")


def acquire_lock(name: str, token: str, seconds: int = 60) -> bool:
    return bool(r.set(f"lock:{name}", token, nx=True, ex=seconds))


def unlock(name: str, token: str) -> bool:
    return release_lock(keys=[f"lock:{name}"], args=[token]) == 1


# ---------- 4. rate limit (fixed window of one minute) ----------


def allow_request(customer_id: int, now: float | None = None) -> bool:
    minute = int((now if now is not None else time.time()) // RATE_WINDOW)
    key = f"ratelimit:{customer_id}:{minute}"
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, RATE_WINDOW, nx=True)  # set once, when the counter is created
    count, _ = pipe.execute()
    return count <= RATE_LIMIT

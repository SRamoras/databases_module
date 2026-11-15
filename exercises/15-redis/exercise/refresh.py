"""Task 3: refresh monthly_revenue under a Redis lock.

Start two at the same time; one refreshes, the other skips:

    uv run python refresh.py & uv run python refresh.py & wait
"""

import os
import time
import uuid
from datetime import datetime

from patterns import acquire_lock, pg, r, unlock

LOCK = "refresh:monthly_revenue"
NAME = f"pid {os.getpid()}"


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f" [{NAME}] {message}", flush=True)


def main() -> None:
    token = str(uuid.uuid4())
    if not acquire_lock(LOCK, token, seconds=60):
        holder = r.get(f"lock:{LOCK}")
        log(f"skipped: lock:{LOCK} is held by token {holder[:8]}..., TTL {r.ttl(f'lock:{LOCK}')}s")
        return

    log(f"acquired lock:{LOCK} with token {token[:8]}...")
    try:
        started = time.perf_counter()
        with pg() as conn:
            conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_revenue")
        log(f"refreshed monthly_revenue in {time.perf_counter() - started:.2f}s")
        log("holding the lock for 5 more seconds")
        time.sleep(5)
    finally:
        released = unlock(LOCK, token)
        log(f"released the lock: {released}")


if __name__ == "__main__":
    main()

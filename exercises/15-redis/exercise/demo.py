"""Demonstrations of tasks 1, 2 and 4, plus the lock release rule of task 3.

    uv run python demo.py
"""

import time
import uuid

from patterns import (
    acquire_lock,
    allow_request,
    cache_stats,
    film_key,
    get_film,
    pg,
    r,
    record_view,
    recent_views,
    unlock,
    update_film_rate,
    viewed_key,
)


def title(text: str) -> None:
    print(f"\n=== {text}")


def demo_recently_viewed() -> None:
    title("1. Recently viewed films")
    r.delete(viewed_key(1))
    for film_id in range(1, 26):
        record_view(1, film_id)
        time.sleep(0.002)  # distinct timestamps, so the order is the order of the views
    print("customer 1 viewed films 1 to 25")
    print(f"recent_views(1) = {recent_views(1)}")
    print(f"ZCARD {viewed_key(1)} = {r.zcard(viewed_key(1))}")

    record_view(1, 10)
    views = recent_views(1)
    print("customer 1 viewed film 10 again")
    print(f"recent_views(1) = {views}")
    print(f"film 10 appears {views.count(10)} time(s); ZCARD = {r.zcard(viewed_key(1))}")
    print(f"TTL {viewed_key(1)} = {r.ttl(viewed_key(1))} seconds (30 days = 2592000)")


def demo_cache_aside() -> None:
    title("2. Cache-aside for film 1")
    r.delete(film_key(1))
    with pg() as conn:  # start from the original rate, so the demo can be repeated
        conn.execute("UPDATE film SET rental_rate = 0.99 WHERE film_id = 1")

    def get(label: str) -> None:
        before = cache_stats.copy()
        film = get_film(1)
        result = "hit " if cache_stats["hit"] > before["hit"] else "miss"
        print(f"{label}: {result} -> {film}  (TTL {r.ttl(film_key(1))}s)")

    get("get_film(1), first ")
    get("get_film(1), second")
    update_film_rate(1, "1.99")
    print(f"update_film_rate(1, 1.99): PostgreSQL updated, EXISTS {film_key(1)} = {r.exists(film_key(1))}")
    get("get_film(1), third ")
    get("get_film(1), fourth")


def demo_lock_release() -> None:
    title("3. The lock is never released by a process that does not hold it")
    name = "demo"
    r.delete(f"lock:{name}")
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    print(f"A acquires lock:{name}: {acquire_lock(name, a, seconds=1)}")
    print(f"B acquires lock:{name}: {acquire_lock(name, b, seconds=1)}  (A holds it)")
    time.sleep(1.1)
    print("... A is slow; its lock expires after 1 second")
    print(f"B acquires lock:{name}: {acquire_lock(name, b, seconds=60)}")
    print(f"A releases with its old token: {unlock(name, a)}  (lock still held by B: {r.get(f'lock:{name}') == b})")
    print(f"B releases with its token:     {unlock(name, b)}  (EXISTS lock:{name} = {r.exists(f'lock:{name}')})")


def demo_rate_limit() -> None:
    title("4. Rate limit: 10 requests per customer per minute")
    # start at the beginning of a minute, so the 12 calls fall in the same window
    wait = 60 - time.time() % 60
    if wait < 55:
        print(f"(waiting {wait:.0f}s for a new minute to start)")
        time.sleep(wait + 0.2)
    minute = int(time.time() // 60)
    for key in r.scan_iter("ratelimit:1:*"):
        r.delete(key)

    results = [allow_request(1) for _ in range(12)]
    print(f"12 calls for customer 1 in minute {minute}: {results}")
    print(f"True: {results.count(True)}, False: {results.count(False)}")
    key = f"ratelimit:1:{minute}"
    print(f"GET {key} = {r.get(key)}, TTL {r.ttl(key)}s")

    wait = 60 - time.time() % 60
    print(f"(waiting {wait:.0f}s for the next minute)")
    time.sleep(wait + 0.2)
    print(f"call in minute {int(time.time() // 60)}: {allow_request(1)}")
    print(f"GET ratelimit:1:{int(time.time() // 60)} = {r.get(f'ratelimit:1:{int(time.time() // 60)}')}")


if __name__ == "__main__":
    demo_recently_viewed()
    demo_cache_aside()
    demo_lock_release()
    demo_rate_limit()

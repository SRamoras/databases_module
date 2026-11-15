"""Task 1: rebuild every customer:{customer_id}:categories set from PostgreSQL.

One query (categories.EXPECTED_SQL) and one pipeline. Each set is built in a
temporary key and renamed over the real one, so a reader sees either the old set
or the new one, never a half-built one. Sets of customers who should not have
one (no rentals) are deleted in the same pipeline.

    uv run python rebuild.py
"""

import time

from categories import KEY_PATTERN, connect_redis, customer_of, expected, key


def main() -> None:
    started = time.perf_counter()
    r = connect_redis()
    sets = expected()  # the only query

    stale = [k for k in r.scan_iter(match=KEY_PATTERN, count=1000)
             if customer_of(k) not in sets]

    # transaction=False: one round trip, but not one MULTI/EXEC. Atomicity per set
    # comes from RENAME, which replaces the old set in one step.
    pipe = r.pipeline(transaction=False)
    for customer_id, names in sets.items():
        tmp = key(customer_id) + ":rebuild"
        pipe.delete(tmp)
        pipe.sadd(tmp, *sorted(names))
        pipe.rename(tmp, key(customer_id))
    for k in stale:
        pipe.delete(k)
    commands = len(pipe)
    pipe.execute()

    print(f"rebuilt {len(sets)} sets, deleted {len(stale)} stale set(s), "
          f"1 query, 1 pipeline of {commands} commands, {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()

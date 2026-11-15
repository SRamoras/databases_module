"""Task 3: compare every customer:{customer_id}:categories set with PostgreSQL.

Prints every difference and exits with 1 if there is any, 0 otherwise, so it can
run in CI or on a schedule.

    uv run python verify.py; echo "exit $?"
"""

import sys

from categories import KEY_PATTERN, connect_redis, customer_of, expected, key


def main() -> int:
    r = connect_redis()
    sets = expected()
    differences = 0

    # every expected set: read all of them in one pipeline
    pipe = r.pipeline(transaction=False)
    for customer_id in sets:
        pipe.smembers(key(customer_id))
    actual = dict(zip(sets, pipe.execute()))

    for customer_id, want in sets.items():
        got = actual[customer_id]
        if got == want:
            continue
        differences += 1
        if not got:
            print(f"{key(customer_id)}: missing (postgres has {len(want)} categories)")
            continue
        print(f"{key(customer_id)}: redis {len(got)} members, postgres {len(want)}"
              + (f"; missing in redis {sorted(want - got)}" if want - got else "")
              + (f"; not in postgres {sorted(got - want)}" if got - want else ""))

    # sets for customers who should not have one
    for k in sorted(r.scan_iter(match=KEY_PATTERN, count=1000)):
        if customer_of(k) not in sets:
            differences += 1
            print(f"{k}: should not exist (customer has no rentals), "
                  f"has {sorted(r.smembers(k))}")

    print(f"checked {len(sets)} customers: "
          + ("redis matches postgres" if differences == 0 else f"{differences} difference(s)"))
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())

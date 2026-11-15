"""Task 1: insert N new rentals for random existing customers and copies.

Each rental and its outbox row are inserted in the same transaction: either both
exist or neither does, so the worker can never miss a rental.

    uv run python rent.py 5000
"""

import os
import random
import sys
import time

import psycopg


def main() -> None:
    n = int(sys.argv[1])
    rng = random.Random()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        customers = [row[0] for row in conn.execute("SELECT customer_id FROM customer")]
        copies = conn.execute("SELECT inventory_id, film_id FROM inventory").fetchall()
        staff = [row[0] for row in conn.execute("SELECT staff_id FROM staff")]

        started = time.perf_counter()
        for i in range(1, n + 1):
            customer_id = rng.choice(customers)
            inventory_id, film_id = rng.choice(copies)
            with conn.transaction():
                conn.execute(
                    "INSERT INTO rental (rental_date, inventory_id, customer_id, staff_id) "
                    "VALUES (clock_timestamp(), %s, %s, %s)",
                    (inventory_id, customer_id, rng.choice(staff)),
                )
                conn.execute(
                    "INSERT INTO outbox (customer_id, film_id) VALUES (%s, %s)",
                    (customer_id, film_id),
                )
            if i % 1000 == 0:
                print(f"rent: {i} rentals inserted ({time.perf_counter() - started:.1f}s)", flush=True)
    print(f"rent: done, {n} rentals and {n} outbox rows", flush=True)


if __name__ == "__main__":
    main()

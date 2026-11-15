"""What rebuild.py and verify.py share: the key name and the one query that reads
the expected sets from PostgreSQL (the source of truth)."""

import os

import psycopg
import redis

KEY_PATTERN = "customer:*:categories"

# For every customer with rentals: the names of the categories of every film rented.
# A film can have several categories; DISTINCT removes the repeats.
EXPECTED_SQL = """
SELECT r.customer_id, array_agg(DISTINCT c.name ORDER BY c.name) AS categories
FROM rental r
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c       ON c.category_id = fc.category_id
GROUP BY r.customer_id
ORDER BY r.customer_id
"""


def key(customer_id: int) -> str:
    return f"customer:{customer_id}:categories"


def customer_of(redis_key: str) -> int:
    return int(redis_key.split(":")[1])


def connect_redis() -> redis.Redis:
    # REDIS_URL must end in /1: this exercise uses logical database 1
    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def expected() -> dict[int, set[str]]:
    """One query: {customer_id: {category, ...}} for every customer with rentals."""
    url = os.environ.get("READONLY_DATABASE_URL") or os.environ["DATABASE_URL"]
    with psycopg.connect(url) as pg:
        return {customer_id: set(names) for customer_id, names in pg.execute(EXPECTED_SQL)}

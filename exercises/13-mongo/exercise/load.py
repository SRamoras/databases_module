"""Tarefa 1: lê a Pagila (PostgreSQL) e escreve films, customers e rentals em pagila_docs.

Correr:
    uv run --env-file .env python load.py

Usa os IDs da Pagila como _id e ReplaceOne(upsert=True): correr duas vezes
deixa exatamente os mesmos documentos (o segundo run só substitui cada
documento por outro igual).
"""

import os
from decimal import Decimal

import psycopg
from bson.decimal128 import Decimal128
from pymongo import MongoClient, ReplaceOne

BATCH = 5000

FILMS_SQL = """
SELECT f.film_id, f.title, f.release_year::int, l.name AS language, f.rating::text,
       f.length, f.rental_duration, f.rental_rate,
       coalesce((SELECT array_agg(c.name ORDER BY c.name)
                 FROM film_category fc JOIN category c ON c.category_id = fc.category_id
                 WHERE fc.film_id = f.film_id), '{}') AS categories,
       coalesce((SELECT json_agg(json_build_object(
                            'actor_id', a.actor_id,
                            'name', a.first_name || ' ' || a.last_name)
                        ORDER BY a.actor_id)
                 FROM film_actor fa JOIN actor a ON a.actor_id = fa.actor_id
                 WHERE fa.film_id = f.film_id), '[]') AS actors
FROM film f
JOIN language l ON l.language_id = f.language_id
ORDER BY f.film_id
"""

CUSTOMERS_SQL = """
SELECT cu.customer_id, cu.first_name, cu.last_name, cu.email, cu.store_id,
       ci.city, co.country,
       (SELECT count(*) FROM rental r WHERE r.customer_id = cu.customer_id) AS rental_count
FROM customer cu
JOIN address a  ON a.address_id = cu.address_id
JOIN city ci    ON ci.city_id = a.city_id
JOIN country co ON co.country_id = ci.country_id
ORDER BY cu.customer_id
"""

# Os 10 alugueres mais recentes de cada cliente
RECENT_SQL = """
SELECT customer_id, rental_id, film_id, title, rental_date, return_date
FROM (
    SELECT r.customer_id, r.rental_id, i.film_id, f.title, r.rental_date, r.return_date,
           row_number() OVER (PARTITION BY r.customer_id
                              ORDER BY r.rental_date DESC, r.rental_id DESC) AS n
    FROM rental r
    JOIN inventory i ON i.inventory_id = r.inventory_id
    JOIN film f      ON f.film_id = i.film_id
) t
WHERE n <= 10
ORDER BY customer_id, n
"""

RENTALS_SQL = """
WITH film_categories AS (
    SELECT fc.film_id, array_agg(c.name ORDER BY c.name) AS categories
    FROM film_category fc JOIN category c ON c.category_id = fc.category_id
    GROUP BY fc.film_id
),
amounts AS (
    SELECT rental_id, sum(amount) AS amount FROM payment GROUP BY rental_id
)
SELECT r.rental_id, r.customer_id, i.film_id, f.title,
       coalesce(fcat.categories, '{}') AS categories,
       i.store_id, r.rental_date, r.return_date,
       coalesce(am.amount, 0) AS amount
FROM rental r
JOIN inventory i            ON i.inventory_id = r.inventory_id
JOIN film f                 ON f.film_id = i.film_id
LEFT JOIN film_categories fcat ON fcat.film_id = i.film_id
LEFT JOIN amounts am        ON am.rental_id = r.rental_id
ORDER BY r.rental_id
"""


def dec(value: Decimal) -> Decimal128:
    """Dinheiro como Decimal128, nunca como float."""
    return Decimal128(value)


def write(collection, docs) -> int:
    """Substitui cada documento pelo _id (cria-o se não existir), em lotes."""
    ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
    for i in range(0, len(ops), BATCH):
        collection.bulk_write(ops[i : i + BATCH], ordered=False)
    return len(ops)


def load_films(pg, db) -> int:
    docs = [
        {
            "_id": film_id,
            "title": title,
            "release_year": release_year,
            "language": language,
            "rating": rating,
            "length": length,
            "rental_duration": rental_duration,
            "rental_rate": dec(rental_rate),
            "categories": categories,
            "actors": actors,
        }
        for (film_id, title, release_year, language, rating, length, rental_duration,
             rental_rate, categories, actors) in pg.execute(FILMS_SQL)
    ]
    return write(db.films, docs)


def load_customers(pg, db) -> int:
    recent: dict[int, list[dict]] = {}
    for customer_id, rental_id, film_id, title, rental_date, return_date in pg.execute(RECENT_SQL):
        recent.setdefault(customer_id, []).append(
            {
                "rental_id": rental_id,
                "film_id": film_id,
                "title": title,
                "rental_date": rental_date,
                "return_date": return_date,
            }
        )
    docs = [
        {
            "_id": customer_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "store_id": store_id,
            "address": {"city": city, "country": country},
            "rental_count": rental_count,
            "recent_rentals": recent.get(customer_id, []),
        }
        for (customer_id, first_name, last_name, email, store_id, city, country,
             rental_count) in pg.execute(CUSTOMERS_SQL)
    ]
    return write(db.customers, docs)


def load_rentals(pg, db) -> int:
    docs = [
        {
            "_id": rental_id,
            "customer_id": customer_id,
            "film_id": film_id,
            "title": title,
            "categories": categories,
            "store_id": store_id,
            "rental_date": rental_date,
            "return_date": return_date,
            "amount": dec(amount),
        }
        for (rental_id, customer_id, film_id, title, categories, store_id, rental_date,
             return_date, amount) in pg.execute(RENTALS_SQL)
    ]
    return write(db.rentals, docs)


def main() -> None:
    db = MongoClient(os.environ["MONGO_URL"], tz_aware=True)["pagila_docs"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        print("films:", load_films(pg, db))
        print("customers:", load_customers(pg, db))
        print("rentals:", load_rentals(pg, db))
    for name in ("films", "customers", "rentals"):
        print(f"{name}: {db[name].count_documents({})} documentos")


if __name__ == "__main__":
    main()

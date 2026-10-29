"""Acrescenta 1 000 000 de alugueres à tabela rental de uma cópia de Pagila, com COPY.

Uso: uv run seed.py <nome da base de dados>

A ligação vem de DATABASE_URL; o nome da base de dados do argumento substitui o do URL.
Os dados são reproduzíveis (semente fixa) e o script é idempotente: se os alugueres
100 001 a 1 100 000 já existirem, não faz nada.
"""

import os
import random
import sys
import time
from datetime import UTC, datetime, timedelta

import psycopg

SEED = 42
FIRST_ID = 100_001
ROWS = 1_000_000
LAST_ID = FIRST_ID + ROWS - 1
START = datetime(2022, 1, 1, tzinfo=UTC)
END = datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC)
NOT_RETURNED = 0.02  # 2% dos alugueres ficam por devolver
MAX_RENTAL_SECONDS = 10 * 24 * 3600  # devolução até 10 dias depois


def ids(conn: psycopg.Connection, query: str) -> list[int]:
    # ORDER BY garante a mesma lista (e portanto os mesmos dados) em todas as cópias.
    return [row[0] for row in conn.execute(query)]


def generate(inventory: list[int], customers: list[int], staff: list[int], taken: set):
    rng = random.Random(SEED)
    span = int((END - START).total_seconds())
    for rental_id in range(FIRST_ID, LAST_ID + 1):
        while True:
            rental_date = START + timedelta(seconds=rng.randint(0, span))
            inventory_id = rng.choice(inventory)
            customer_id = rng.choice(customers)
            key = (rental_date, inventory_id, customer_id)
            if key not in taken:  # respeita o índice único (rental_date, inventory_id, customer_id)
                taken.add(key)
                break
        if rng.random() < NOT_RETURNED:
            return_date = None
        else:
            return_date = rental_date + timedelta(seconds=rng.randint(1, MAX_RENTAL_SECONDS))
        yield rental_id, rental_date, inventory_id, customer_id, return_date, rng.choice(staff)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Uso: uv run seed.py <nome da base de dados>")
    dbname = sys.argv[1]

    started = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"], dbname=dbname) as conn:
        existing = conn.execute(
            "SELECT count(*) FROM rental WHERE rental_id BETWEEN %s AND %s", (FIRST_ID, LAST_ID)
        ).fetchone()[0]
        if existing == ROWS:
            print(f"{dbname}: os {ROWS} alugueres já existem, nada a fazer.")
            return
        if existing:
            sys.exit(f"{dbname}: só existem {existing} dos {ROWS} alugueres, recria a base de dados.")

        inventory = ids(conn, "SELECT inventory_id FROM inventory ORDER BY inventory_id")
        customers = ids(conn, "SELECT customer_id FROM customer ORDER BY customer_id")
        staff = ids(conn, "SELECT staff_id FROM staff ORDER BY staff_id")
        taken = set(conn.execute("SELECT rental_date, inventory_id, customer_id FROM rental"))

        # Tudo numa transação: ou entram as 1 000 000 linhas, ou nenhuma.
        with conn.cursor().copy(
            "COPY rental (rental_id, rental_date, inventory_id, customer_id, return_date, staff_id)"
            " FROM STDIN"
        ) as copy:
            for row in generate(inventory, customers, staff, taken):
                copy.write_row(row)

        # O próximo INSERT sem rental_id recebe LAST_ID + 1.
        conn.execute("SELECT setval('rental_rental_id_seq', %s)", (LAST_ID,))

    print(f"{dbname}: {ROWS} alugueres inseridos em {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

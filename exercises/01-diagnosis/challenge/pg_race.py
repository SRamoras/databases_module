"""10 processos, cada um com a sua ligação, inserem 1000 registos cada na tabela record."""

import multiprocessing
import os

import psycopg

WORKERS = 10
RECORDS_PER_WORKER = 1000
DATABASE_URL = os.environ["DATABASE_URL"]


def worker(number: int) -> None:
    # autocommit: cada INSERT é uma transação própria, como cada escrita no JSON.
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        for n in range(RECORDS_PER_WORKER):
            conn.execute("INSERT INTO record (worker, n) VALUES (%s, %s)", (number, n))


def main() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS record (worker integer NOT NULL, n integer NOT NULL)"
        )
        conn.execute("TRUNCATE record")

    processes = [multiprocessing.Process(target=worker, args=(i,)) for i in range(WORKERS)]
    for p in processes:
        p.start()
    for p in processes:
        p.join()

    with psycopg.connect(DATABASE_URL) as conn:
        count = conn.execute("SELECT count(*) FROM record").fetchone()[0]

    print(f"SELECT count(*) FROM record: {count} (expected {WORKERS * RECORDS_PER_WORKER})")


if __name__ == "__main__":
    main()

"""Insere trabalhos na fila.

Uso:
    uv run producer.py             10 000 trabalhos com payload {"n": <número>}
    uv run producer.py --slow 30   um trabalho cujo processamento dorme 30 segundos
"""

import os
import sys

import psycopg
from psycopg.types.json import Jsonb

JOBS = 10_000
DATABASE_URL = os.environ["DATABASE_URL"]


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        if len(sys.argv) == 3 and sys.argv[1] == "--slow":
            seconds = int(sys.argv[2])
            job_id = conn.execute(
                "INSERT INTO job (payload) VALUES (%s) RETURNING job_id",
                (Jsonb({"n": 0, "sleep_seconds": seconds}),),
            ).fetchone()[0]
            print(f"inserted slow job {job_id} ({seconds} s)")
            return

        with conn.cursor().copy("COPY job (payload) FROM STDIN") as copy:
            for n in range(1, JOBS + 1):
                copy.write_row((Jsonb({"n": n}),))
        print(f"inserted {JOBS} jobs")


if __name__ == "__main__":
    main()

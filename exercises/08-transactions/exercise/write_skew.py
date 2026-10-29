"""Write skew: 20 funcionários da loja 1 desativam-se ao mesmo tempo.

Regra: cada loja mantém pelo menos um funcionário ativo.
Cada thread, numa transação: conta os ativos da loja 1; se forem mais de 1, desativa-se; commit.
Uma Barrier(20) entre a contagem e o update garante que todas leem antes de alguma escrever.

Uso: uv run write_skew.py read-committed | serializable
"""

import os
import sys
import threading

import psycopg
from psycopg import IsolationLevel, errors

STORE_ID = 1
DATABASE_URL = os.environ["DATABASE_URL"]
LEVELS = {
    "read-committed": IsolationLevel.READ_COMMITTED,
    "serializable": IsolationLevel.SERIALIZABLE,
}


def active_staff() -> list[int]:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT staff_id FROM staff WHERE store_id = %s AND active ORDER BY staff_id",
            (STORE_ID,),
        ).fetchall()
    return [row[0] for row in rows]


def worker(staff_id: int, level: IsolationLevel, barrier: threading.Barrier, log: list) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.isolation_level = level
        attempt = 0
        while True:
            attempt += 1
            try:
                with conn.transaction():
                    count = conn.execute(
                        "SELECT count(*) FROM staff WHERE store_id = %s AND active", (STORE_ID,)
                    ).fetchone()[0]
                    if attempt == 1:
                        barrier.wait()  # só na primeira tentativa, como pede o enunciado
                    if count > 1:
                        conn.execute(
                            "UPDATE staff SET active = false WHERE staff_id = %s", (staff_id,)
                        )
                        action = "deactivated"
                    else:
                        action = "stayed active"
                log.append(f"staff {staff_id}: attempt {attempt}, saw {count} active, {action}")
                return
            except errors.SerializationFailure:
                log.append(f"staff {staff_id}: attempt {attempt}, serialization failure (40001), retrying")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in LEVELS:
        sys.exit("Uso: uv run write_skew.py read-committed | serializable")
    level = LEVELS[sys.argv[1]]

    staff = active_staff()
    print(f"isolation: {sys.argv[1]}")
    print(f"active staff in store {STORE_ID} before: {len(staff)}")

    barrier = threading.Barrier(len(staff))
    log: list[str] = []
    threads = [threading.Thread(target=worker, args=(s, level, barrier, log)) for s in staff]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for line in log:
        print("  " + line)
    failures = sum("serialization failure" in line for line in log)
    print(f"serialization failures (retried): {failures}")
    print(f"active staff in store {STORE_ID} after: {len(active_staff())}")


if __name__ == "__main__":
    main()

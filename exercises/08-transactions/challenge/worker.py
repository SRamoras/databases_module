"""Processa trabalhos da fila até não haver nenhum pendente.

Uso: uv run worker.py <número do worker>

Cada trabalho é uma transação: reclama-o com FOR UPDATE SKIP LOCKED, processa-o
(regista o resultado e dorme), marca-o como done e faz commit. Se o processo morrer
a meio, a transação é desfeita e o trabalho volta a estar disponível.
"""

import os
import random
import sys
import time

import psycopg

DATABASE_URL = os.environ["DATABASE_URL"]


def main() -> None:
    worker = int(sys.argv[1])
    processed = 0
    # application_name identifica o worker em pg_stat_activity.
    with psycopg.connect(DATABASE_URL, application_name=f"worker-{worker}") as conn:
        while True:
            with conn.transaction():
                row = conn.execute(
                    "SELECT job_id, payload FROM job WHERE status = 'pending'"
                    " ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1"
                ).fetchone()
                if row is None:
                    break  # nenhum trabalho pendente que não esteja já reclamado por outro worker
                job_id, payload = row

                conn.execute(
                    "INSERT INTO job_result (job_id, worker) VALUES (%s, %s)", (job_id, worker)
                )
                if "sleep_seconds" in payload:
                    print(f"worker {worker} (pid {os.getpid()}): job {job_id} sleeps {payload['sleep_seconds']} s", flush=True)
                    time.sleep(payload["sleep_seconds"])
                else:
                    time.sleep(random.uniform(0.001, 0.005))

                conn.execute("UPDATE job SET status = 'done' WHERE job_id = %s", (job_id,))
            processed += 1

    print(f"worker {worker}: processed {processed} jobs", flush=True)


if __name__ == "__main__":
    main()

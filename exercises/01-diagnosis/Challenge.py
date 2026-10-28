"""
Desafio de concorrência: 10 processos x 1000 registos.

Parte 1: todos fazem read -> append -> write back ao MESMO ficheiro JSON.
Parte 2: todos inserem na MESMA tabela PostgreSQL, cada um com a sua ligação.

Uso:
    pip install psycopg2-binary
    export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
    python concurrency_test.py

Sem DATABASE_URL, corre só a parte do JSON.
"""
import json
import os
import time
from multiprocessing import Process, Queue

N_PROCS = 10
N_RECORDS = 1000
EXPECTED = N_PROCS * N_RECORDS
JSON_FILE = "records.json"                                                                                                                                                                                


# ---------------------------------------------------------------- JSON
def json_worker(worker_id, failures):
    failed_reads = 0
    for seq in range(N_RECORDS):
        # 1. read
        try:
            with open(JSON_FILE) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            # outro processo estava a meio de escrever: ficheiro truncado
            failed_reads += 1
            continue
        # 2. append
        data.append({"worker": worker_id, "seq": seq})
        # 3. write back (o "w" trunca o ficheiro antes de escrever)
        with open(JSON_FILE, "w") as f:
            json.dump(data, f)
    failures.put(failed_reads)


def run_json():
    with open(JSON_FILE, "w") as f:
        json.dump([], f)

    failures = Queue()
    procs = [Process(target=json_worker, args=(i, failures)) for i in range(N_PROCS)]
    start = time.time()
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    elapsed = time.time() - start

    failed_reads = sum(failures.get() for _ in procs)

    # O ficheiro pode ter ficado corrompido (dois processos a escrever
    # ao mesmo tempo). Nesse caso contamos só os registos do primeiro
    # array JSON válido e assinalamos a corrupção.
    with open(JSON_FILE) as f:
        raw = f.read()
    corrupted = False
    try:
        total = len(json.loads(raw))
    except json.JSONDecodeError:
        corrupted = True
        try:
            total = len(json.JSONDecoder().raw_decode(raw)[0])
        except json.JSONDecodeError:
            total = 0
    return total, failed_reads, corrupted, elapsed


# ---------------------------------------------------------- PostgreSQL
def pg_worker(dsn, worker_id):
    import psycopg2

    conn = psycopg2.connect(dsn)  # uma ligação por processo
    cur = conn.cursor()
    for seq in range(N_RECORDS):
        cur.execute(
            "INSERT INTO records (worker, seq) VALUES (%s, %s)", (worker_id, seq)
        )
        conn.commit()  # um commit por registo, como no JSON
    conn.close()


def run_postgres(dsn):
    import psycopg2

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS records")
    cur.execute(
        """CREATE TABLE records (
               id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
               worker integer NOT NULL,
               seq    integer NOT NULL
           )"""
    )
    conn.commit()

    procs = [Process(target=pg_worker, args=(dsn, i)) for i in range(N_PROCS)]
    start = time.time()
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    elapsed = time.time() - start

    cur.execute("SELECT count(*) FROM records")
    total = cur.fetchone()[0]
    conn.close()
    return total, elapsed


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    print(f"Esperado: {EXPECTED} registos ({N_PROCS} processos x {N_RECORDS})\n")

    total, failed_reads, corrupted, t = run_json()
    print("JSON (read, append, write back)")
    print(f"  registos no ficheiro : {total}")
    print(f"  registos perdidos    : {EXPECTED - total}")
    print(f"  leituras falhadas    : {failed_reads} (ficheiro lido a meio de uma escrita)")
    print(f"  ficheiro corrompido  : {'SIM (JSON inválido no fim)' if corrupted else 'não'}")
    print(f"  tempo                : {t:.1f}s\n")

    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        total, t = run_postgres(dsn)
        print("PostgreSQL (10 ligações em simultâneo)")
        print(f"  registos na tabela   : {total}")
        print(f"  registos perdidos    : {EXPECTED - total}")
        print(f"  tempo                : {t:.1f}s")
    else:
        print("DATABASE_URL não definida: parte do PostgreSQL ignorada.")
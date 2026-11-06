"""Tarefa 6: 5 POST /rentals simultâneos para o filme 7 na loja 1.

O filme 7 tem exatamente 2 cópias na loja 1. Resultado esperado: dois 201 e
três 409, com dois inventory_id diferentes.

Correr (com a API a correr):
    uv run python concurrency_test.py               # http://127.0.0.1:8000
    API_URL=http://127.0.0.1:8012 uv run python concurrency_test.py

No fim devolve as cópias alugadas (POST /rentals/{id}/return), para o teste
poder correr outra vez. Com --keep deixa os alugueres abertos.
"""

import os
import sys
import threading
from collections import Counter

import httpx

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
FILM_ID, STORE_ID, STAFF_ID = 7, 1, 6
CUSTOMERS = [1, 2, 3, 4, 5]

barrier = threading.Barrier(len(CUSTOMERS))
results: dict[int, httpx.Response] = {}


def rent(customer_id: int) -> None:
    body = {"customer_id": customer_id, "film_id": FILM_ID, "store_id": STORE_ID, "staff_id": STAFF_ID}
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        barrier.wait()  # todos os pedidos partem ao mesmo tempo
        results[customer_id] = client.post("/rentals", json=body)


def main() -> int:
    threads = [threading.Thread(target=rent, args=(c,)) for c in CUSTOMERS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for customer_id in CUSTOMERS:
        r = results[customer_id]
        print(f"customer {customer_id}: {r.status_code} {r.json()}")

    statuses = Counter(r.status_code for r in results.values())
    created = [r.json() for r in results.values() if r.status_code == 201]
    inventory_ids = {c["inventory_id"] for c in created}
    print(f"\n201: {statuses[201]}  409: {statuses[409]}  inventory_id: {sorted(inventory_ids)}")

    ok = statuses == Counter({201: 2, 409: 3}) and len(inventory_ids) == 2
    print("OK" if ok else "FALHOU")

    if "--keep" not in sys.argv:
        with httpx.Client(base_url=API_URL) as client:
            for c in created:
                client.post(f"/rentals/{c['rental_id']}/return")
        print(f"(devolvidos os alugueres {[c['rental_id'] for c in created]})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

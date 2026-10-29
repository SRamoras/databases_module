"""10 processos acrescentam 1000 registos cada ao mesmo ficheiro JSON, sem lock.

Cada escrita é: ler o ficheiro todo, acrescentar um registo, escrever o ficheiro todo.

Por omissão o ficheiro é escrito num ficheiro temporário e trocado com os.replace,
para que nunca fique meio escrito. Com --in-place é escrito diretamente por cima.
"""

import json
import multiprocessing
import os
import sys
from pathlib import Path

WORKERS = 10
RECORDS_PER_WORKER = 1000
FILE = Path(__file__).with_name("records.json")


def write_file(number: int, content: str, in_place: bool) -> None:
    if in_place:
        # open("w") esvazia o ficheiro antes de escrever: outro processo pode lê-lo vazio ou a meio.
        FILE.write_text(content)
    else:
        tmp = FILE.with_name(f"{FILE.name}.{number}.tmp")
        tmp.write_text(content)
        os.replace(tmp, FILE)


def worker(number: int, failed: multiprocessing.Value, in_place: bool) -> None:
    for n in range(RECORDS_PER_WORKER):
        try:
            records = json.loads(FILE.read_text())
            records.append({"worker": number, "n": n})
            write_file(number, json.dumps(records), in_place)
        except (json.JSONDecodeError, OSError):
            # O ficheiro estava vazio ou a meio de uma escrita de outro processo.
            with failed.get_lock():
                failed.value += 1


def main() -> None:
    in_place = "--in-place" in sys.argv
    FILE.write_text("[]")
    failed = multiprocessing.Value("i", 0)

    processes = [
        multiprocessing.Process(target=worker, args=(i, failed, in_place))
        for i in range(WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join()

    try:
        count = len(json.loads(FILE.read_text()))
        status = "valid JSON"
    except json.JSONDecodeError:
        count = 0
        status = "CORRUPTED, not valid JSON"

    print(f"records in file: {count} (expected {WORKERS * RECORDS_PER_WORKER}), file is {status}")
    print(f"failed writes:   {failed.value}")


if __name__ == "__main__":
    main()

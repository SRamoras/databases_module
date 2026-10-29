"""Cria os utilizadores MongoDB das duas instâncias. Pode correr mais do que uma vez.

ex09_app    (instância A): readWrite em ex09
ex09_reader (instância B): read em ex09

Corre como root (MONGO_ADMIN_URL do .env.setup). A coleção notes e o seu validador são
criados pelo setup_mongo.py do exercício.
"""

import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(".env.setup")

DB = os.environ["MONGO_DB"]
USERS = {
    "ex09_app": (os.environ["MONGO_APP_PASSWORD"], "readWrite"),
    "ex09_reader": (os.environ["MONGO_READER_PASSWORD"], "read"),
}


def main() -> None:
    db = MongoClient(os.environ["MONGO_ADMIN_URL"])[DB]
    for user, (password, role) in USERS.items():
        roles = [{"role": role, "db": DB}]
        if db.command("usersInfo", user)["users"]:
            db.command("updateUser", user, pwd=password, roles=roles)
            print(f"updated user {user} on {DB}: {role} on {DB}")
        else:
            db.command("createUser", user, pwd=password, roles=roles)
            print(f"created user {user} on {DB}: {role} on {DB}")


if __name__ == "__main__":
    main()

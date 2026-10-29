"""Cria o utilizador MongoDB da API e a coleção notes com validação. Pode correr mais do que uma vez.

O utilizador é criado como root (MONGO_ADMIN_URL), com readWrite só na base de dados ex09.
Depois liga-se como o novo utilizador (MONGO_URL) e mostra o que pode e não pode fazer.
"""

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure, WriteError

load_dotenv()

DB = os.environ["MONGO_DB"]
USER = "ex09_app"

# Defesa em profundidade: mesmo que a API deixasse passar um tipo errado, o MongoDB recusava.
NOTES_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["customer_id", "text"],
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "objectId"},
            "customer_id": {"bsonType": ["int", "long"]},
            "text": {"bsonType": "string", "minLength": 1, "maxLength": 2000},
        },
    }
}


def setup_as_admin() -> None:
    db = MongoClient(os.environ["MONGO_ADMIN_URL"])[DB]
    roles = [{"role": "readWrite", "db": DB}]
    password = os.environ["MONGO_APP_PASSWORD"]
    # O utilizador vive em ex09 (authSource=ex09), por isso não colide com os de outros projetos.
    if db.command("usersInfo", USER)["users"]:
        db.command("updateUser", USER, pwd=password, roles=roles)
        print(f"updated user {USER} on {DB}: readWrite on {DB}")
    else:
        db.command("createUser", USER, pwd=password, roles=roles)
        print(f"created user {USER} on {DB}: readWrite on {DB}")

    if "notes" in db.list_collection_names():
        db.command("collMod", "notes", validator=NOTES_SCHEMA, validationLevel="strict")
    else:
        db.create_collection("notes", validator=NOTES_SCHEMA, validationLevel="strict")
    print("collection notes: $jsonSchema validator (customer_id int, text string)")


def prove_as_app() -> None:
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[DB]
    print(f"connected as {db.command('connectionStatus')['authInfo']['authenticatedUsers']}")

    result = db.probe.insert_one({"x": 1})
    print(f"insert into {DB}.probe: allowed")
    db.probe.delete_one({"_id": result.inserted_id})

    try:
        db.notes.insert_one({"customer_id": 1, "text": {"$ne": None}})
        print("insert note with an object as text: allowed (unexpected)")
    except WriteError as exc:
        print(f"insert note with an object as text: refused by the validator ({exc.details['errmsg']})")

    try:
        client[f"{DB}_other"].probe.insert_one({"x": 1})
        print(f"insert into {DB}_other: allowed (unexpected)")
    except OperationFailure as exc:
        print(f"insert into {DB}_other: refused ({exc.details['codeName']})")

    try:
        db.command("dropDatabase")
        print(f"dropDatabase {DB}: allowed")
    except OperationFailure as exc:
        print(f"dropDatabase {DB}: refused ({exc.details['codeName']})")


if __name__ == "__main__":
    setup_as_admin()
    prove_as_app()

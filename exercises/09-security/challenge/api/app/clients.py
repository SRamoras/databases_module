import os

import psycopg
import redis
from pymongo import MongoClient

# As credenciais vêm só do ambiente da instância (uvicorn --env-file .env.a ou .env.b).
# O código é o mesmo nas duas instâncias e não sabe qual delas é: só os utilizadores mudam.
DATABASE_URL = os.environ["DATABASE_URL"]

mongo = MongoClient(os.environ["MONGO_URL"])
mongo_db = mongo[os.environ["MONGO_DB"]]

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def pg_connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)

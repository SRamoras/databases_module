import os

import psycopg
import redis
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# Só as credenciais da aplicação. As de administração são usadas apenas pelos scripts de setup.
DATABASE_URL = os.environ["DATABASE_URL"]  # role ex09_app

mongo = MongoClient(os.environ["MONGO_URL"])  # utilizador ex09_app, readWrite só em ex09
mongo_db = mongo[os.environ["MONGO_DB"]]

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)  # ACL: só INCR em counter:*


def pg_connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)

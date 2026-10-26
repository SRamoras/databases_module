from sqlalchemy import text
from sqlmodel import Session, select

from db import public_engine, private_engine
from models.public import public_metadata, Produto
from models.private import private_metadata

# 1. criar as tabelas (só cria as que ainda não existem)
with private_engine.begin() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS privado"))

public_metadata.create_all(public_engine)
private_metadata.create_all(private_engine)

# 2. a tua consulta
with Session(public_engine) as s:
    for p in s.exec(select(Produto)).all():
        print(p.nome, p.preco)
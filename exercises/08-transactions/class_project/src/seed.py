from sqlmodel import Session
from db import public_engine, private_engine
from models.public import Produto
from models.private import Cliente

with Session(public_engine) as s:
    s.add(Produto(nome="Caneta", preco=1.5))
    s.commit()

with Session(private_engine) as s:
    s.add(Cliente(nome="Ana", email="ana@example.com"))
    s.commit()
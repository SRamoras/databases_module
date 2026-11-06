import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQL_ECHO=1 mostra no log cada instrução SQL (para contar as consultas).
engine = create_engine(
    os.environ["DATABASE_URL"],
    echo=os.environ.get("SQL_ECHO") == "1",
    pool_size=10,
)
SessionLocal = sessionmaker(engine)


def get_session():
    """Uma sessão por pedido, fechada no fim do pedido."""
    with SessionLocal() as session:
        yield session

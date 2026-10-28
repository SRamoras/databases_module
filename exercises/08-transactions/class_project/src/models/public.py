from sqlalchemy import MetaData
from sqlmodel import SQLModel, Field

public_metadata = MetaData()

class PublicBase(SQLModel):
    metadata = public_metadata

class Produto(PublicBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    preco: float
from sqlalchemy import MetaData
from sqlmodel import SQLModel, Field

private_metadata = MetaData(schema="privado")

class PrivateBase(SQLModel):
    metadata = private_metadata

class Cliente(PrivateBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    email: str = Field(unique=True)
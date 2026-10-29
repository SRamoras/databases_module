from typing import Annotated

from fastapi import FastAPI, Path
from pydantic import BaseModel, ConfigDict, Field

from app.clients import mongo_db, pg_connect, r

app = FastAPI(title="Exercício 09: segurança")

# strict=True: um campo só aceita o seu tipo exato. "1" não passa a 1, e um objeto
# como {"$ne": null} não passa a texto. Qualquer outro tipo dá 422 antes de chegar ao motor.


class ActorIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    first_name: str = Field(min_length=1, max_length=45)
    last_name: str = Field(min_length=1, max_length=45)


class NoteIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    customer_id: int
    text: str = Field(min_length=1, max_length=2000)


CounterName = Annotated[str, Path(pattern=r"^[a-z0-9_-]{1,32}$")]


@app.post("/actors", status_code=201)
def create_actor(body: ActorIn):
    # Query parametrizada: o texto SQL e os valores viajam separados, os valores nunca são lidos como SQL.
    with pg_connect() as conn:
        actor_id = conn.execute(
            "INSERT INTO actor (first_name, last_name) VALUES (%s, %s) RETURNING actor_id",
            (body.first_name, body.last_name),
        ).fetchone()[0]
    return {"actor_id": actor_id}


@app.post("/notes", status_code=201)
def create_note(body: NoteIn):
    # O documento é construído campo a campo a partir do modelo validado, nunca a partir do JSON bruto.
    result = mongo_db.notes.insert_one({"customer_id": body.customer_id, "text": body.text})
    return {"note_id": str(result.inserted_id)}


@app.post("/counters/{name}")
def increment_counter(name: CounterName):
    # O nome já foi validado pelo padrão, por isso a chave é sempre counter:<letras, dígitos, _ ou ->.
    # INCR explícito: r.incr() do redis-py envia INCRBY, que o ACL de ex09_app não permite.
    return {"name": name, "value": r.execute_command("INCR", f"counter:{name}")}

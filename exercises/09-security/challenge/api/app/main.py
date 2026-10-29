from typing import Annotated

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import OperationFailure

from app.clients import mongo_db, pg_connect, r

app = FastAPI(title="Desafio 09: a base de dados decide quem escreve")

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


# --- Erros de privilégio dos motores -> 403 --------------------------------------------------
# Nenhum endpoint verifica que instância é. Um 403 só acontece quando o próprio motor recusa a
# operação por falta de privilégio; qualquer outro erro continua a ser um 500.


def forbidden(engine: str, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": f"{engine} refused: {exc}"})


@app.exception_handler(psycopg.errors.InsufficientPrivilege)  # SQLSTATE 42501
async def postgres_forbidden(request: Request, exc: psycopg.errors.InsufficientPrivilege):
    return forbidden("postgres", exc)


@app.exception_handler(OperationFailure)
async def mongo_forbidden(request: Request, exc: OperationFailure):
    if exc.code == 13:  # Unauthorized
        return forbidden("mongodb", exc.details.get("errmsg", exc))
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.exception_handler(redis.exceptions.NoPermissionError)  # NOPERM
async def redis_forbidden(request: Request, exc: redis.exceptions.NoPermissionError):
    return forbidden("redis", exc)


# --- PostgreSQL ------------------------------------------------------------------------------


@app.post("/actors", status_code=201)
def create_actor(body: ActorIn):
    # Query parametrizada: o texto SQL e os valores viajam separados, os valores nunca são lidos como SQL.
    with pg_connect() as conn:
        actor_id = conn.execute(
            "INSERT INTO actor (first_name, last_name) VALUES (%s, %s) RETURNING actor_id",
            (body.first_name, body.last_name),
        ).fetchone()[0]
    return {"actor_id": actor_id}


@app.get("/actors/{actor_id}")
def get_actor(actor_id: int):
    with pg_connect() as conn:
        row = conn.execute(
            "SELECT actor_id, first_name, last_name FROM actor WHERE actor_id = %s", (actor_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "actor not found")
    return {"actor_id": row[0], "first_name": row[1], "last_name": row[2]}


# --- MongoDB ---------------------------------------------------------------------------------


@app.post("/notes", status_code=201)
def create_note(body: NoteIn):
    # O documento é construído campo a campo a partir do modelo validado, nunca a partir do JSON bruto.
    result = mongo_db.notes.insert_one({"customer_id": body.customer_id, "text": body.text})
    return {"note_id": str(result.inserted_id)}


@app.get("/notes")
def list_notes(customer_id: int):
    # customer_id já é um int validado, por isso o filtro nunca recebe um operador como {"$ne": ...}.
    notes = mongo_db.notes.find({"customer_id": customer_id}).sort("_id", 1)
    return [{"note_id": str(n["_id"]), "customer_id": n["customer_id"], "text": n["text"]} for n in notes]


# --- Redis -----------------------------------------------------------------------------------


@app.post("/counters/{name}")
def increment_counter(name: CounterName):
    # O nome já foi validado pelo padrão, por isso a chave é sempre counter:<letras, dígitos, _ ou ->.
    # INCR explícito: r.incr() do redis-py envia INCRBY, que o ACL de ex09_app não permite.
    return {"name": name, "value": r.execute_command("INCR", f"counter:{name}")}


@app.get("/counters/{name}")
def get_counter(name: CounterName):
    value = r.get(f"counter:{name}")
    return {"name": name, "value": int(value) if value is not None else 0}

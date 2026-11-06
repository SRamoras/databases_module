"""Tarefa 3: um N+1 de propósito e a correção com eager loading.

Correr: uv run --env-file ../../../.env python n_plus_one.py
"""

import os

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, selectinload

from models import Film

engine = create_engine(os.environ["DATABASE_URL"], echo=True)

# Conta os SELECT que o engine envia, para não ter de os contar à mão no log.
selects = 0


@event.listens_for(engine, "before_cursor_execute")
def count_selects(conn, cursor, statement, parameters, context, executemany):
    global selects
    if statement.lstrip().upper().startswith("SELECT"):
        selects += 1


def print_films(films):
    for film in films:
        names = ", ".join(f"{a.first_name} {a.last_name}" for a in film.actors)
        print(f"{film.title}: {names}")


def run(label, stmt):
    global selects
    selects = 0
    # Sessão nova em cada versão, para que os atores não venham já do identity map.
    with Session(engine) as session:
        print_films(session.scalars(stmt).all())
    return label, selects


if __name__ == "__main__":
    base = select(Film).order_by(Film.film_id).limit(100)
    results = [
        run("N+1 (lazy loading)", base),
        run("corrigido (selectinload)", base.options(selectinload(Film.actors))),
    ]
    print()
    for label, n in results:
        print(f"{label}: {n} SELECT")

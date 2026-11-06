"""Tarefa 2: as 3 consultas do enunciado escritas com o ORM.

Correr: uv run --env-file ../../../.env python queries.py
(com DATABASE_URL a apontar para a base ex11 e o esquema postgresql+psycopg://)
"""

import os

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from models import Actor, Category, Film, FilmActor, FilmCategory

engine = create_engine(os.environ["DATABASE_URL"], echo=True)


# Q1: número de filmes por categoria, mais filmes primeiro
films_count = func.count().label("films")
q1 = (
    select(Category.name, films_count)
    .join(FilmCategory, FilmCategory.category_id == Category.category_id)
    .group_by(Category.category_id, Category.name)
    .order_by(films_count.desc(), Category.name)
)

# Q2: filmes mais longos do que a média
avg_length = select(func.avg(Film.length)).scalar_subquery()
q2 = (
    select(Film.film_id, Film.title, Film.length)
    .where(Film.length > avg_length)
    .order_by(Film.length.desc(), Film.film_id)
)

# Q3: os 10 atores com mais filmes
actor_films = func.count().label("films")
q3 = (
    select(Actor.actor_id, Actor.first_name, Actor.last_name, actor_films)
    .join(FilmActor, FilmActor.actor_id == Actor.actor_id)
    .group_by(Actor.actor_id)
    .order_by(actor_films.desc(), Actor.actor_id)
    .limit(10)
)


# O SQL escrito à mão do enunciado, para comparar as linhas.
HANDWRITTEN = {
    "Q1": """
        SELECT c.name, count(*) AS films
        FROM category c JOIN film_category fc ON fc.category_id = c.category_id
        GROUP BY c.category_id, c.name
        ORDER BY films DESC, c.name""",
    "Q2": """
        SELECT f.film_id, f.title, f.length
        FROM film f
        WHERE f.length > (SELECT avg(length) FROM film)
        ORDER BY f.length DESC, f.film_id""",
    "Q3": """
        SELECT a.actor_id, a.first_name, a.last_name, count(*) AS films
        FROM actor a JOIN film_actor fa ON fa.actor_id = a.actor_id
        GROUP BY a.actor_id
        ORDER BY films DESC, a.actor_id
        LIMIT 10""",
}


if __name__ == "__main__":
    with Session(engine) as session:
        for name, q in (("Q1", q1), ("Q2", q2), ("Q3", q3)):
            rows = [tuple(r) for r in session.execute(q)]
            expected = [tuple(r) for r in session.execute(text(HANDWRITTEN[name]))]
            same = "iguais" if rows == expected else "DIFERENTES"
            print(f"\n=== {name}: {len(rows)} linhas, {same} ao SQL escrito à mão ===")
            for row in rows[:5]:
                print(row)

"""The code under test: list films with their actors and categories."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models import Film


def list_films(session: Session, limit: int = 100) -> list[dict]:
    """The first `limit` films by film_id, each with its actors and categories.

    Eager loading keeps this at 3 queries whatever the limit: films, then the
    actors of all of them, then the categories of all of them.
    """
    stmt = (
        select(Film)
        .order_by(Film.film_id)
        .limit(limit)
        .options(selectinload(Film.actors), selectinload(Film.categories))
    )
    return [
        {
            "film_id": film.film_id,
            "title": film.title,
            "actors": [f"{a.first_name} {a.last_name}" for a in film.actors],
            "categories": [c.name for c in film.categories],
        }
        for film in session.scalars(stmt)
    ]

"""SQLAlchemy 2.0 models for 6 Pagila tables: film, language, actor, film_actor,
category and film_category.

The tables already exist (they come from Pagila), so these models only map them.
They are never used to create or change the schema.
"""

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# rating uses the enum type mpaa_rating, which already exists in Pagila
MpaaRating = ENUM("G", "PG", "PG-13", "R", "NC-17", name="mpaa_rating", create_type=False)


class Language(Base):
    __tablename__ = "language"

    language_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    films: Mapped[list["Film"]] = relationship(
        back_populates="language", foreign_keys="Film.language_id"
    )

    def __repr__(self) -> str:
        return f"Language({self.language_id}, {self.name!r})"


class FilmActor(Base):
    """Association table between film and actor (N:M)."""

    __tablename__ = "film_actor"

    actor_id: Mapped[int] = mapped_column(ForeignKey("actor.actor_id"), primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id"), primary_key=True)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FilmCategory(Base):
    """Association table between film and category (N:M)."""

    __tablename__ = "film_category"

    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.category_id"), primary_key=True
    )
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Film(Base):
    __tablename__ = "film"

    film_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # release_year uses the domain "year" (an integer with a CHECK)
    release_year: Mapped[int | None] = mapped_column(Integer)
    language_id: Mapped[int] = mapped_column(ForeignKey("language.language_id"))
    original_language_id: Mapped[int | None] = mapped_column(
        ForeignKey("language.language_id")
    )
    rental_duration: Mapped[int] = mapped_column(SmallInteger)
    rental_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    length: Mapped[int | None] = mapped_column(SmallInteger)
    replacement_cost: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    rating: Mapped[str | None] = mapped_column(MpaaRating)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    special_features: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    fulltext: Mapped[str] = mapped_column(TSVECTOR)

    # film has two foreign keys to language, so each relationship says which one it uses
    language: Mapped[Language] = relationship(
        back_populates="films", foreign_keys=[language_id]
    )
    original_language: Mapped[Language | None] = relationship(
        foreign_keys=[original_language_id]
    )
    actors: Mapped[list["Actor"]] = relationship(
        secondary="film_actor", back_populates="films", order_by="Actor.actor_id"
    )
    categories: Mapped[list["Category"]] = relationship(
        secondary="film_category", back_populates="films", order_by="Category.category_id"
    )

    def __repr__(self) -> str:
        return f"Film({self.film_id}, {self.title!r})"


class Actor(Base):
    __tablename__ = "actor"

    actor_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    films: Mapped[list[Film]] = relationship(
        secondary="film_actor", back_populates="actors", order_by=Film.film_id
    )

    def __repr__(self) -> str:
        return f"Actor({self.actor_id}, {self.first_name} {self.last_name})"


class Category(Base):
    __tablename__ = "category"

    category_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    films: Mapped[list[Film]] = relationship(
        secondary="film_category", back_populates="categories", order_by=Film.film_id
    )

    def __repr__(self) -> str:
        return f"Category({self.category_id}, {self.name!r})"


def database_url() -> str:
    """DATABASE_URL with the psycopg driver in the scheme, as SQLAlchemy needs it."""
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def make_engine(echo: bool = True):
    return create_engine(database_url(), echo=echo)

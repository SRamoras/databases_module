from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Language(Base):
    __tablename__ = "language"

    language_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Actor(Base):
    __tablename__ = "actor"

    actor_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    films: Mapped[list["Film"]] = relationship(
        secondary="film_actor", back_populates="actors"
    )


class Category(Base):
    __tablename__ = "category"

    category_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    films: Mapped[list["Film"]] = relationship(
        secondary="film_category", back_populates="categories"
    )


class Film(Base):
    __tablename__ = "film"

    film_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    release_year: Mapped[Optional[int]]
    language_id: Mapped[int] = mapped_column(ForeignKey("language.language_id"))
    original_language_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("language.language_id")
    )
    rental_duration: Mapped[int] = mapped_column(SmallInteger)
    rental_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    length: Mapped[Optional[int]] = mapped_column(SmallInteger)
    replacement_cost: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    rating: Mapped[Optional[str]] = mapped_column(
        ENUM("G", "PG", "PG-13", "R", "NC-17", name="mpaa_rating", create_type=False)
    )
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    special_features: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    fulltext: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    # Há duas FKs para language: é preciso dizer qual usa esta relationship.
    language: Mapped["Language"] = relationship(foreign_keys=[language_id])
    actors: Mapped[list["Actor"]] = relationship(
        secondary="film_actor", back_populates="films"
    )
    categories: Mapped[list["Category"]] = relationship(
        secondary="film_category", back_populates="films"
    )


class FilmActor(Base):
    __tablename__ = "film_actor"

    actor_id: Mapped[int] = mapped_column(
        ForeignKey("actor.actor_id"), primary_key=True
    )
    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id"), primary_key=True)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FilmCategory(Base):
    __tablename__ = "film_category"

    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.category_id"), primary_key=True
    )
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True))

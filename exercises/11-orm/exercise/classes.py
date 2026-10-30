from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column


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
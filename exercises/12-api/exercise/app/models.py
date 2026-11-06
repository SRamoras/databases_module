"""Modelos das tabelas da Pagila usadas pela API.

Só estão mapeadas as colunas de que a API precisa. O `include_object` de
`migrations/env.py` faz o autogenerate ignorar tudo o que não está aqui.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, SmallInteger, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# As FKs da Pagila são ON UPDATE CASCADE ON DELETE RESTRICT. Se os modelos não
# disserem o mesmo, o autogenerate vê-as como diferentes e propõe recriá-las.
FK_OPTS = {"onupdate": "CASCADE", "ondelete": "RESTRICT"}


class Customer(Base):
    __tablename__ = "customer"

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int]
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(Text)
    create_date: Mapped[date]
    # Migração 0002
    loyalty_points: Mapped[int] = mapped_column(server_default=text("0"))

    rentals: Mapped[list["Rental"]] = relationship(back_populates="customer")


class Film(Base):
    __tablename__ = "film"

    film_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    rental_duration: Mapped[int] = mapped_column(SmallInteger)
    rental_rate: Mapped[Decimal] = mapped_column(Numeric(4, 2))

    inventory: Mapped[list["Inventory"]] = relationship(back_populates="film")


class Staff(Base):
    __tablename__ = "staff"

    staff_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    store_id: Mapped[int]
    active: Mapped[bool]


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("film.film_id", **FK_OPTS))
    store_id: Mapped[int]

    film: Mapped[Film] = relationship(back_populates="inventory")
    rentals: Mapped[list["Rental"]] = relationship(back_populates="inventory")


class Rental(Base):
    __tablename__ = "rental"
    __table_args__ = (
        # Migração 0003: no máximo um aluguer aberto por cópia
        Index(
            "rental_one_open_per_copy",
            "inventory_id",
            unique=True,
            postgresql_where=text("return_date IS NULL"),
        ),
    )

    rental_id: Mapped[int] = mapped_column(primary_key=True)
    rental_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.inventory_id", **FK_OPTS))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id", **FK_OPTS))
    return_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.staff_id", **FK_OPTS))

    customer: Mapped[Customer] = relationship(back_populates="rentals")
    inventory: Mapped[Inventory] = relationship(back_populates="rentals")
    staff: Mapped[Staff] = relationship()

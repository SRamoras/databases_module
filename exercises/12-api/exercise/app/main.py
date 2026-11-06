from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, func, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.db import get_session
from app.models import Customer, Film, Inventory, Rental

app = FastAPI(title="Exercício 12: alugueres")

MAX_ATTEMPTS = 3
OPEN_RENTAL_INDEX = "rental_one_open_per_copy"


# ---------- Corpos de pedido e de resposta ----------


class RentalIn(BaseModel):
    customer_id: int
    film_id: int
    store_id: int
    staff_id: int


class RentalCreated(BaseModel):
    rental_id: int
    inventory_id: int


class RentalReturned(BaseModel):
    rental_id: int
    return_date: datetime


class CustomerOut(BaseModel):
    customer_id: int
    first_name: str
    last_name: str


class FilmOut(BaseModel):
    film_id: int
    title: str


class OverdueRental(BaseModel):
    rental_id: int
    rental_date: datetime
    due_date: datetime
    customer: CustomerOut
    film: FilmOut


# ---------- Endpoints ----------


class NoCopyAvailable(Exception):
    pass


def _rent_once(session: Session, body: RentalIn) -> RentalCreated:
    """Uma tentativa, numa única transação."""
    with session.begin():
        if session.get(Customer, body.customer_id) is None:
            raise HTTPException(404, "Customer not found")
        if session.get(Film, body.film_id) is None:
            raise HTTPException(404, "Film not found")

        has_open_rental = exists().where(
            Rental.inventory_id == Inventory.inventory_id,
            Rental.return_date.is_(None),
        )
        # Uma cópia livre, trancada. skip_locked: se outro pedido já trancou uma
        # cópia, salta-a e tenta a seguinte em vez de ficar à espera.
        copy = session.scalars(
            select(Inventory)
            .where(
                Inventory.film_id == body.film_id,
                Inventory.store_id == body.store_id,
                ~has_open_rental,
            )
            .order_by(Inventory.inventory_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if copy is None:
            raise NoCopyAvailable

        rental = Rental(
            rental_date=func.now(),
            inventory_id=copy.inventory_id,
            customer_id=body.customer_id,
            staff_id=body.staff_id,
        )
        session.add(rental)
        session.flush()  # o INSERT corre aqui; uma violação do índice rebenta aqui
        return RentalCreated(rental_id=rental.rental_id, inventory_id=copy.inventory_id)


@app.post("/rentals", status_code=201, response_model=RentalCreated)
def create_rental(body: RentalIn, session: Session = Depends(get_session)):
    for _ in range(MAX_ATTEMPTS):
        try:
            return _rent_once(session, body)
        except NoCopyAvailable:
            raise HTTPException(409, "No copy available")
        except IntegrityError as exc:
            # Outro pedido alugou a mesma cópia entre a nossa leitura e o nosso
            # INSERT. O session.begin() já fez rollback: tenta-se tudo outra vez.
            if getattr(exc.orig.diag, "constraint_name", None) != OPEN_RENTAL_INDEX:
                raise
    raise HTTPException(409, "No copy available")


@app.post("/rentals/{rental_id}/return", response_model=RentalReturned)
def return_rental(rental_id: int, session: Session = Depends(get_session)):
    with session.begin():
        rental = session.scalars(
            select(Rental).where(Rental.rental_id == rental_id).with_for_update()
        ).one_or_none()
        if rental is None:
            raise HTTPException(404, "Rental not found")
        if rental.return_date is not None:
            raise HTTPException(409, "Rental already returned")
        rental.return_date = func.now()
        session.flush()
        session.refresh(rental, ["return_date"])
        return RentalReturned(rental_id=rental.rental_id, return_date=rental.return_date)


@app.get("/rentals/overdue", response_model=list[OverdueRental])
def overdue_rentals(as_of: date, session: Session = Depends(get_session)):
    due_date = Rental.rental_date + literal_column("interval '1 day'") * Film.rental_duration
    # Uma só consulta: os JOIN trazem o cliente e o filme, e contains_eager diz
    # ao ORM para preencher as relationships com essas colunas (sem N+1).
    stmt = (
        select(Rental, due_date.label("due_date"))
        .join(Rental.customer)
        .join(Rental.inventory)
        .join(Inventory.film)
        .where(Rental.return_date.is_(None), due_date < as_of)
        .options(
            contains_eager(Rental.customer),
            contains_eager(Rental.inventory).contains_eager(Inventory.film),
        )
        .order_by(Rental.rental_date, Rental.rental_id)
    )
    return [
        OverdueRental(
            rental_id=rental.rental_id,
            rental_date=rental.rental_date,
            due_date=due,
            customer=CustomerOut(
                customer_id=rental.customer.customer_id,
                first_name=rental.customer.first_name,
                last_name=rental.customer.last_name,
            ),
            film=FilmOut(film_id=rental.inventory.film.film_id, title=rental.inventory.film.title),
        )
        for rental, due in session.execute(stmt)
    ]

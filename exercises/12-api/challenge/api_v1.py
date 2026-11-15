"""Version 1 of the API: knows only the column customer.email.

    uv run uvicorn api_v1:app --port 8001
"""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from db import get_session


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customer"

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)


class EmailIn(BaseModel):
    email: str


class CustomerOut(BaseModel):
    version: int = 1
    customer_id: int
    first_name: str
    last_name: str
    email: str | None


app = FastAPI(title="Customers API v1 (email)")


def out(c: Customer) -> CustomerOut:
    return CustomerOut(
        customer_id=c.customer_id, first_name=c.first_name, last_name=c.last_name, email=c.email
    )


@app.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, session: Session = Depends(get_session)):
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return out(customer)


@app.put("/customers/{customer_id}/email", response_model=CustomerOut)
def change_email(customer_id: int, body: EmailIn, session: Session = Depends(get_session)):
    with session.begin():
        customer = session.get(Customer, customer_id, with_for_update=True)
        if customer is None:
            raise HTTPException(404, "Customer not found")
        customer.email = body.email
    return out(customer)

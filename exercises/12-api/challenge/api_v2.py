"""Version 2 of the API: knows only the column customer.email_address.

The JSON field is still called "email": renaming the column is an internal change,
and the clients of the API do not need to know about it.

    uv run uvicorn api_v2:app --port 8002
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
    email_address: Mapped[str | None] = mapped_column(Text)


class EmailIn(BaseModel):
    email: str


class CustomerOut(BaseModel):
    version: int = 2
    customer_id: int
    first_name: str
    last_name: str
    email: str | None


app = FastAPI(title="Customers API v2 (email_address)")


def out(c: Customer) -> CustomerOut:
    return CustomerOut(
        customer_id=c.customer_id,
        first_name=c.first_name,
        last_name=c.last_name,
        email=c.email_address,
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
        customer.email_address = body.email
    return out(customer)

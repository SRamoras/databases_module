"""expand: add customer.email_address and keep it in sync with customer.email

Revision ID: 0004
Revises: 0003_one_open_rental_per_copy
Create Date: 2026-11-15

First half of renaming customer.email to customer.email_address without downtime.
After this migration both columns exist and hold the same value, so version 1 of
the API (email) and version 2 (email_address) can run at the same time.

1. add email_address (nullable, like email)
2. a trigger that copies a change made to one column into the other (email_sync.py),
   created BEFORE the backfill, so a write from version 1 during the backfill is
   copied too
3. backfill email_address from email
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import email_sync

revision: str = "0004"
down_revision: str | None = "0003_one_open_rental_per_copy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("email_address", sa.Text(), nullable=True))
    op.execute(email_sync.CREATE_FUNCTION)
    op.execute(email_sync.CREATE_TRIGGER)
    # Backfill. On a large table this would run in batches (WHERE customer_id
    # BETWEEN ...), each in its own transaction, to avoid locking every row at once.
    op.execute("UPDATE customer SET email_address = email WHERE email_address IS DISTINCT FROM email")


def downgrade() -> None:
    op.execute(email_sync.DROP_TRIGGER)
    op.execute(email_sync.DROP_FUNCTION)
    op.drop_column("customer", "email_address")

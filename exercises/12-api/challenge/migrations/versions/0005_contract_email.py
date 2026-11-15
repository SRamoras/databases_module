"""contract: drop the sync trigger and customer.email

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15

Second half of the rename. Apply only after version 1 of the API has been stopped:
from here on, only email_address exists.

downgrade brings email back, filled from email_address, and the trigger with it,
so that version 1 can be started again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import email_sync

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(email_sync.DROP_TRIGGER)
    op.execute(email_sync.DROP_FUNCTION)
    op.drop_column("customer", "email")


def downgrade() -> None:
    op.add_column("customer", sa.Column("email", sa.Text(), nullable=True))
    op.execute(email_sync.CREATE_FUNCTION)
    op.execute(email_sync.CREATE_TRIGGER)
    op.execute("UPDATE customer SET email = email_address")

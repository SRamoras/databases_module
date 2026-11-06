"""customer.loyalty_points, preenchido com o número de alugueres

Revision ID: 0002_loyalty_points
Revises: 0001_baseline
Create Date: 2026-11-06

Uma coluna NOT NULL numa tabela com linhas não pode ser criada de uma vez sem
valor. Faz-se em três passos: criar nullable, preencher, pôr NOT NULL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_loyalty_points"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Coluna nullable, com o default 0 para as linhas novas
    op.add_column(
        "customer",
        sa.Column("loyalty_points", sa.Integer(), nullable=True, server_default=sa.text("0")),
    )
    # 2. Migração de dados: um ponto por aluguer
    op.execute(
        """
        UPDATE customer c
        SET loyalty_points = (SELECT count(*) FROM rental r WHERE r.customer_id = c.customer_id)
        """
    )
    # 3. Agora que todas as linhas têm valor, NOT NULL
    op.alter_column("customer", "loyalty_points", nullable=False)


def downgrade() -> None:
    op.drop_column("customer", "loyalty_points")

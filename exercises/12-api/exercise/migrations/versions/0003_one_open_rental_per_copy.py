"""no máximo um aluguer aberto por cópia

Revision ID: 0003_one_open_rental_per_copy
Revises: 0002_loyalty_points
Create Date: 2026-11-06

As cópias 1358, 1435 e 2408 têm dois alugueres abertos cada uma, o que impede
criar o índice único. Primeiro fecha-se o mais antigo de cada par com a data do
mais recente (a cópia teve de voltar à loja antes de ser alugada outra vez);
depois cria-se o índice único parcial.
"""

from alembic import op

revision = "0003_one_open_rental_per_copy"
down_revision = "0002_loyalty_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migração de dados: para cada cópia com mais de um aluguer aberto, fecha
    # todos menos o mais recente, com o rental_date do aluguer aberto seguinte.
    op.execute(
        """
        WITH open_rentals AS (
            SELECT rental_id,
                   lead(rental_date) OVER (
                       PARTITION BY inventory_id ORDER BY rental_date, rental_id
                   ) AS next_rental_date
            FROM rental
            WHERE return_date IS NULL
        )
        UPDATE rental r
        SET return_date = o.next_rental_date
        FROM open_rentals o
        WHERE r.rental_id = o.rental_id
          AND o.next_rental_date IS NOT NULL
        """
    )
    op.create_index(
        "rental_one_open_per_copy",
        "rental",
        ["inventory_id"],
        unique=True,
        postgresql_where="return_date IS NULL",
    )


def downgrade() -> None:
    # Só o índice. A correção dos dados não é desfeita (ver README).
    op.drop_index("rental_one_open_per_copy", table_name="rental")

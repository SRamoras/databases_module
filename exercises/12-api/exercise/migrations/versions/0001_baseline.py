"""baseline: o esquema da Pagila tal como já existe

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-06

A base de dados já existe (foi criada a partir da Pagila), por isso esta
migração não faz nada. Serve só de ponto de partida: corre-se
`alembic stamp head` para marcar a base de dados como estando nesta versão, e
todas as alterações seguintes são migrações por cima desta.
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

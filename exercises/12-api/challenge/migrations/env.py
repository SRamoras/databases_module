"""Alembic environment for the challenge.

The revisions 0001 to 0003 come from ../exercise/migrations/versions (see
version_locations in alembic.ini); 0004 and 0005 are in migrations/versions here.
These migrations are written by hand, so autogenerate is not used and there is no
target_metadata.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from db import database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

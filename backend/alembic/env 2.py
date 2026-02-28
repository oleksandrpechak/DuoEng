"""Alembic template env file.

This project currently uses SQL bootstrap migrations in `migrate.py`.
You can switch to managed Alembic revisions by wiring SQLAlchemy metadata here.
"""

from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    raise RuntimeError(
        "Online Alembic migrations are not configured yet. "
        "Use backend/migrate.py or extend this template."
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

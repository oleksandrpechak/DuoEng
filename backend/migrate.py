from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.db import check_db_connection, seed_from_dmklinger


def run_migrations() -> None:
    root = Path(__file__).resolve().parent
    alembic_cfg = Config(str(root / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    run_migrations()
    check_db_connection()
    seeded = seed_from_dmklinger()
    print(f"Migrations complete. Seeded words: {seeded}")

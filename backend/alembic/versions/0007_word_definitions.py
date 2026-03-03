"""add definition and example columns to words and dictionary_entries."""

from alembic import op
import sqlalchemy as sa


revision = "0007_word_definitions"
down_revision = "0006_custom_second_chance_ai"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Raw SQL check for column existence."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        return column_name in columns
    else:
        result = bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=:t AND column_name=:c AND table_schema='public'"
            ),
            {"t": table_name, "c": column_name},
        )
        return result.scalar() is not None


def upgrade() -> None:
    # words table
    if not _column_exists("words", "definition"):
        op.add_column("words", sa.Column("definition", sa.Text(), nullable=True, server_default=""))
    if not _column_exists("words", "example"):
        op.add_column("words", sa.Column("example", sa.Text(), nullable=True, server_default=""))

    # dictionary_entries table
    if not _column_exists("dictionary_entries", "definition"):
        op.add_column("dictionary_entries", sa.Column("definition", sa.Text(), nullable=True, server_default=""))
    if not _column_exists("dictionary_entries", "example"):
        op.add_column("dictionary_entries", sa.Column("example", sa.Text(), nullable=True, server_default=""))


def downgrade() -> None:
    if _column_exists("dictionary_entries", "example"):
        op.drop_column("dictionary_entries", "example")
    if _column_exists("dictionary_entries", "definition"):
        op.drop_column("dictionary_entries", "definition")
    if _column_exists("words", "example"):
        op.drop_column("words", "example")
    if _column_exists("words", "definition"):
        op.drop_column("words", "definition")

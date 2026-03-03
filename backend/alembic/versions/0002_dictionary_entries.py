"""add dictionary entries table."""

from alembic import op
import sqlalchemy as sa


revision = "0002_dictionary_entries"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        result = bind.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table_name},
        )
    else:
        result = bind.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_name=:t AND table_schema='public'"),
            {"t": table_name},
        )
    return result.scalar() is not None


def upgrade() -> None:
    if _table_exists("dictionary_entries"):
        return

    op.create_table(
        "dictionary_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ua_word", sa.Text(), nullable=False),
        sa.Column("en_word", sa.Text(), nullable=False),
        sa.Column("part_of_speech", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ua_word", "en_word", name="uq_dictionary_entries_ua_en"),
    )
    op.create_index("ix_dictionary_entries_ua_word", "dictionary_entries", ["ua_word"], unique=False)
    op.create_index("ix_dictionary_entries_en_word", "dictionary_entries", ["en_word"], unique=False)


def downgrade() -> None:
    if not _table_exists("dictionary_entries"):
        return
    op.drop_index("ix_dictionary_entries_en_word", table_name="dictionary_entries")
    op.drop_index("ix_dictionary_entries_ua_word", table_name="dictionary_entries")
    op.drop_table("dictionary_entries")

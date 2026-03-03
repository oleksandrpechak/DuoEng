"""expand CEFR levels for words, add word_level to rooms."""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "0004_cefr_room_level"
down_revision = "0003_oauth_match_idx"
branch_labels = None
depends_on = None

VALID_LEVELS = "('A1', 'A2', 'B1', 'B2', 'C1', 'C2')"


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    # -- words table: widen the level check constraint ----------------
    if bind.dialect.name != "sqlite":
        try:
            op.drop_constraint("ck_words_level", "words", type_="check")
        except Exception:
            pass
        op.create_check_constraint(
            "ck_words_level",
            "words",
            f"level IN {VALID_LEVELS}",
        )

    # -- rooms table: add word_level column ---------------------------
    if not _column_exists("rooms", "word_level"):
        op.add_column(
            "rooms",
            sa.Column("word_level", sa.String(2), nullable=False, server_default="B1"),
        )

        if bind.dialect.name != "sqlite":
            op.create_check_constraint(
                "ck_rooms_word_level",
                "rooms",
                f"word_level IN {VALID_LEVELS}",
            )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "sqlite":
        try:
            op.drop_constraint("ck_rooms_word_level", "rooms", type_="check")
        except Exception:
            pass

    if _column_exists("rooms", "word_level"):
        op.drop_column("rooms", "word_level")

    if bind.dialect.name != "sqlite":
        try:
            op.drop_constraint("ck_words_level", "words", type_="check")
        except Exception:
            pass
        op.create_check_constraint(
            "ck_words_level",
            "words",
            "level IN ('B1', 'B2')",
        )

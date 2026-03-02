"""expand CEFR levels for words, add word_level to rooms."""

from alembic import op
import sqlalchemy as sa


revision = "0004_cefr_levels_and_room_word_level"
down_revision = "0003_player_oauth_and_match_index"
branch_labels = None
depends_on = None

VALID_LEVELS = "('A1', 'A2', 'B1', 'B2', 'C1', 'C2')"


def upgrade() -> None:
    # -- words table: widen the level check constraint ----------------
    # SQLite doesn't support ALTER CONSTRAINT, but create_all already
    # uses the new model definition for fresh databases.  For Postgres:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("ck_words_level", "words", type_="check")
        op.create_check_constraint(
            "ck_words_level",
            "words",
            f"level IN {VALID_LEVELS}",
        )

    # -- rooms table: add word_level column ---------------------------
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
        op.drop_constraint("ck_rooms_word_level", "rooms", type_="check")

    op.drop_column("rooms", "word_level")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("ck_words_level", "words", type_="check")
        op.create_check_constraint(
            "ck_words_level",
            "words",
            "level IN ('B1', 'B2')",
        )

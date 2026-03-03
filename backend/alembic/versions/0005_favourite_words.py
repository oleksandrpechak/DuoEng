"""Add favourite_words table for per-player word bookmarks."""

from alembic import op
import sqlalchemy as sa


revision = "0005_favourite_words"
down_revision = "0004_cefr_room_level"
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
    if _table_exists("favourite_words"):
        return

    op.create_table(
        "favourite_words",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "player_id",
            sa.String(36),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "word_id",
            sa.String(64),
            sa.ForeignKey("words.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("player_id", "word_id", name="uq_favourite_words_player_word"),
    )

    op.create_index(
        "ix_favourite_words_player_id",
        "favourite_words",
        ["player_id"],
    )


def downgrade() -> None:
    if not _table_exists("favourite_words"):
        return
    op.drop_index("ix_favourite_words_player_id", table_name="favourite_words")
    op.drop_constraint("uq_favourite_words_player_word", "favourite_words", type_="unique")
    op.drop_table("favourite_words")

"""Add favourite_words table for per-player word bookmarks."""

from alembic import op
import sqlalchemy as sa


revision = "0005_favourite_words"
down_revision = "0004_cefr_room_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    )

    op.create_unique_constraint(
        "uq_favourite_words_player_word",
        "favourite_words",
        ["player_id", "word_id"],
    )
    op.create_index(
        "ix_favourite_words_player_id",
        "favourite_words",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_favourite_words_player_id", table_name="favourite_words")
    op.drop_constraint("uq_favourite_words_player_word", "favourite_words", type_="unique")
    op.drop_table("favourite_words")

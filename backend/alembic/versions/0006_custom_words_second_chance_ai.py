"""Add custom_words table, second_chance columns to rooms, ai_difficulty to rooms.

Revision ID: 0006_custom_words_second_chance_ai
Revises: 0005_favourite_words
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_custom_words_second_chance_ai"
down_revision = "0005_favourite_words"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Custom words table (Feature 9) ──
    op.create_table(
        "custom_words",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "player_id",
            sa.String(36),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ua_word", sa.Text, nullable=False),
        sa.Column("en_word", sa.Text, nullable=False),
        sa.Column("level", sa.String(2), nullable=False, server_default="B1"),
        sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_custom_words_player_ua_en",
        "custom_words",
        ["player_id", "ua_word", "en_word"],
    )
    op.create_index(
        "ix_custom_words_player_id",
        "custom_words",
        ["player_id"],
    )

    # ── Second-chance columns on rooms (Feature 7) ──
    op.add_column(
        "rooms",
        sa.Column("second_chance_player", sa.String(36), nullable=True),
    )
    op.add_column(
        "rooms",
        sa.Column("second_chance_expires", sa.DateTime(timezone=True), nullable=True),
    )

    # ── AI difficulty column on rooms (Feature 8) ──
    op.add_column(
        "rooms",
        sa.Column("ai_difficulty", sa.String(16), nullable=True),
    )

    # ── Update mode CHECK constraint to allow 'vs_ai' (Feature 8) ──
    # SQLite doesn't support ALTER CONSTRAINT, so we use batch_alter_table
    # For PostgreSQL: op.drop_constraint / op.create_check_constraint would work
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_constraint("ck_rooms_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_rooms_mode",
            "mode IN ('classic', 'challenge', 'vs_ai')",
        )


def downgrade() -> None:
    # ── Restore original mode constraint ──
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_constraint("ck_rooms_mode", type_="check")
        batch_op.create_check_constraint(
            "ck_rooms_mode",
            "mode IN ('classic', 'challenge')",
        )

    # ── Remove AI difficulty ──
    op.drop_column("rooms", "ai_difficulty")

    # ── Remove second-chance columns ──
    op.drop_column("rooms", "second_chance_expires")
    op.drop_column("rooms", "second_chance_player")

    # ── Remove custom_words table ──
    op.drop_index("ix_custom_words_player_id", table_name="custom_words")
    op.drop_constraint("uq_custom_words_player_ua_en", "custom_words", type_="unique")
    op.drop_table("custom_words")

"""Add custom_words table, second_chance columns to rooms, ai_difficulty to rooms.

Revision ID: 0006_custom_second_chance_ai
Revises: 0005_favourite_words
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_custom_second_chance_ai"
down_revision = "0005_favourite_words"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Raw SQL check — works reliably inside Alembic transactions on both PG and SQLite."""
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


def _column_exists(table_name: str, column_name: str) -> bool:
    """Raw SQL check for column existence."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        result = bind.execute(sa.text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
    else:
        result = bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=:t AND column_name=:c AND table_schema='public'"
            ),
            {"t": table_name, "c": column_name},
        )
        return result.scalar() is not None
    return column_name in columns


def upgrade() -> None:
    # ── Custom words table (Feature 9) ──
    if not _table_exists("custom_words"):
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
            sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("player_id", "ua_word", "en_word", name="uq_custom_words_player_ua_en"),
        )
        op.create_index(
            "ix_custom_words_player_id",
            "custom_words",
            ["player_id"],
        )

    # ── Second-chance columns on rooms (Feature 7) ──
    if not _column_exists("rooms", "second_chance_player"):
        op.add_column(
            "rooms",
            sa.Column("second_chance_player", sa.String(36), nullable=True),
        )
    if not _column_exists("rooms", "second_chance_expires"):
        op.add_column(
            "rooms",
            sa.Column("second_chance_expires", sa.DateTime(timezone=True), nullable=True),
        )

    # ── AI difficulty column on rooms (Feature 8) ──
    if not _column_exists("rooms", "ai_difficulty"):
        op.add_column(
            "rooms",
            sa.Column("ai_difficulty", sa.String(16), nullable=True),
        )

    # ── Update mode CHECK constraint to allow 'vs_ai' (Feature 8) ──
    # Only attempt constraint update if not already correct.
    # On PostgreSQL, drop+recreate. On SQLite, use batch_alter_table.
    try:
        with op.batch_alter_table("rooms") as batch_op:
            batch_op.drop_constraint("ck_rooms_mode", type_="check")
            batch_op.create_check_constraint(
                "ck_rooms_mode",
                "mode IN ('classic', 'challenge', 'vs_ai')",
            )
    except Exception:
        # Constraint may already be correct or not exist — safe to ignore
        pass


def downgrade() -> None:
    # ── Restore original mode constraint ──
    try:
        with op.batch_alter_table("rooms") as batch_op:
            batch_op.drop_constraint("ck_rooms_mode", type_="check")
            batch_op.create_check_constraint(
                "ck_rooms_mode",
                "mode IN ('classic', 'challenge')",
            )
    except Exception:
        pass

    # ── Remove AI difficulty ──
    if _column_exists("rooms", "ai_difficulty"):
        op.drop_column("rooms", "ai_difficulty")

    # ── Remove second-chance columns ──
    if _column_exists("rooms", "second_chance_expires"):
        op.drop_column("rooms", "second_chance_expires")
    if _column_exists("rooms", "second_chance_player"):
        op.drop_column("rooms", "second_chance_player")

    # ── Remove custom_words table ──
    if _table_exists("custom_words"):
        op.drop_index("ix_custom_words_player_id", table_name="custom_words")
        op.drop_constraint("uq_custom_words_player_ua_en", "custom_words", type_="unique")
        op.drop_table("custom_words")

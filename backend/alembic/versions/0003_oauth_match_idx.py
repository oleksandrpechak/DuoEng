"""add google_id and email to players, index on matches.started_at."""

from alembic import op
import sqlalchemy as sa


revision = "0003_oauth_match_idx"
down_revision = "0002_dictionary_entries"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
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


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        result = bind.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": index_name},
        )
    else:
        result = bind.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname=:n"),
            {"n": index_name},
        )
    return result.scalar() is not None


def upgrade() -> None:
    # Google OAuth columns
    if not _column_exists("players", "google_id"):
        op.add_column("players", sa.Column("google_id", sa.String(128), nullable=True))
    if not _column_exists("players", "email"):
        op.add_column("players", sa.Column("email", sa.String(256), nullable=True))
    if not _index_exists("ix_players_google_id"):
        op.create_index("ix_players_google_id", "players", ["google_id"], unique=True)
    if not _index_exists("ix_players_email"):
        op.create_index("ix_players_email", "players", ["email"], unique=True)

    # Leaderboard time-range queries
    if not _index_exists("ix_matches_started_at"):
        op.create_index("ix_matches_started_at", "matches", ["started_at"], unique=False)


def downgrade() -> None:
    if _index_exists("ix_matches_started_at"):
        op.drop_index("ix_matches_started_at", table_name="matches")
    if _index_exists("ix_players_email"):
        op.drop_index("ix_players_email", table_name="players")
    if _index_exists("ix_players_google_id"):
        op.drop_index("ix_players_google_id", table_name="players")
    if _column_exists("players", "email"):
        op.drop_column("players", "email")
    if _column_exists("players", "google_id"):
        op.drop_column("players", "google_id")

"""add google_id and email to players, index on matches.started_at."""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "0003_oauth_match_idx"
down_revision = "0002_dictionary_entries"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = [idx["name"] for idx in insp.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # Google OAuth columns
    if not _column_exists("players", "google_id"):
        op.add_column("players", sa.Column("google_id", sa.String(128), nullable=True))
    if not _column_exists("players", "email"):
        op.add_column("players", sa.Column("email", sa.String(256), nullable=True))
    if not _index_exists("players", "ix_players_google_id"):
        op.create_index("ix_players_google_id", "players", ["google_id"], unique=True)
    if not _index_exists("players", "ix_players_email"):
        op.create_index("ix_players_email", "players", ["email"], unique=True)

    # Leaderboard time-range queries
    if not _index_exists("matches", "ix_matches_started_at"):
        op.create_index("ix_matches_started_at", "matches", ["started_at"], unique=False)


def downgrade() -> None:
    if _index_exists("matches", "ix_matches_started_at"):
        op.drop_index("ix_matches_started_at", table_name="matches")
    if _index_exists("players", "ix_players_email"):
        op.drop_index("ix_players_email", table_name="players")
    if _index_exists("players", "ix_players_google_id"):
        op.drop_index("ix_players_google_id", table_name="players")
    if _column_exists("players", "email"):
        op.drop_column("players", "email")
    if _column_exists("players", "google_id"):
        op.drop_column("players", "google_id")

"""add google_id and email to players, index on matches.started_at."""

from alembic import op
import sqlalchemy as sa


revision = "0003_oauth_match_idx"
down_revision = "0002_dictionary_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Google OAuth columns
    op.add_column("players", sa.Column("google_id", sa.String(128), nullable=True))
    op.add_column("players", sa.Column("email", sa.String(256), nullable=True))
    op.create_index("ix_players_google_id", "players", ["google_id"], unique=True)
    op.create_index("ix_players_email", "players", ["email"], unique=True)

    # Leaderboard time-range queries
    op.create_index("ix_matches_started_at", "matches", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_matches_started_at", table_name="matches")
    op.drop_index("ix_players_email", table_name="players")
    op.drop_index("ix_players_google_id", table_name="players")
    op.drop_column("players", "email")
    op.drop_column("players", "google_id")

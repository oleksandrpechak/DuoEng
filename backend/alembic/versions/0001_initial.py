"""initial schema for gameplay, stats, and llm cache."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=False),
        sa.Column("elo", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_games", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_response_time", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_moves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nickname"),
    )
    op.create_index("ix_players_elo", "players", ["elo"], unique=False)

    op.create_table(
        "rooms",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_turn", sa.String(length=36), nullable=True),
        sa.Column("turn_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("target_score", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("turn_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_word_ua", sa.Text(), nullable=True),
        sa.Column("current_word_en", sa.Text(), nullable=True),
        sa.Column("match_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint("mode IN ('classic', 'challenge')", name="ck_rooms_mode"),
        sa.CheckConstraint("status IN ('waiting', 'playing', 'finished')", name="ck_rooms_status"),
        sa.ForeignKeyConstraint(["current_turn"], ["players.id"]),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "room_players",
        sa.Column("room_code", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("player_order", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_code"], ["rooms.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("room_code", "player_id"),
    )
    op.create_index("ix_room_players_player_id", "room_players", ["player_id"], unique=False)
    op.create_index("ix_room_players_room_code", "room_players", ["room_code"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_code", sa.String(length=16), nullable=False),
        sa.Column("player_a", sa.String(length=36), nullable=False),
        sa.Column("player_b", sa.String(length=36), nullable=False),
        sa.Column("winner_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["player_a"], ["players.id"]),
        sa.ForeignKeyConstraint(["player_b"], ["players.id"]),
        sa.ForeignKeyConstraint(["room_code"], ["rooms.code"]),
        sa.ForeignKeyConstraint(["winner_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_room_code", "matches", ["room_code"], unique=False)

    op.create_table(
        "moves",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("match_id", sa.String(length=36), nullable=False),
        sa.Column("room_code", sa.String(length=16), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("ua_word", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("score_awarded", sa.Integer(), nullable=False),
        sa.Column("response_time", sa.Float(), nullable=False),
        sa.Column("scoring_source", sa.String(length=32), nullable=False),
        sa.Column("is_timeout", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["room_code"], ["rooms.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "turn_number", name="uq_moves_match_turn"),
    )
    op.create_index("ix_moves_match_id", "moves", ["match_id"], unique=False)
    op.create_index("ix_moves_player_id", "moves", ["player_id"], unique=False)
    op.create_index("ix_moves_room_code", "moves", ["room_code"], unique=False)

    op.create_table(
        "words",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("ua", sa.Text(), nullable=False),
        sa.Column("en", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.CheckConstraint("level IN ('B1', 'B2')", name="ck_words_level"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entity_type IN ('player', 'ip')", name="ck_bans_entity_type"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bans_entity_lookup",
        "bans",
        ["entity_type", "entity_id", "banned_until"],
        unique=False,
    )

    op.create_table(
        "llm_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )


def downgrade() -> None:
    op.drop_table("llm_cache")
    op.drop_index("ix_bans_entity_lookup", table_name="bans")
    op.drop_table("bans")
    op.drop_table("words")
    op.drop_index("ix_moves_room_code", table_name="moves")
    op.drop_index("ix_moves_player_id", table_name="moves")
    op.drop_index("ix_moves_match_id", table_name="moves")
    op.drop_table("moves")
    op.drop_index("ix_matches_room_code", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_room_players_room_code", table_name="room_players")
    op.drop_index("ix_room_players_player_id", table_name="room_players")
    op.drop_table("room_players")
    op.drop_table("rooms")
    op.drop_index("ix_players_elo", table_name="players")
    op.drop_table("players")

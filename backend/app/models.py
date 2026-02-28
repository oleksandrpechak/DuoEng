from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (Index("ix_players_elo", "elo"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    elo: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_response_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_moves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("status IN ('waiting', 'playing', 'finished')", name="ck_rooms_status"),
        CheckConstraint("mode IN ('classic', 'challenge')", name="ck_rooms_mode"),
    )

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting")
    current_turn: Mapped[str | None] = mapped_column(String(36), ForeignKey("players.id"), nullable=True)
    turn_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="classic")
    target_score: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_word_ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_word_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class RoomPlayer(Base):
    __tablename__ = "room_players"
    __table_args__ = (
        Index("ix_room_players_room_code", "room_code"),
        Index("ix_room_players_player_id", "player_id"),
    )

    room_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("rooms.code", ondelete="CASCADE"),
        primary_key=True,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("players.id", ondelete="CASCADE"),
        primary_key=True,
    )
    player_order: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (Index("ix_matches_room_code", "room_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_code: Mapped[str] = mapped_column(String(16), ForeignKey("rooms.code"), nullable=False)
    player_a: Mapped[str] = mapped_column(String(36), ForeignKey("players.id"), nullable=False)
    player_b: Mapped[str] = mapped_column(String(36), ForeignKey("players.id"), nullable=False)
    winner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("players.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (
        UniqueConstraint("match_id", "turn_number", name="uq_moves_match_turn"),
        Index("ix_moves_match_id", "match_id"),
        Index("ix_moves_player_id", "player_id"),
        Index("ix_moves_room_code", "room_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_id: Mapped[str] = mapped_column(String(36), ForeignKey("matches.id"), nullable=False)
    room_code: Mapped[str] = mapped_column(String(16), ForeignKey("rooms.code"), nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str] = mapped_column(String(36), ForeignKey("players.id"), nullable=False)
    ua_word: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_source: Mapped[str] = mapped_column(String(32), nullable=False)
    is_timeout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (CheckConstraint("level IN ('B1', 'B2')", name="ck_words_level"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ua: Mapped[str] = mapped_column(Text, nullable=False)
    en: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(2), nullable=False)


class Ban(Base):
    __tablename__ = "bans"
    __table_args__ = (
        CheckConstraint("entity_type IN ('player', 'ip')", name="ck_bans_entity_type"),
        Index("ix_bans_entity_lookup", "entity_type", "entity_id", "banned_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    banned_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LLMCache(Base):
    __tablename__ = "llm_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"
    __table_args__ = (
        UniqueConstraint("ua_word", "en_word", name="uq_dictionary_entries_ua_en"),
        Index("ix_dictionary_entries_ua_word", "ua_word"),
        Index("ix_dictionary_entries_en_word", "en_word"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ua_word: Mapped[str] = mapped_column(Text, nullable=False)
    en_word: Mapped[str] = mapped_column(Text, nullable=False)
    part_of_speech: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

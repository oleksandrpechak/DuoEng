from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Iterator

from .config import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                id TEXT PRIMARY KEY,
                nickname TEXT UNIQUE NOT NULL,
                elo INTEGER NOT NULL DEFAULT 1000,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                total_games INTEGER NOT NULL DEFAULT 0,
                total_response_time REAL NOT NULL DEFAULT 0,
                total_moves INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('waiting', 'playing', 'finished')),
                current_turn TEXT,
                turn_started_at TEXT,
                mode TEXT NOT NULL CHECK(mode IN ('classic', 'challenge')),
                target_score INTEGER NOT NULL DEFAULT 10,
                turn_number INTEGER NOT NULL DEFAULT 0,
                current_word_ua TEXT,
                current_word_en TEXT,
                match_id TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS room_players (
                room_code TEXT NOT NULL,
                player_id TEXT NOT NULL,
                player_order INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (room_code, player_id),
                FOREIGN KEY (room_code) REFERENCES rooms(code) ON DELETE CASCADE,
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_room_players_room ON room_players(room_code)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY,
                room_code TEXT NOT NULL,
                player_a TEXT NOT NULL,
                player_b TEXT NOT NULL,
                winner_id TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY (room_code) REFERENCES rooms(code),
                FOREIGN KEY (player_a) REFERENCES players(id),
                FOREIGN KEY (player_b) REFERENCES players(id),
                FOREIGN KEY (winner_id) REFERENCES players(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS moves (
                id TEXT PRIMARY KEY,
                match_id TEXT NOT NULL,
                room_code TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                ua_word TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                score_awarded INTEGER NOT NULL,
                response_time REAL NOT NULL,
                scoring_source TEXT NOT NULL,
                is_timeout INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE (match_id, turn_number),
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (room_code) REFERENCES rooms(code),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_moves_match_turn ON moves(match_id, turn_number)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                id TEXT PRIMARY KEY,
                ua TEXT NOT NULL,
                en TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('B1', 'B2'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL CHECK(entity_type IN ('player', 'ip')),
                entity_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                banned_until TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bans_entity
            ON bans(entity_type, entity_id, banned_until)
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                score INTEGER NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )


def seed_sample_words_if_empty() -> int:
    sample_words = [
        ("привіт", "hello", "B1"),
        ("дякую", "thank you", "B1"),
        ("будь ласка", "please", "B1"),
        ("добрий ранок", "good morning", "B1"),
        ("на добраніч", "good night", "B1"),
        ("так", "yes", "B1"),
        ("ні", "no", "B1"),
        ("вода", "water", "B1"),
        ("хліб", "bread", "B1"),
        ("молоко", "milk", "B1"),
        ("яблуко", "apple", "B1"),
        ("книга", "book", "B1"),
        ("стіл", "table", "B1"),
        ("стілець", "chair", "B1"),
        ("вікно", "window", "B1"),
        ("двері", "door", "B1"),
        ("будинок", "house", "B1"),
        ("машина", "car", "B1"),
        ("собака", "dog", "B1"),
        ("кіт", "cat", "B1"),
        ("друг", "friend", "B1"),
        ("сім'я", "family", "B1"),
        ("любов", "love", "B1"),
        ("час", "time", "B1"),
        ("день", "day", "B1"),
        ("незважаючи на", "despite", "B2"),
        ("однак", "however", "B2"),
        ("отже", "therefore", "B2"),
        ("насправді", "actually", "B2"),
        ("очевидно", "obviously", "B2"),
        ("можливо", "perhaps", "B2"),
        ("зрештою", "eventually", "B2"),
        ("здебільшого", "mostly", "B2"),
        ("зазвичай", "usually", "B2"),
        ("визначати", "determine", "B2"),
        ("досягати", "achieve", "B2"),
        ("впливати", "influence", "B2"),
        ("порівнювати", "compare", "B2"),
        ("враження", "impression", "B2"),
        ("досвід", "experience", "B2"),
        ("середовище", "environment", "B2"),
        ("розвиток", "development", "B2"),
        ("суспільство", "society", "B2"),
        ("уряд", "government", "B2"),
        ("економіка", "economy", "B2"),
        ("культура", "culture", "B2"),
        ("освіта", "education", "B2"),
        ("наука", "science", "B2"),
        ("технологія", "technology", "B2"),
        ("здоров'я", "health", "B2"),
    ]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM words")
        count = cursor.fetchone()["cnt"]
        if count > 0:
            return 0

        for idx, (ua, en, level) in enumerate(sample_words, start=1):
            cursor.execute(
                "INSERT INTO words (id, ua, en, level) VALUES (?, ?, ?, ?)",
                (f"seed-{idx:03d}", ua, en, level),
            )

    return len(sample_words)


def clear_expired_llm_cache() -> None:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM llm_cache WHERE expires_at <= ?",
            (_utc_now(),),
        )

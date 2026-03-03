"""
AI Player for vs-AI game mode.

Simulates an opponent with configurable difficulty levels.
"""
from __future__ import annotations

import asyncio
import logging
import random
import string

from sqlalchemy import text

from .db import get_db

logger = logging.getLogger("duoeng.ai_player")

# Fixed AI player IDs
AI_PLAYER_IDS = {
    "easy": "ai_easy",
    "medium": "ai_medium",
    "hard": "ai_hard",
}

AI_NICKNAMES = {
    "easy": "🤖 AI (Easy)",
    "medium": "🤖 AI (Medium)",
    "hard": "🤖 AI (Hard)",
}

DIFFICULTY_SETTINGS = {
    "easy": {"correct_rate": 0.40, "response_delay": (3.0, 6.0), "typo_rate": 0.3},
    "medium": {"correct_rate": 0.65, "response_delay": (2.0, 4.0), "typo_rate": 0.1},
    "hard": {"correct_rate": 0.90, "response_delay": (1.0, 2.5), "typo_rate": 0.0},
}


def ensure_ai_players_exist() -> None:
    """Create AI player rows in the DB if they don't exist. Called at startup."""
    with get_db() as session:
        for difficulty, player_id in AI_PLAYER_IDS.items():
            existing = session.execute(
                text("SELECT id FROM players WHERE id = :id"),
                {"id": player_id},
            ).mappings().first()
            if not existing:
                nickname = AI_NICKNAMES[difficulty]
                session.execute(
                    text(
                        """
                        INSERT INTO players (
                            id, nickname, elo, wins, losses,
                            total_games, total_response_time, total_moves, created_at
                        )
                        VALUES (
                            :id, :nickname, :elo, 0, 0, 0, 0.0, 0, :created_at
                        )
                        """
                    ),
                    {
                        "id": player_id,
                        "nickname": nickname,
                        "elo": {"easy": 800, "medium": 1000, "hard": 1200}[difficulty],
                        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    },
                )
                logger.info("Created AI player: %s (%s)", nickname, player_id)


def introduce_typo(word: str) -> str:
    """Introduce a single random typo into a word."""
    if len(word) < 3:
        return word
    i = random.randint(1, len(word) - 2)
    chars = list(word)
    chars[i] = random.choice(string.ascii_lowercase)
    return "".join(chars)


def get_random_wrong_answer(ua_word: str) -> str:
    """Pick a random wrong English word from the dictionary."""
    with get_db() as session:
        row = session.execute(
            text(
                "SELECT en_word FROM dictionary_entries "
                "WHERE LOWER(ua_word) != :ua "
                "ORDER BY RANDOM() LIMIT 1"
            ),
            {"ua": ua_word.strip().lower()},
        ).mappings().first()
    if row:
        return row["en_word"]
    return "unknown"


async def make_ai_move(ua_word: str, en_word: str, difficulty: str) -> str:
    """Simulate an AI player making a move.

    Returns the AI's answer string after a simulated delay.
    """
    diff = difficulty.lower()
    if diff not in DIFFICULTY_SETTINGS:
        diff = "medium"

    conf = DIFFICULTY_SETTINGS[diff]

    # Simulate thinking time
    delay = random.uniform(*conf["response_delay"])
    await asyncio.sleep(delay)

    # Decide if AI answers correctly
    if random.random() < conf["correct_rate"]:
        answer = en_word  # Correct answer
        # Add typos for lower difficulties
        if conf["typo_rate"] > 0 and random.random() < conf["typo_rate"]:
            answer = introduce_typo(answer)
    else:
        # Wrong answer — pick random word from dictionary
        answer = get_random_wrong_answer(ua_word)

    return answer


def is_ai_player(player_id: str) -> bool:
    """Check if a player_id belongs to an AI player."""
    return player_id in AI_PLAYER_IDS.values()


def get_ai_difficulty(player_id: str) -> str | None:
    """Get difficulty string from AI player ID."""
    for diff, pid in AI_PLAYER_IDS.items():
        if pid == player_id:
            return diff
    return None

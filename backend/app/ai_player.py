"""
AI Player for vs-AI game mode.

Simulates an opponent with configurable difficulty levels.
All responses are instant — no delays, no DB lookups for wrong answers.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

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

# Probability of getting 2 pts, 1 pt, or 0 pts per difficulty
AI_CONFIG = {
    "easy":   {"correct_rate": 0.35, "partial_rate": 0.15},
    "medium": {"correct_rate": 0.60, "partial_rate": 0.20},
    "hard":   {"correct_rate": 0.85, "partial_rate": 0.10},
}


def ensure_ai_players_exist() -> None:
    """Create AI player rows in the DB if they don't exist. Called at startup."""
    now = datetime.now(timezone.utc)
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
                        "created_at": now,
                    },
                )
                logger.info("Created AI player: %s (%s)", nickname, player_id)


def simulate_ai_score(correct_word: str, difficulty: str = "medium") -> tuple[int, str]:
    """Instantly determine AI score and answer. No delays, no DB calls."""
    config = AI_CONFIG.get(difficulty, AI_CONFIG["medium"])
    roll = random.random()
    if roll < config["correct_rate"]:
        return 2, correct_word
    elif roll < config["correct_rate"] + config["partial_rate"]:
        # Partial — swap two adjacent chars
        answer = _slightly_wrong(correct_word)
        return 1, answer
    else:
        return 0, _random_wrong_word()


def _slightly_wrong(word: str) -> str:
    if len(word) <= 2:
        return word + "s"
    chars = list(word)
    i = random.randint(0, len(chars) - 2)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


_WRONG_POOL = [
    "apple", "house", "water", "green", "table",
    "stone", "black", "music", "light", "place",
    "money", "power", "space", "paper", "heart",
]


def _random_wrong_word() -> str:
    return random.choice(_WRONG_POOL)


def is_ai_player(player_id: str) -> bool:
    """Check if a player_id belongs to an AI player."""
    return player_id in AI_PLAYER_IDS.values()


def get_ai_difficulty(player_id: str) -> str | None:
    """Get difficulty string from AI player ID."""
    for diff, pid in AI_PLAYER_IDS.items():
        if pid == player_id:
            return diff
    return None

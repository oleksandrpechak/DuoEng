"""
AI Player for vs-AI game mode.

Simulates an opponent with configurable difficulty levels.
"""
from __future__ import annotations

import asyncio
import logging
import random
import string
import uuid

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
    "easy": {"correct_rate": 0.40, "response_delay": (0.5, 1.5), "typo_rate": 0.3},
    "medium": {"correct_rate": 0.65, "response_delay": (0.5, 1.5), "typo_rate": 0.1},
    "hard": {"correct_rate": 0.90, "response_delay": (0.5, 1.5), "typo_rate": 0.0},
}

AI_CONFIG = {
    "easy":   {"correct_rate": 0.35, "partial_rate": 0.15},
    "medium": {"correct_rate": 0.60, "partial_rate": 0.20},
    "hard":   {"correct_rate": 0.85, "partial_rate": 0.10},
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


def simulate_ai_score(correct_word: str, difficulty: str = "medium") -> tuple[int, str]:
    config = AI_CONFIG.get(difficulty, AI_CONFIG["medium"])
    roll = random.random()
    if roll < config["correct_rate"]:
        return 2, correct_word
    elif roll < config["correct_rate"] + config["partial_rate"]:
        wrong = _slightly_wrong(correct_word)
        return 1, wrong
    else:
        return 0, _random_wrong_word()


def _slightly_wrong(word: str) -> str:
    if len(word) <= 2:
        return word + "s"
    chars = list(word)
    i = random.randint(0, len(chars)-2)
    chars[i], chars[i+1] = chars[i+1], chars[i]
    return ''.join(chars)


def _random_wrong_word() -> str:
    wrong_pool = [
        "apple", "house", "water", "green", "table",
        "stone", "black", "music", "light", "place",
        "money", "power", "space", "paper", "heart",
    ]
    return random.choice(wrong_pool)


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


async def take_ai_turn(
    room_code: str,
    current_word: dict,
    difficulty: str,
    broadcast_fn,
    ai_player_id: str,
) -> None:
    correct_en = current_word.get("en", "")
    delays = {"easy": 2.0, "medium": 1.2, "hard": 0.6}
    delay = delays.get(difficulty, 1.0) + random.uniform(-0.2, 0.4)
    await asyncio.sleep(max(0.3, delay))
    score, ai_answer = simulate_ai_score(correct_en, difficulty)
    with get_db() as session:
        # Fetch match_id from rooms table
        row = session.execute(text("SELECT match_id FROM rooms WHERE code = :code"), {"code": room_code}).mappings().first()
        match_id = row["match_id"] if row else None
        if score > 0:
            session.execute(text("""
                UPDATE players 
                SET total_score = total_score + :score
                WHERE id = :player_id
            """), {"score": score, "player_id": ai_player_id})
        session.execute(text("""
            INSERT INTO moves 
                (id, match_id, room_code, player_id, word_id, 
                 player_answer, correct_answer, score_awarded,
                 response_time, scoring_source, is_timeout, created_at)
            VALUES 
                (:id, :match_id, :room_code, :player_id, :word_id,
                 :answer, :correct, :score,
                 :response_time, 'local', false, NOW())
        """), {
            "id": str(uuid.uuid4()),
            "match_id": match_id,
            "room_code": room_code,
            "player_id": ai_player_id,
            "word_id": current_word.get("id", ""),
            "answer": ai_answer,
            "correct": correct_en,
            "score": score,
            "response_time": delay,
        })
    await broadcast_fn(room_code, {
        "type": "ai_answer",
        "player_id": ai_player_id,
        "answer": ai_answer,
        "score": score,
        "correct_answer": correct_en,
    })


def is_ai_player(player_id: str) -> bool:
    """Check if a player_id belongs to an AI player."""
    return player_id in AI_PLAYER_IDS.values()


def get_ai_difficulty(player_id: str) -> str | None:
    """Get difficulty string from AI player ID."""
    for diff, pid in AI_PLAYER_IDS.items():
        if pid == player_id:
            return diff
    return None

"""
Admin service for CEFR level re-evaluation using AI.

Provides batch re-evaluation of words that have a default B1 level.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import text

from ..db import get_db

logger = logging.getLogger("duoeng.admin")


async def assign_cefr_level(en_word: str, ua_word: str) -> str:
    """Use AI to assign a CEFR level to a word pair."""
    from ..services.gemini_service import GeminiServiceError, generate_text

    prompt = (
        "Rate the CEFR difficulty of this vocabulary word for an English learner.\n"
        f'English word: "{en_word}" (Ukrainian: "{ua_word}")\n'
        "Reply with ONLY one of: A1, A2, B1, B2, C1, C2\n"
        "Base your answer on how common and simple this word is."
    )
    try:
        result = await asyncio.wait_for(generate_text(prompt), timeout=5.0)
        level = result.strip().upper()
        if level in ("A1", "A2", "B1", "B2", "C1", "C2"):
            return level
    except asyncio.TimeoutError:
        logger.warning("CEFR level AI timeout for %s", en_word)
    except GeminiServiceError:
        logger.warning("CEFR level AI error for %s", en_word)
    except Exception:
        logger.exception("CEFR level AI unexpected error for %s", en_word)
    return "B1"


async def evaluate_word_levels(batch_size: int = 50, max_words: Optional[int] = None) -> dict:
    """Re-evaluate CEFR levels for words currently at B1 (likely defaulted).

    Processes in batches with rate limiting.
    Returns summary stats.
    """
    with get_db() as session:
        query = "SELECT id, ua, en, level FROM words WHERE level = 'B1'"
        if max_words:
            query += f" LIMIT {max_words}"
        rows = session.execute(text(query)).mappings().all()

    if not rows:
        return {"total": 0, "updated": 0, "unchanged": 0, "errors": 0}

    total = len(rows)
    updated = 0
    unchanged = 0
    errors = 0

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        tasks = []
        for row in batch:
            tasks.append(_evaluate_single(row["id"], row["en"], row["ua"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for row_data, result in zip(batch, results):
            if isinstance(result, Exception):
                errors += 1
                continue
            word_id, new_level = result
            if new_level != "B1":
                with get_db() as session:
                    session.execute(
                        text("UPDATE words SET level = :level WHERE id = :id"),
                        {"level": new_level, "id": word_id},
                    )
                updated += 1
            else:
                unchanged += 1

        # Rate limiting between batches
        if i + batch_size < total:
            await asyncio.sleep(1.0)

    logger.info(
        "CEFR re-evaluation complete",
        extra={
            "event": "cefr_evaluation_done",
            "total": total,
            "updated": updated,
            "unchanged": unchanged,
            "errors": errors,
        },
    )

    return {
        "total": total,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
    }


async def _evaluate_single(word_id: str, en_word: str, ua_word: str) -> tuple[str, str]:
    """Evaluate a single word and return (word_id, new_level)."""
    new_level = await assign_cefr_level(en_word, ua_word)
    return word_id, new_level

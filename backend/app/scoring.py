from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover - handled via fallback scoring
    aiohttp = None

from sqlalchemy import text

from .config import settings
from .db import get_db
from .metrics import LLM_CALLS_TOTAL, LLM_TIMEOUTS_TOTAL

logger = logging.getLogger("duoeng.scoring")


@dataclass(frozen=True)
class ScoreResult:
    score: int
    source: str
    used_llm: bool


class LLMScorer:
    """LLM scoring with timeout, cache, and fallback matching."""

    def __init__(self) -> None:
        self._memory_cache: dict[str, tuple[float, ScoreResult]] = {}
        self._synonyms = {
            "hello": {"hi", "hey"},
            "car": {"automobile", "vehicle"},
            "house": {"home"},
            "friend": {"mate", "buddy"},
            "dog": {"puppy", "hound"},
            "cat": {"kitty", "kitten"},
            "thank you": {"thanks", "thx"},
            "good morning": {"morning"},
            "good night": {"night"},
        }

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())

    def _cache_key(self, correct_answer: str, user_answer: str) -> str:
        normalized = f"{self._normalize(correct_answer)}::{self._normalize(user_answer)}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load_cached(self, key: str) -> Optional[ScoreResult]:
        now_ts = datetime.now(timezone.utc).timestamp()

        cached = self._memory_cache.get(key)
        if cached and cached[0] > now_ts:
            return cached[1]

        with get_db() as session:
            row = session.execute(
                text("SELECT score, source, expires_at FROM llm_cache WHERE cache_key = :cache_key"),
                {"cache_key": key},
            ).mappings().first()

        if not row:
            return None

        expires_raw = row["expires_at"]
        if isinstance(expires_raw, datetime):
            expires_at = expires_raw.timestamp()
        else:
            expires_at = datetime.fromisoformat(expires_raw).timestamp()
        if expires_at <= now_ts:
            return None

        result = ScoreResult(score=row["score"], source=row["source"], used_llm=row["source"] == "llm")
        self._memory_cache[key] = (expires_at, result)
        return result

    def _store_cached(self, key: str, result: ScoreResult) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.llm_cache_ttl_seconds)
        self._memory_cache[key] = (expires_at.timestamp(), result)

        with get_db() as session:
            session.execute(
                text(
                    """
                    INSERT INTO llm_cache (cache_key, score, source, created_at, expires_at)
                    VALUES (:cache_key, :score, :source, :created_at, :expires_at)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        score = EXCLUDED.score,
                        source = EXCLUDED.source,
                        created_at = EXCLUDED.created_at,
                        expires_at = EXCLUDED.expires_at
                    """
                ),
                {
                    "cache_key": key,
                    "score": result.score,
                    "source": result.source,
                    "created_at": datetime.now(timezone.utc),
                    "expires_at": expires_at,
                },
            )

    def _quick_match(self, correct_answer: str, user_answer: str) -> Optional[ScoreResult]:
        correct = self._normalize(correct_answer)
        answer = self._normalize(user_answer)

        if answer == correct:
            return ScoreResult(score=2, source="fallback_exact", used_llm=False)

        if answer in self._synonyms.get(correct, set()) or correct in self._synonyms.get(answer, set()):
            return ScoreResult(score=2, source="fallback_synonym", used_llm=False)

        if correct and correct in answer and len(answer) > len(correct):
            return ScoreResult(score=1, source="fallback_contains", used_llm=False)

        return None

    def _semantic_lite(self, correct_answer: str, user_answer: str) -> ScoreResult:
        correct_tokens = set(self._normalize(correct_answer).split())
        answer_tokens = set(self._normalize(user_answer).split())
        if not correct_tokens or not answer_tokens:
            return ScoreResult(score=0, source="fallback_semantic_lite", used_llm=False)

        intersection = len(correct_tokens & answer_tokens)
        union = len(correct_tokens | answer_tokens)
        jaccard = intersection / union
        if jaccard >= 0.5:
            return ScoreResult(score=1, source="fallback_semantic_lite", used_llm=False)
        return ScoreResult(score=0, source="fallback_semantic_lite", used_llm=False)

    async def _call_llm(self, correct_answer: str, user_answer: str) -> Optional[ScoreResult]:
        if not settings.enable_llm_scoring or not settings.llm_api_url:
            return None
        if aiohttp is None:
            return None

        payload = {
            "prompt": (
                "Score translation quality from 0 to 2. "
                "0=wrong, 1=partial, 2=correct. "
                f"Correct answer: {correct_answer}. User answer: {user_answer}."
            ),
            "correct_answer": correct_answer,
            "user_answer": user_answer,
        }
        headers = {}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        timeout = aiohttp.ClientTimeout(total=settings.llm_timeout)
        LLM_CALLS_TOTAL.inc()

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(settings.llm_api_url, json=payload, headers=headers) as response:
                    if response.status >= 400:
                        return None
                    data = await response.json(content_type=None)
        except asyncio.TimeoutError:
            LLM_TIMEOUTS_TOTAL.inc()
            logger.warning("LLM timeout", extra={"event": "llm_timeout"})
            return None
        except Exception:
            logger.exception("LLM call failed", extra={"event": "llm_call_failed"})
            return None

        score = data.get("score") if isinstance(data, dict) else None
        if score is None and isinstance(data, dict):
            score = data.get("result", {}).get("score")

        try:
            score_value = int(score)
        except (TypeError, ValueError):
            return None

        score_value = max(0, min(2, score_value))
        return ScoreResult(score=score_value, source="llm", used_llm=True)

    async def score(self, correct_answer: str, user_answer: str) -> ScoreResult:
        key = self._cache_key(correct_answer, user_answer)
        cached = self._load_cached(key)
        if cached:
            return cached

        quick = self._quick_match(correct_answer, user_answer)
        if quick:
            self._store_cached(key, quick)
            return quick

        llm_result = await self._call_llm(correct_answer, user_answer)
        if llm_result:
            self._store_cached(key, llm_result)
            return llm_result

        fallback = self._semantic_lite(correct_answer, user_answer)
        self._store_cached(key, fallback)
        return fallback

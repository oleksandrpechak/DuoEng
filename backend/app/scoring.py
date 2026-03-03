from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import hashlib
import logging
import re
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

# Hard timeout for LLM calls (seconds)
LLM_HARD_TIMEOUT = 4.0


@dataclass(frozen=True)
class ScoreResult:
    score: int
    source: str
    used_llm: bool


class LLMScorer:
    """LLM scoring with timeout, cache, dictionary-first lookup, and fallback matching.

    Scoring pipeline for description mode:
      1. Check LLM cache (instant)
      2. Check local dictionary (fast DB lookup, ~5ms)
      3. AI fallback only if word not in dictionary (slower, ~2-4s)
    """

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

    @staticmethod
    def _sanitize_for_llm(text: str, max_length: int = 200) -> str:
        """Strip dangerous patterns before embedding user text in an LLM prompt."""
        sanitized = text.strip()[:max_length]
        sanitized = re.sub(r"[`<>]", "", sanitized)
        _injection_patterns = re.compile(
            r"(ignore\s+(all\s+)?previous\s+instructions|system\s*:|assistant\s*:|<\|im_start\|>)",
            re.IGNORECASE,
        )
        sanitized = _injection_patterns.sub("", sanitized)
        return sanitized.strip()

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

    # ------------------------------------------------------------------
    # Dictionary-first lookup (fast, ~5ms)
    # ------------------------------------------------------------------

    def dictionary_check(self, ua_word: str, player_answer: str) -> Optional[str]:
        """Check dictionary_entries table for a match.

        Returns:
          "exact"   — exact translation found
          "similar" — word exists and answer is close (contains / token overlap)
          "wrong"   — word exists but answer doesn't match any translation
          None      — word not found in dictionary at all (use AI fallback)
        """
        normalized_answer = player_answer.strip().lower()
        normalized_ua = ua_word.strip().lower()

        if not normalized_answer or not normalized_ua:
            return None

        with get_db() as session:
            # Direct exact match: does this Ukrainian word have this exact English translation?
            row = session.execute(
                text(
                    "SELECT en_word FROM dictionary_entries "
                    "WHERE LOWER(ua_word) = :ua AND LOWER(en_word) = :en "
                    "LIMIT 1"
                ),
                {"ua": normalized_ua, "en": normalized_answer},
            ).mappings().first()

            if row:
                return "exact"  # Exact match found

            # Get all English translations for this Ukrainian word
            rows = session.execute(
                text(
                    "SELECT en_word FROM dictionary_entries "
                    "WHERE LOWER(ua_word) = :ua "
                    "LIMIT 20"
                ),
                {"ua": normalized_ua},
            ).mappings().all()

            if rows:
                # Word exists in dictionary — check if any translation is close enough
                for r in rows:
                    en = r["en_word"].lower().strip()
                    # Contains match (e.g. "dog" in "hot dog", or answer "automobile" contains "auto")
                    if normalized_answer in en or en in normalized_answer:
                        return "similar"
                    # Token overlap for multi-word translations
                    en_tokens = set(en.split())
                    answer_tokens = set(normalized_answer.split())
                    if en_tokens and answer_tokens:
                        overlap = len(en_tokens & answer_tokens)
                        if overlap >= min(len(en_tokens), len(answer_tokens)):
                            return "similar"
                return "wrong"  # Word found in dictionary but answer doesn't match any translation

            return None  # Word not in dictionary — use AI fallback

    def similarity_check(self, ua_word: str, player_answer: str) -> bool:
        """Returns True if answer is 80%+ similar to any known translation."""
        normalized = player_answer.strip().lower()
        normalized_ua = ua_word.strip().lower()

        if not normalized or not normalized_ua:
            return False

        with get_db() as session:
            rows = session.execute(
                text(
                    "SELECT en_word FROM dictionary_entries "
                    "WHERE LOWER(ua_word) = :ua "
                    "LIMIT 20"
                ),
                {"ua": normalized_ua},
            ).scalars().all()

        for en_word in rows:
            ratio = SequenceMatcher(None, normalized, en_word.lower().strip()).ratio()
            if ratio >= 0.80:
                return True
        return False

    # ------------------------------------------------------------------
    # Translation mode helpers (legacy, kept for backward compat)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Description-mode scoring (primary game mode)
    # ------------------------------------------------------------------

    def _description_fallback(self, word: str, description: str) -> ScoreResult:
        """Quick keyword-based fallback when LLM is unavailable."""
        w = self._normalize(word)
        d = self._normalize(description)

        # If the description literally contains the word, that's a pass
        if w in d:
            return ScoreResult(score=1, source="fallback_contains_word", used_llm=False)

        # Check synonym overlap
        word_synonyms = self._synonyms.get(w, set()) | {w}
        for syn in word_synonyms:
            if syn in d:
                return ScoreResult(score=1, source="fallback_synonym_match", used_llm=False)

        return ScoreResult(score=0, source="fallback_no_match", used_llm=False)

    async def _call_llm_describe(self, word: str, description: str, ua_word: str = "") -> Optional[ScoreResult]:
        """Call Gemini to judge whether the English response matches the Ukrainian word."""
        from .services.gemini_service import (
            GeminiServiceError,
            generate_text,
        )

        safe_word = self._sanitize_for_llm(word, max_length=64)
        safe_desc = self._sanitize_for_llm(description, max_length=200)
        safe_ua = self._sanitize_for_llm(ua_word, max_length=64) if ua_word else ""

        if safe_ua:
            prompt = (
                "You are a vocabulary judge for a Ukrainian-English learning game. "
                f'The Ukrainian word shown to the player was: "{safe_ua}". '
                f'The player\'s English response was: "{safe_desc}". '
                "Is the player's response a correct translation or accurate description of the Ukrainian word? "
                "Reply with only: YES or NO"
            )
        else:
            prompt = (
                f'You are a vocabulary judge. The word is: "{safe_word}". '
                f'The player\'s description is: "{safe_desc}". '
                "Does the description correctly explain the meaning of the word? "
                "Reply with only: YES or NO"
            )

        LLM_CALLS_TOTAL.inc()

        try:
            raw = await asyncio.wait_for(
                generate_text(prompt),
                timeout=LLM_HARD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            LLM_TIMEOUTS_TOTAL.inc()
            logger.warning("LLM describe timeout", extra={"event": "llm_describe_timeout"})
            return None
        except GeminiServiceError:
            logger.warning("LLM describe service error", extra={"event": "llm_describe_error"})
            return None
        except Exception:
            logger.exception("LLM describe call failed", extra={"event": "llm_describe_failed"})
            return None

        answer = raw.strip().upper()
        if answer.startswith("YES"):
            logger.info(
                "AI description check: accepted",
                extra={"event": "ai_description_check", "ua_word": ua_word, "answer": description, "result": True},
            )
            return ScoreResult(score=1, source="llm", used_llm=True)
        logger.info(
            "AI description check: rejected",
            extra={"event": "ai_description_check", "ua_word": ua_word, "answer": description, "result": False},
        )
        return ScoreResult(score=0, source="llm", used_llm=True)

    async def score_description(self, word: str, description: str, ua_word: str = "") -> ScoreResult:
        """Score a player's English response for a Ukrainian word.

        Pipeline:
          1. Check LLM cache (instant if cached)
          2. Check dictionary (fast DB lookup, ~5ms)
             - exact match → +2 pts
             - similar (contains/overlap) → +1 pt
             - no match → 0 pts
          3. AI fallback only if word not in dictionary (slower, ~2-4s)
             - AI says YES → +1 pt (description accepted)
             - AI says NO → 0 pts

        Returns ScoreResult with score 2, 1, or 0.
        """
        key = self._cache_key(f"{ua_word}:{word}" if ua_word else word, description)
        cached = self._load_cached(key)
        if cached:
            return cached

        # STEP 2: Dictionary lookup (fast)
        if ua_word:
            dict_result = self.dictionary_check(ua_word, description)
            if dict_result == "exact":
                result = ScoreResult(score=2, source="dictionary_exact", used_llm=False)
                self._store_cached(key, result)
                return result
            elif dict_result == "similar":
                result = ScoreResult(score=1, source="dictionary_similar", used_llm=False)
                self._store_cached(key, result)
                return result
            elif dict_result == "wrong":
                # Dictionary says wrong, but check similarity before giving 0
                if self.similarity_check(ua_word, description):
                    result = ScoreResult(score=1, source="similarity", used_llm=False)
                    self._store_cached(key, result)
                    return result
                result = ScoreResult(score=0, source="dictionary", used_llm=False)
                self._store_cached(key, result)
                return result
            # dict_result is None → word not in dictionary, fall through to AI

        # STEP 2b: Similarity check (difflib, fast, no AI)
        if ua_word and self.similarity_check(ua_word, description):
            result = ScoreResult(score=1, source="similarity", used_llm=False)
            self._store_cached(key, result)
            return result

        # STEP 3: AI fallback
        try:
            llm_result = await asyncio.wait_for(
                self._call_llm_describe(word, description, ua_word=ua_word),
                timeout=LLM_HARD_TIMEOUT + 1.0,
            )
        except asyncio.TimeoutError:
            LLM_TIMEOUTS_TOTAL.inc()
            logger.warning("LLM hard timeout in score_description()", extra={"event": "llm_hard_timeout"})
            llm_result = None

        if llm_result:
            self._store_cached(key, llm_result)
            return llm_result

        # Fallback
        fallback = self._description_fallback(word, description)
        self._store_cached(key, fallback)
        return fallback

    # ------------------------------------------------------------------
    # Legacy translation scoring (kept for backward compat)
    # ------------------------------------------------------------------

    async def _call_llm(self, correct_answer: str, user_answer: str) -> Optional[ScoreResult]:
        if not settings.enable_llm_scoring or not settings.llm_api_url:
            return None
        if aiohttp is None:
            return None

        safe_correct = self._sanitize_for_llm(correct_answer)
        safe_user = self._sanitize_for_llm(user_answer)

        payload = {
            "prompt": (
                "You are a translation quality scorer. "
                "Score the user's translation from 0 to 2. "
                "0=wrong, 1=partial, 2=correct. "
                "Respond with ONLY a JSON object: {\"score\": N}\n"
                "---\n"
                f"Correct answer: \"{safe_correct}\"\n"
                f"User answer: \"{safe_user}\"\n"
                "---"
            ),
            "correct_answer": safe_correct,
            "user_answer": safe_user,
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
        """Legacy translation scoring."""
        key = self._cache_key(correct_answer, user_answer)
        cached = self._load_cached(key)
        if cached:
            return cached

        quick = self._quick_match(correct_answer, user_answer)
        if quick:
            self._store_cached(key, quick)
            return quick

        try:
            llm_result = await asyncio.wait_for(
                self._call_llm(correct_answer, user_answer),
                timeout=settings.llm_timeout + 1.0,
            )
        except asyncio.TimeoutError:
            LLM_TIMEOUTS_TOTAL.inc()
            logger.warning("LLM hard timeout in score()", extra={"event": "llm_hard_timeout"})
            llm_result = None

        if llm_result:
            self._store_cached(key, llm_result)
            return llm_result

        fallback = self._semantic_lite(correct_answer, user_answer)
        self._store_cached(key, fallback)
        return fallback

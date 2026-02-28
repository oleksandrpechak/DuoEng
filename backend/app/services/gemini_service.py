from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from threading import Lock
from typing import Any

from ..config import settings

logger = logging.getLogger("duoeng.gemini")
CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_LEVEL_SET = set(CEFR_LEVELS)


class GeminiServiceError(RuntimeError):
    """Base Gemini service error."""


class GeminiConfigurationError(GeminiServiceError):
    """Raised when Gemini cannot be initialized due to config/credentials issues."""


class GeminiServiceTimeoutError(GeminiServiceError):
    """Raised when Gemini generation exceeds timeout."""


@dataclass(frozen=True)
class GeminiRuntimeConfig:
    project: str
    location: str
    model: str
    timeout_seconds: float
    max_output_tokens: int
    temperature: float


class GeminiService:
    """Reusable Gemini text generation service with ADC auth."""

    def __init__(self, cfg: GeminiRuntimeConfig) -> None:
        self._cfg = cfg
        self._client: Any | None = None
        self._client_lock = Lock()

    def _build_client(self) -> Any:
        if not self._cfg.project:
            raise GeminiConfigurationError("GEMINI_PROJECT (or GOOGLE_CLOUD_PROJECT) is not set")

        try:
            from google import genai
            from google.auth.exceptions import DefaultCredentialsError
        except ImportError as exc:
            raise GeminiConfigurationError(
                "Gemini dependencies are not installed; add google-genai/google-auth"
            ) from exc

        try:
            return genai.Client(
                vertexai=True,
                project=self._cfg.project,
                location=self._cfg.location,
            )
        except DefaultCredentialsError as exc:
            logger.exception(
                "Gemini ADC credentials are unavailable",
                extra={"event": "gemini_adc_missing"},
            )
            raise GeminiConfigurationError("ADC credentials are not configured") from exc
        except Exception as exc:
            logger.exception(
                "Gemini client initialization failed",
                extra={"event": "gemini_client_init_failed"},
            )
            raise GeminiConfigurationError("Failed to initialize Gemini client") from exc

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        with self._client_lock:
            if self._client is None:
                self._client = self._build_client()
        return self._client

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        text_value = (getattr(response, "text", None) or "").strip()
        if text_value:
            return text_value

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            merged = [str(getattr(part, "text", "")).strip() for part in parts if getattr(part, "text", None)]
            if merged:
                return "\n".join(merged)
        return ""

    def _generate_sync(self, prompt: str) -> str:
        try:
            from google.genai import types as genai_types
        except ImportError as exc:
            raise GeminiConfigurationError(
                "Gemini dependencies are not installed; add google-genai/google-auth"
            ) from exc

        client = self._get_client()
        config = genai_types.GenerateContentConfig(
            temperature=self._cfg.temperature,
            max_output_tokens=self._cfg.max_output_tokens,
        )
        response = client.models.generate_content(
            model=self._cfg.model,
            contents=prompt,
            config=config,
        )
        text_value = self._extract_response_text(response).strip()
        if not text_value:
            raise GeminiServiceError("Gemini returned an empty response")
        return text_value

    @staticmethod
    def _normalize_word(word: str) -> str:
        return " ".join(word.strip().lower().split())

    @staticmethod
    def _extract_json_payload(raw_text: str) -> Any:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        bracket_start = raw_text.find("[")
        bracket_end = raw_text.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            return json.loads(raw_text[bracket_start : bracket_end + 1])

        brace_start = raw_text.find("{")
        brace_end = raw_text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            return json.loads(raw_text[brace_start : brace_end + 1])

        raise GeminiServiceError("Gemini response is not valid JSON")

    @staticmethod
    def _parse_word_levels_payload(payload: Any) -> dict[str, str]:
        rows: Any = payload
        if isinstance(rows, dict):
            for key in ("items", "results", "words", "data"):
                candidate = rows.get(key)
                if isinstance(candidate, list):
                    rows = candidate
                    break

        if not isinstance(rows, list):
            raise GeminiServiceError("Gemini JSON payload must be a list")

        mapping: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            word = str(row.get("word", "")).strip()
            level = str(row.get("level", "")).strip().upper()
            if not word or level not in CEFR_LEVEL_SET:
                continue
            mapping[GeminiService._normalize_word(word)] = level

        if not mapping:
            raise GeminiServiceError("Gemini returned no valid word levels")
        return mapping

    def _classify_words_batch_sync(self, words: list[str]) -> dict[str, str]:
        try:
            from google.genai import types as genai_types
        except ImportError as exc:
            raise GeminiConfigurationError(
                "Gemini dependencies are not installed; add google-genai/google-auth"
            ) from exc

        if not words:
            return {}

        client = self._get_client()
        prompt_lines = [
            "You are a CEFR classifier for English vocabulary.",
            "Assign exactly one level to each word: A1, A2, B1, B2, C1, or C2.",
            'Return ONLY valid JSON array objects with keys "word" and "level".',
            "Do not include explanations.",
            "Words:",
        ]
        prompt_lines.extend(f"- {word}" for word in words)
        prompt = "\n".join(prompt_lines)

        config = genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=max(self._cfg.max_output_tokens, len(words) * 24),
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=self._cfg.model,
            contents=prompt,
            config=config,
        )
        text_value = self._extract_response_text(response).strip()
        if not text_value:
            raise GeminiServiceError("Gemini returned empty CEFR output")

        parsed = self._extract_json_payload(text_value)
        mapping = self._parse_word_levels_payload(parsed)

        missing = [word for word in words if self._normalize_word(word) not in mapping]
        if missing:
            raise GeminiServiceError(
                f"Gemini response missing levels for {len(missing)} words"
            )
        return mapping

    async def generate_text(self, prompt: str) -> str:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ValueError("Prompt is required")

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, cleaned_prompt),
                timeout=self._cfg.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Gemini request timeout",
                extra={
                    "event": "gemini_timeout",
                    "reason": "deadline_exceeded",
                },
            )
            raise GeminiServiceTimeoutError("Gemini request timed out") from exc
        except (GeminiConfigurationError, ValueError):
            raise
        except GeminiServiceError:
            raise
        except Exception as exc:
            logger.exception(
                "Gemini generation failed",
                extra={
                    "event": "gemini_generation_failed",
                    "reason": exc.__class__.__name__,
                },
            )
            raise GeminiServiceError("Gemini request failed") from exc

    async def classify_words_cefr(self, words: list[str]) -> list[dict[str, str]]:
        if not words:
            raise ValueError("At least one word is required")

        cleaned_words = [" ".join(word.strip().split()) for word in words if str(word).strip()]
        if not cleaned_words:
            raise ValueError("At least one non-empty word is required")

        if len(cleaned_words) > settings.word_level_max_words:
            raise ValueError(
                f"Too many words: max {settings.word_level_max_words} per request"
            )

        unique_words: list[str] = []
        seen: set[str] = set()
        for word in cleaned_words:
            normalized = self._normalize_word(word)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_words.append(word)

        levels_by_word: dict[str, str] = {}
        batch_size = max(1, settings.word_level_batch_size)

        for offset in range(0, len(unique_words), batch_size):
            batch = unique_words[offset : offset + batch_size]
            logger.info(
                "Classifying word CEFR levels",
                extra={
                    "event": "word_level_batch_started",
                    "reason": "gemini_classification",
                },
            )
            try:
                batch_result = await asyncio.wait_for(
                    asyncio.to_thread(self._classify_words_batch_sync, batch),
                    timeout=self._cfg.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "Gemini word level timeout",
                    extra={"event": "word_level_timeout", "reason": "deadline_exceeded"},
                )
                raise GeminiServiceTimeoutError("Word level classification timed out") from exc

            levels_by_word.update(batch_result)

        output: list[dict[str, str]] = []
        for word in cleaned_words:
            level = levels_by_word.get(self._normalize_word(word))
            if not level:
                raise GeminiServiceError(f"Missing CEFR level for word: {word}")
            output.append({"word": word, "level": level})

        return output


@lru_cache(maxsize=1)
def get_gemini_service() -> GeminiService:
    return GeminiService(
        GeminiRuntimeConfig(
            project=settings.gemini_project,
            location=settings.gemini_location,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout,
            max_output_tokens=settings.gemini_max_output_tokens,
            temperature=settings.gemini_temperature,
        )
    )


async def generate_text(prompt: str) -> str:
    """Module-level async helper required by service contract."""

    return await get_gemini_service().generate_text(prompt)


async def classify_words_cefr(words: list[str]) -> list[dict[str, str]]:
    """Classify English words into CEFR levels using Gemini."""

    return await get_gemini_service().classify_words_cefr(words)

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
import logging
from threading import Lock
from typing import Any

from ..config import settings

logger = logging.getLogger("duoeng.gemini")


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

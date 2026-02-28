from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..schemas import AIGenerateRequest, AIGenerateResponse
from ..services.gemini_service import (
    GeminiConfigurationError,
    GeminiServiceError,
    GeminiServiceTimeoutError,
    generate_text,
)

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger("duoeng.ai")


@router.post("/generate", response_model=AIGenerateResponse)
async def generate_ai_text(payload: AIGenerateRequest) -> AIGenerateResponse:
    """Generate text using Gemini 2.0 Flash through Vertex AI (ADC)."""

    try:
        generated = await generate_text(payload.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GeminiServiceTimeoutError as exc:
        raise HTTPException(status_code=504, detail="AI generation timed out") from exc
    except GeminiConfigurationError as exc:
        logger.error(
            "AI service configuration error",
            extra={
                "event": "ai_configuration_error",
                "reason": str(exc),
                "path": "/ai/generate",
            },
        )
        raise HTTPException(status_code=503, detail="AI service is not configured") from exc
    except GeminiServiceError as exc:
        logger.exception(
            "AI service execution failed",
            extra={
                "event": "ai_generation_failed",
                "path": "/ai/generate",
            },
        )
        raise HTTPException(status_code=502, detail="AI service request failed") from exc

    return AIGenerateResponse(result=generated)

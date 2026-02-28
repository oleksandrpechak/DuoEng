from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..schemas import WordLevelItem, WordLevelsRequest
from ..services.gemini_service import (
    GeminiConfigurationError,
    GeminiServiceError,
    GeminiServiceTimeoutError,
    classify_words_cefr,
)

router = APIRouter(prefix="/api/v1/words", tags=["words"])
logger = logging.getLogger("duoeng.words")


@router.post(
    "/level",
    response_model=list[WordLevelItem],
    summary="Assign CEFR level for each input English word",
    description="Returns CEFR levels (A1-C2) for a provided list of English words.",
    responses={
        200: {
            "description": "CEFR levels assigned successfully",
            "content": {
                "application/json": {
                    "example": [
                        {"word": "apple", "level": "A1"},
                        {"word": "analyze", "level": "B2"},
                        {"word": "meticulous", "level": "C1"},
                    ]
                }
            },
        },
        400: {"description": "Invalid request payload"},
        502: {"description": "Gemini response could not be processed"},
        503: {"description": "Gemini service misconfigured"},
        504: {"description": "Gemini request timed out"},
    },
)
async def classify_word_levels(payload: WordLevelsRequest) -> list[WordLevelItem]:
    """Classify each word in the request into a CEFR level."""

    try:
        result = await classify_words_cefr(payload.words)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GeminiServiceTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Word level classification timed out") from exc
    except GeminiConfigurationError as exc:
        logger.error(
            "Word levels service configuration error",
            extra={
                "event": "word_levels_configuration_error",
                "reason": str(exc),
                "path": "/api/v1/words/level",
            },
        )
        raise HTTPException(status_code=503, detail="Word levels service is not configured") from exc
    except GeminiServiceError as exc:
        logger.exception(
            "Word levels service failed",
            extra={
                "event": "word_levels_failed",
                "path": "/api/v1/words/level",
            },
        )
        raise HTTPException(status_code=502, detail="Word levels classification failed") from exc

    return [WordLevelItem(**item) for item in result]

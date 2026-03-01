from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _normalize_database_url(value: str | None, fallback: str) -> str:
    raw = (value or fallback).strip() or fallback
    # Some dashboards accidentally store quoted values.
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    if "://" not in raw:
        return raw

    scheme, suffix = raw.split("://", 1)
    scheme = scheme.lower()

    # Force a driver we install in production image.
    if scheme in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+asyncpg",
        "postgresql+pg8000",
        "postgresql+psycopg2",
    }:
        url = f"postgresql+psycopg2://{suffix}"
        # Append sslmode=require for encrypted DB connections (production safety).
        if "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode=require"
        return url

    return raw


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    jwt_algorithm: str
    jwt_exp_minutes: int
    port: int
    database_url: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int
    db_pool_recycle: int
    cors_origins: list[str]
    frontend_url: str
    debug: bool
    turn_timeout_seconds: int
    room_code_length: int
    room_code_attempts: int
    llm_api_url: str
    llm_api_key: str
    llm_timeout: float
    llm_cache_ttl_seconds: int
    enable_llm_scoring: bool
    rate_limit_requests_per_min: int
    rate_limit_submits_per_min: int
    rate_limit_ws_messages_per_min: int
    redis_url: str
    default_elo: int
    k_factor: int
    ban_seconds: int
    max_join_failures_per_min: int
    suspicious_attempts_per_min: int
    target_score_default: int
    admin_nicknames: set[str]
    enable_prometheus_metrics: bool
    farm_wins_per_min_threshold: int
    google_application_credentials: str
    gemini_project: str
    gemini_location: str
    gemini_model: str
    gemini_max_output_tokens: int
    gemini_temperature: float
    word_level_batch_size: int
    word_level_max_words: int
    log_level: str

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.env.lower() not in {"development", "dev", "test", "testing"}

    def validate(self) -> None:
        """Raise early on dangerous mis-configurations in non-dev environments."""
        if self.is_production and self.secret_key == _DEFAULT_SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY must be explicitly set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )


_DEFAULT_SECRET_KEY = "change-me-in-production-min-32-bytes-key"


settings = Settings(
    env=os.getenv("ENV", "development"),
    secret_key=os.getenv("SECRET_KEY", _DEFAULT_SECRET_KEY),
    jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
    jwt_exp_minutes=_as_int(os.getenv("JWT_EXP_MINUTES"), 60 * 12),
    port=_as_int(os.getenv("PORT"), 8000),
    database_url=_normalize_database_url(
        os.getenv("DATABASE_URL"),
        "sqlite:///./duoeng.db",
    ),
    db_pool_size=max(1, _as_int(os.getenv("DB_POOL_SIZE"), 5)),
    db_max_overflow=max(0, _as_int(os.getenv("DB_MAX_OVERFLOW"), 10)),
    db_pool_timeout=max(1, _as_int(os.getenv("DB_POOL_TIMEOUT"), 30)),
    db_pool_recycle=max(60, _as_int(os.getenv("DB_POOL_RECYCLE"), 1800)),
    cors_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", os.getenv("FRONTEND_URL", "http://localhost:3000")).split(",")
        if origin.strip()
    ],
    frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").strip(),
    debug=_as_bool(os.getenv("DEBUG"), False),
    turn_timeout_seconds=_as_int(os.getenv("TURN_TIMEOUT_SECONDS"), 30),
    room_code_length=max(8, _as_int(os.getenv("ROOM_CODE_LENGTH"), 8)),
    room_code_attempts=max(3, _as_int(os.getenv("ROOM_CODE_ATTEMPTS"), 12)),
    llm_api_url=os.getenv("LLM_API_URL", "").strip(),
    llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
    llm_timeout=max(0.3, _as_float(os.getenv("LLM_TIMEOUT"), 1.5)),
    llm_cache_ttl_seconds=_as_int(os.getenv("LLM_CACHE_TTL_SECONDS"), 60 * 60 * 24),
    enable_llm_scoring=_as_bool(os.getenv("ENABLE_LLM_SCORING"), True),
    rate_limit_requests_per_min=_as_int(os.getenv("RATE_LIMIT_REQUESTS_PER_MIN"), 60),
    rate_limit_submits_per_min=_as_int(os.getenv("RATE_LIMIT_SUBMITS_PER_MIN"), 40),
    rate_limit_ws_messages_per_min=_as_int(os.getenv("RATE_LIMIT_WS_MESSAGES_PER_MIN"), 120),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
    default_elo=_as_int(os.getenv("DEFAULT_ELO"), 1000),
    k_factor=_as_int(os.getenv("K_FACTOR"), 32),
    ban_seconds=_as_int(os.getenv("BAN_SECONDS"), 300),
    max_join_failures_per_min=_as_int(os.getenv("MAX_JOIN_FAILURES_PER_MIN"), 12),
    suspicious_attempts_per_min=_as_int(os.getenv("SUSPICIOUS_ATTEMPTS_PER_MIN"), 8),
    target_score_default=_as_int(os.getenv("TARGET_SCORE_DEFAULT"), 10),
    admin_nicknames={
        item.strip().lower()
        for item in os.getenv("ADMIN_NICKNAMES", "admin").split(",")
        if item.strip()
    },
    enable_prometheus_metrics=_as_bool(os.getenv("ENABLE_PROMETHEUS_METRICS"), True),
    farm_wins_per_min_threshold=_as_int(os.getenv("FARM_WINS_PER_MIN_THRESHOLD"), 5),
    google_application_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/etc/secrets/gcp-key.json").strip(),
    gemini_project=(
        os.getenv("GEMINI_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
        or ""
    ).strip(),
    gemini_location=os.getenv("GEMINI_LOCATION", "us-central1").strip(),
    gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
    gemini_max_output_tokens=max(1, _as_int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS"), 512)),
    gemini_temperature=max(0.0, min(2.0, _as_float(os.getenv("GEMINI_TEMPERATURE"), 0.2))),
    word_level_batch_size=max(1, _as_int(os.getenv("WORD_LEVEL_BATCH_SIZE"), 25)),
    word_level_max_words=max(1, _as_int(os.getenv("WORD_LEVEL_MAX_WORDS"), 200)),
    log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
)

settings.validate()

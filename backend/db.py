from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        future=True,
    )


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_ENGINE = _build_engine(settings.database_url)
SessionLocal = sessionmaker(
    bind=_ENGINE,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
    future=True,
)


def get_engine() -> Engine:
    return _ENGINE


def reset_database_engine(database_url: str | None = None) -> None:
    global _ENGINE
    if database_url:
        object.__setattr__(settings, "database_url", database_url)

    _ENGINE.dispose()
    _ENGINE = _build_engine(settings.database_url)
    SessionLocal.configure(bind=_ENGINE)


@contextmanager
def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_connection() -> None:
    with _ENGINE.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db() -> None:
    Base.metadata.create_all(bind=_ENGINE)


def seed_sample_words_if_empty() -> int:
    sample_words = [
        ("привіт", "hello", "B1"),
        ("дякую", "thank you", "B1"),
        ("будь ласка", "please", "B1"),
        ("добрий ранок", "good morning", "B1"),
        ("на добраніч", "good night", "B1"),
        ("так", "yes", "B1"),
        ("ні", "no", "B1"),
        ("вода", "water", "B1"),
        ("хліб", "bread", "B1"),
        ("молоко", "milk", "B1"),
        ("яблуко", "apple", "B1"),
        ("книга", "book", "B1"),
        ("стіл", "table", "B1"),
        ("стілець", "chair", "B1"),
        ("вікно", "window", "B1"),
        ("двері", "door", "B1"),
        ("будинок", "house", "B1"),
        ("машина", "car", "B1"),
        ("собака", "dog", "B1"),
        ("кіт", "cat", "B1"),
        ("друг", "friend", "B1"),
        ("сім'я", "family", "B1"),
        ("любов", "love", "B1"),
        ("час", "time", "B1"),
        ("день", "day", "B1"),
        ("незважаючи на", "despite", "B2"),
        ("однак", "however", "B2"),
        ("отже", "therefore", "B2"),
        ("насправді", "actually", "B2"),
        ("очевидно", "obviously", "B2"),
        ("можливо", "perhaps", "B2"),
        ("зрештою", "eventually", "B2"),
        ("здебільшого", "mostly", "B2"),
        ("зазвичай", "usually", "B2"),
        ("визначати", "determine", "B2"),
        ("досягати", "achieve", "B2"),
        ("впливати", "influence", "B2"),
        ("порівнювати", "compare", "B2"),
        ("враження", "impression", "B2"),
        ("досвід", "experience", "B2"),
        ("середовище", "environment", "B2"),
        ("розвиток", "development", "B2"),
        ("суспільство", "society", "B2"),
        ("уряд", "government", "B2"),
        ("економіка", "economy", "B2"),
        ("культура", "culture", "B2"),
        ("освіта", "education", "B2"),
        ("наука", "science", "B2"),
        ("технологія", "technology", "B2"),
        ("здоров'я", "health", "B2"),
    ]

    with get_db() as session:
        count = session.execute(text("SELECT COUNT(*) FROM words")).scalar_one()
        if count > 0:
            return 0

        session.execute(
            text("INSERT INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level)"),
            [
                {"id": f"seed-{idx:03d}", "ua": ua, "en": en, "level": level}
                for idx, (ua, en, level) in enumerate(sample_words, start=1)
            ],
        )

    return len(sample_words)


def clear_expired_llm_cache() -> None:
    with get_db() as session:
        session.execute(
            text("DELETE FROM llm_cache WHERE expires_at <= :now"),
            {"now": _utc_now()},
        )

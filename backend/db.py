from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import sqlite3
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

logger = logging.getLogger("duoeng.db")

CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}

# Part-of-speech abbreviation expansion
POS_MAP = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "prep": "preposition",
    "conj": "conjunction",
    "pron": "pronoun",
    "num": "numeral",
    "pref": "prefix",
    "suf": "suffix",
    "int": "interjection",
}


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
    try:
        with _ENGINE.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection check passed")
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        raise


def init_db() -> None:
    Base.metadata.create_all(bind=_ENGINE)


# ---------------------------------------------------------------------------
# Dictionary Seeder — dmklinger/ukrainian
# ---------------------------------------------------------------------------

def _expand_pos(raw: str) -> str:
    """Expand part-of-speech abbreviation to full word."""
    cleaned = raw.strip().lower()
    return POS_MAP.get(cleaned, cleaned)


def _make_word_id(en: str) -> str:
    """Create a stable unique word id from the English text."""
    slug = en.lower().replace(" ", "_").replace("'", "")
    if len(slug) > 56:
        slug = slug[:52] + hashlib.md5(en.encode()).hexdigest()[:4]
    return slug[:64]


def seed_from_dmklinger(force: bool = False) -> int:
    """Seed the words + dictionary_entries tables from dmklinger_processed.csv.

    Returns the number of unique words inserted into the words table.
    Idempotent: uses ON CONFLICT upsert.
    """
    csv_path = Path(__file__).parent / "seeds" / "dmklinger_processed.csv"

    if not csv_path.exists():
        logger.warning("dmklinger_processed.csv not found — seeding sample words only")
        return _seed_sample_words(force)

    logger.info("Using dictionary source: %s", csv_path)

    with get_db() as session:
        existing_count = session.execute(text("SELECT COUNT(*) FROM words")).scalar() or 0
        if existing_count > 100 and not force:
            logger.info("Dictionary already seeded with %d words, skipping", existing_count)
            return 0

    if force:
        logger.info("Force reseed — clearing words and dictionary_entries tables")
        with get_db() as session:
            session.execute(text("DELETE FROM dictionary_entries"))
            session.execute(text("DELETE FROM words"))

    is_sqlite = settings.database_url.startswith("sqlite")

    word_sql = (
        "INSERT OR REPLACE INTO words (id, ua, en, level, definition, example) "
        "VALUES (:id, :ua, :en, :level, :definition, :example)"
        if is_sqlite
        else "INSERT INTO words (id, ua, en, level, definition, example) "
        "VALUES (:id, :ua, :en, :level, :definition, :example) "
        "ON CONFLICT (id) DO UPDATE SET ua = :ua, en = :en, level = :level, "
        "definition = :definition, example = :example"
    )

    dict_sql = (
        "INSERT OR REPLACE INTO dictionary_entries "
        "(ua_word, en_word, part_of_speech, source, definition, example, created_at) "
        "VALUES (:ua_word, :en_word, :part_of_speech, :source, :definition, :example, :created_at)"
        if is_sqlite
        else "INSERT INTO dictionary_entries (ua_word, en_word, part_of_speech, source, definition, example, created_at) "
        "VALUES (:ua_word, :en_word, :part_of_speech, :source, :definition, :example, :created_at) "
        "ON CONFLICT (ua_word, en_word) DO UPDATE SET "
        "definition = :definition, example = :example, source = :source"
    )

    inserted_words = 0
    inserted_dict = 0
    seen_word_ids: set[str] = set()
    batch_words: list[dict] = []
    batch_dict: list[dict] = []
    BATCH_SIZE = 500 if is_sqlite else 5000
    rows_processed = 0

    def flush(session: Session) -> tuple[int, int]:
        nonlocal batch_words, batch_dict
        w = d = 0
        if batch_words:
            session.execute(text(word_sql), batch_words)
            w = len(batch_words)
            batch_words = []
        if batch_dict:
            session.execute(text(dict_sql), batch_dict)
            d = len(batch_dict)
            batch_dict = []
        session.commit()
        return w, d

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        with get_db() as session:
            for row in reader:
                ua = (row.get("ua_word") or "").strip()
                en = (row.get("en_word") or "").strip()
                pos = _expand_pos((row.get("part_of_speech") or "").strip())
                level = (row.get("level") or "B1").strip().upper()
                definition = (row.get("definition") or "").strip()
                example = (row.get("example") or "").strip()

                if not ua or not en:
                    continue
                if level not in CEFR_LEVELS:
                    level = "B1"
                if len(en) > 60 or len(ua) > 100:
                    continue

                batch_dict.append({
                    "ua_word": ua.lower(),
                    "en_word": en.lower(),
                    "part_of_speech": pos or None,
                    "source": "dmklinger",
                    "definition": definition,
                    "example": example,
                    "created_at": _utc_now(),
                })

                word_id = _make_word_id(en)
                if word_id and word_id not in seen_word_ids:
                    seen_word_ids.add(word_id)
                    batch_words.append({
                        "id": word_id,
                        "ua": ua,
                        "en": en,
                        "level": level,
                        "definition": definition,
                        "example": example,
                    })

                rows_processed += 1
                if len(batch_dict) >= BATCH_SIZE:
                    w, d = flush(session)
                    inserted_words += w
                    inserted_dict += d
                    if rows_processed % 10000 == 0:
                        logger.info("Seeding progress: %d rows processed", rows_processed)

            w, d = flush(session)
            inserted_words += w
            inserted_dict += d

    logger.info(
        "dmklinger seed complete: %d unique words, %d dictionary entries from %d rows",
        inserted_words, inserted_dict, rows_processed,
    )
    return inserted_words


def _seed_sample_words(force: bool = False) -> int:
    """Fallback: seed a small set of sample words when no CSV is available."""
    sample_words = [
        ("привіт", "hello", "A1"), ("так", "yes", "A1"), ("ні", "no", "A1"),
        ("дякую", "thank you", "A1"), ("будь ласка", "please", "A1"),
        ("вода", "water", "A1"), ("хліб", "bread", "A1"), ("молоко", "milk", "A1"),
        ("яблуко", "apple", "A1"), ("кіт", "cat", "A1"), ("собака", "dog", "A1"),
        ("будинок", "house", "A1"), ("день", "day", "A1"), ("ніч", "night", "A1"),
        ("мама", "mother", "A1"), ("тато", "father", "A1"), ("дитина", "child", "A1"),
        ("один", "one", "A1"), ("два", "two", "A1"), ("три", "three", "A1"),
        ("великий", "big", "A1"), ("малий", "small", "A1"), ("добрий", "good", "A1"),
        ("поганий", "bad", "A1"), ("їжа", "food", "A1"), ("школа", "school", "A1"),
        ("друг", "friend", "A1"), ("ім'я", "name", "A1"), ("місто", "city", "A1"),
        ("країна", "country", "A1"),
    ]

    with get_db() as session:
        existing = session.execute(text("SELECT COUNT(*) FROM words")).scalar() or 0
        if existing > 0 and not force:
            return 0

        session.execute(
            text("INSERT INTO words (id, ua, en, level, definition, example) "
                 "VALUES (:id, :ua, :en, :level, :definition, :example)"),
            [
                {"id": f"seed-{idx:03d}", "ua": ua, "en": en, "level": level,
                 "definition": "", "example": ""}
                for idx, (ua, en, level) in enumerate(sample_words, start=1)
            ],
        )

    logger.info("Seeded %d sample words (no CSV found)", len(sample_words))
    return len(sample_words)


def clear_expired_llm_cache() -> None:
    with get_db() as session:
        session.execute(
            text("DELETE FROM llm_cache WHERE expires_at <= :now"),
            {"now": _utc_now()},
        )

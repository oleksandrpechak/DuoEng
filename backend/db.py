from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
import os
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
    with _ENGINE.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db() -> None:
    Base.metadata.create_all(bind=_ENGINE)


# ---------------------------------------------------------------------------
# CSV Dictionary Seeder — auto-detects format
# ---------------------------------------------------------------------------

def _find_csv_path() -> str | None:
    """Locate the best dictionary CSV, preferring Oxford processed data."""
    candidates = [
        # Oxford 5000 processed data — highest priority
        Path(__file__).parent / "seeds" / "oxford_processed.csv",
        Path(__file__).parent.parent / "seeds" / "oxford_processed.csv",
        # Legacy dictionary_clean.csv — fallback only
        Path(__file__).parent / "data" / "processed" / "dictionary_clean.csv",
        Path(__file__).parent / "seeds" / "dictionary_clean.csv",
        Path(__file__).parent / "dictionary_clean.csv",
        Path(__file__).parent.parent / "data" / "processed" / "dictionary_clean.csv",
        Path(__file__).parent / "data" / "dictionary_clean.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _detect_csv_format(csv_path: str) -> str:
    """Detect the CSV format by inspecting the first line.

    Returns:
        "header4"  — has header row with 4 columns (dictionary_clean.csv)
        "header3"  — has header row with 3 columns
        "format1"  — no header, 3 cols, last col is CEFR level (sample words)
        "format2"  — no header, 4 cols (ua, en, pos, source)
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        first_line = f.readline().strip()

    if not first_line:
        return "format1"

    cols = first_line.split(",")

    # Check if the first line looks like a header row
    first_lower = [c.strip().lower() for c in cols]
    header_keywords = {"ua_word", "en_word", "word", "source", "part_of_speech", "pos", "level", "ua", "en"}
    if any(kw in header_keywords for kw in first_lower):
        if len(cols) >= 4:
            return "header4"
        return "header3"

    # No header — detect by content
    if len(cols) == 3 and cols[2].strip().upper() in CEFR_LEVELS:
        return "format1"

    if len(cols) >= 4:
        return "format2"

    return "format1"


def _expand_pos(raw: str) -> str:
    """Expand part-of-speech abbreviation to full word."""
    cleaned = raw.strip().lower()
    return POS_MAP.get(cleaned, cleaned)


def seed_from_csv(force: bool = False) -> int:
    """Seed the words + dictionary_entries tables from dictionary_clean.csv.

    Auto-detects CSV format (with/without headers, 3 or 4 columns).
    Returns the number of unique words inserted into the words table.
    Idempotent: uses ON CONFLICT DO NOTHING / INSERT OR IGNORE.
    """
    csv_path = _find_csv_path()

    if not csv_path:
        logger.warning("No dictionary CSV found — searched common paths")
        return 0

    is_oxford = "oxford_processed" in csv_path
    logger.info("Found CSV at: %s (oxford=%s)", csv_path, is_oxford)

    with get_db() as session:
        existing_count = session.execute(text("SELECT COUNT(*) FROM words")).scalar() or 0
        if existing_count > 50 and not force:
            logger.info("Dictionary already seeded with %d words, skipping", existing_count)
            return 0

    if force:
        logger.info("Force reseed — clearing words and dictionary_entries tables")
        with get_db() as session:
            session.execute(text("DELETE FROM words"))
            session.execute(text("DELETE FROM dictionary_entries"))

    fmt = _detect_csv_format(csv_path)
    logger.info("CSV format detected: %s", fmt)

    is_sqlite = settings.database_url.startswith("sqlite")

    # For Oxford data, use upsert (DO UPDATE) so reseeds update existing rows.
    # For legacy CSV, use DO NOTHING to be safe.
    if is_oxford:
        word_sql = (
            "INSERT INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level) "
            "ON CONFLICT (id) DO UPDATE SET ua = :ua, en = :en, level = :level"
            if not is_sqlite
            else "INSERT OR REPLACE INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level)"
        )
    else:
        word_sql = (
            "INSERT OR IGNORE INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level)"
            if is_sqlite
            else "INSERT INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level) ON CONFLICT (id) DO NOTHING"
        )

    dict_sql = (
        "INSERT OR IGNORE INTO dictionary_entries (ua_word, en_word, part_of_speech, source, created_at) "
        "VALUES (:ua_word, :en_word, :part_of_speech, :source, :created_at)"
        if is_sqlite
        else "INSERT INTO dictionary_entries (ua_word, en_word, part_of_speech, source, created_at) "
        "VALUES (:ua_word, :en_word, :part_of_speech, :source, :created_at) ON CONFLICT (ua_word, en_word) DO NOTHING"
    )

    inserted_words = 0
    inserted_dict = 0
    seen_word_ids: set[str] = set()
    batch_words: list[dict] = []
    batch_dict: list[dict] = []
    BATCH_SIZE = 5000 if not is_sqlite else 500
    rows_processed = 0

    def flush(session: Session) -> tuple[int, int]:
        nonlocal batch_words, batch_dict
        w = 0
        d = 0
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

    def _make_word_id(en: str) -> str:
        """Create a stable unique word id from the English text."""
        slug = en.lower().replace(" ", "_").replace("'", "")
        if len(slug) > 56:
            slug = slug[:52] + hashlib.md5(en.encode()).hexdigest()[:4]
        return slug[:64]

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        if fmt in ("header4", "header3"):
            # Has a header row — use DictReader
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            logger.info("CSV columns detected: %s", headers)

            # Auto-detect column names
            def _find_col(candidates: list[str]) -> str | None:
                for c in candidates:
                    for h in headers:
                        if h.strip().lower() == c.lower():
                            return h
                return None

            ua_col = _find_col(["ua_word", "ua", "ukrainian", "word_ua", "uk", "ukr"])
            en_col = _find_col(["en_word", "en", "english", "word_en", "word"])
            pos_col = _find_col(["part_of_speech", "pos", "type", "word_type"])
            level_col = _find_col(["level", "cefr", "cefr_level", "difficulty"])
            source_col = _find_col(["source"])

            logger.info("Mapped columns — ua:%s en:%s pos:%s level:%s source:%s",
                        ua_col, en_col, pos_col, level_col, source_col)

            if not ua_col or not en_col:
                logger.error("Cannot find ua/en columns in CSV. Headers: %s", headers)
                return 0

            with get_db() as session:
                for row in reader:
                    ua = (row.get(ua_col) or "").strip()
                    en = (row.get(en_col) or "").strip()
                    pos_raw = (row.get(pos_col) or "").strip() if pos_col else ""
                    pos = _expand_pos(pos_raw)
                    level = (row.get(level_col) or "B1").strip().upper() if level_col else "B1"
                    source = (row.get(source_col) or ("oxford" if is_oxford else "csv")).strip() if source_col else ("oxford" if is_oxford else "csv")

                    if not ua or not en:
                        continue
                    if level not in CEFR_LEVELS:
                        level = "B1"
                    # Skip very long entries (definitions, not words)
                    if len(en) > 60 or len(ua) > 100:
                        continue

                    # dictionary_entries — all rows
                    batch_dict.append({
                        "ua_word": ua.lower(),
                        "en_word": en.lower(),
                        "part_of_speech": pos or None,
                        "source": source.lower(),
                        "created_at": _utc_now(),
                    })

                    # words table — unique en words
                    word_id = _make_word_id(en)
                    if word_id and word_id not in seen_word_ids:
                        seen_word_ids.add(word_id)
                        batch_words.append({
                            "id": word_id,
                            "ua": ua,
                            "en": en,
                            "level": level,
                        })

                    rows_processed += 1
                    if len(batch_dict) >= BATCH_SIZE:
                        w, d = flush(session)
                        inserted_words += w
                        inserted_dict += d
                        if rows_processed % 50000 == 0:
                            logger.info("Seeding progress: %d rows processed", rows_processed)

                # Final flush
                w, d = flush(session)
                inserted_words += w
                inserted_dict += d

        else:
            # No header — read as raw CSV
            reader = csv.reader(f)

            with get_db() as session:
                for cols in reader:
                    if not cols or len(cols) < 2:
                        continue

                    if fmt == "format1":
                        # 3 columns: ua, en, level
                        ua = cols[0].strip()
                        en = cols[1].strip()
                        level_raw = cols[2].strip().upper() if len(cols) > 2 else "B1"
                        level = level_raw if level_raw in CEFR_LEVELS else "B1"
                        pos = ""
                        source = "sample"
                    else:
                        # format2: ua, en, pos, source
                        ua = cols[0].strip()
                        en = cols[1].strip()
                        pos_raw = cols[2].strip() if len(cols) > 2 else ""
                        pos = _expand_pos(pos_raw)
                        source = cols[3].strip() if len(cols) > 3 else "csv"
                        level = "B1"

                    if not ua or not en:
                        continue
                    if len(en) > 60 or len(ua) > 100:
                        continue

                    batch_dict.append({
                        "ua_word": ua.lower(),
                        "en_word": en.lower(),
                        "part_of_speech": pos or None,
                        "source": source.lower(),
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
                        })

                    rows_processed += 1
                    if len(batch_dict) >= BATCH_SIZE:
                        w, d = flush(session)
                        inserted_words += w
                        inserted_dict += d
                        if rows_processed % 50000 == 0:
                            logger.info("Seeding progress: %d rows processed", rows_processed)

                w, d = flush(session)
                inserted_words += w
                inserted_dict += d

    source_label = "Oxford 5000" if is_oxford else "CSV"
    logger.info(
        "%s seed complete: %d unique words, %d dictionary entries from %d rows",
        source_label,
        inserted_words,
        inserted_dict,
        rows_processed,
    )
    return inserted_words


def seed_sample_words_if_empty() -> int:
    """Seed from CSV first; fall back to hardcoded sample words only if CSV is unavailable."""
    force = os.environ.get("FORCE_RESEED", "0") == "1"
    csv_count = seed_from_csv(force=force)
    if csv_count > 0:
        return csv_count

    # Check if words table already has data (e.g. from previous CSV seed)
    with get_db() as session:
        existing = session.execute(text("SELECT COUNT(*) FROM words")).scalar() or 0
        if existing > 0:
            return 0

    # Hardcoded fallback — only used when CSV is not available
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
        ("добрий ранок", "good morning", "A2"), ("сім'я", "family", "A2"),
        ("книга", "book", "A2"), ("стіл", "table", "A2"), ("машина", "car", "A2"),
        ("любов", "love", "A2"), ("час", "time", "A2"), ("робота", "work", "A2"),
        ("незважаючи на", "despite", "B1"), ("однак", "however", "B1"),
        ("отже", "therefore", "B1"), ("досвід", "experience", "B1"),
        ("суспільство", "society", "B1"), ("уряд", "government", "B1"),
        ("освіта", "education", "B1"), ("наука", "science", "B1"),
        ("впливати", "influence", "B2"), ("забезпечувати", "provide", "B2"),
        ("розглядати", "consider", "B2"), ("дослідження", "research", "B2"),
        ("значний", "significant", "B2"), ("стратегія", "strategy", "B2"),
        ("відшкодування", "compensation", "C1"), ("передумова", "prerequisite", "C1"),
        ("двозначність", "ambiguity", "C1"), ("парадокс", "paradox", "C1"),
        ("безпрецедентний", "unprecedented", "C2"), ("квінтесенція", "quintessence", "C2"),
        ("дихотомія", "dichotomy", "C2"), ("фундаментальний", "fundamental", "C2"),
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

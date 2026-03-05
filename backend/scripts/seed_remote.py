#!/usr/bin/env python3
"""
Seed the remote Supabase database directly from your local machine.

Usage:
    cd backend
    python scripts/seed_remote.py

This reads seeds/dmklinger_processed.csv and inserts all words + dictionary
entries into the production Supabase PostgreSQL database.

It uses the DATABASE_URL from .env (or you can pass it via environment).
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend/ is on the path so we can import app.config if needed
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
except ImportError:
    pass  # dotenv not required if DATABASE_URL is set in env

from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
POS_MAP = {
    "n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb",
    "prep": "preposition", "conj": "conjunction", "pron": "pronoun",
    "num": "numeral", "pref": "prefix", "suf": "suffix", "int": "interjection",
}
BATCH_SIZE = 2000
CSV_PATH = BACKEND_DIR / "seeds" / "dmklinger_processed.csv"


def _normalize_url(raw: str) -> str:
    """Ensure we use the psycopg2 driver and sslmode=require."""
    raw = raw.strip().strip("'\"")
    if "://" not in raw:
        raise ValueError(f"Invalid DATABASE_URL: {raw}")
    scheme, suffix = raw.split("://", 1)
    scheme = scheme.lower()
    if scheme in {"postgres", "postgresql", "postgresql+psycopg",
                   "postgresql+asyncpg", "postgresql+pg8000",
                   "postgresql+psycopg2"}:
        url = f"postgresql+psycopg2://{suffix}"
    else:
        url = raw
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def _make_word_id(en: str) -> str:
    slug = en.lower().replace(" ", "_").replace("'", "")
    if len(slug) > 56:
        slug = slug[:52] + hashlib.md5(en.encode()).hexdigest()[:4]
    return slug[:64]


def _expand_pos(raw: str) -> str:
    cleaned = raw.strip().lower()
    return POS_MAP.get(cleaned, cleaned)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set. Check your .env or environment.")
        sys.exit(1)

    database_url = _normalize_url(database_url)
    print(f"Connecting to: {database_url[:40]}...")

    engine = create_engine(database_url, pool_pre_ping=True)

    # --- Verify connection and schema ---
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        print(f"✅ Database connection OK (SELECT 1 = {result})")

        # Check tables exist
        tables = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )).scalars().all()
        print(f"Tables in public schema: {tables}")

        if "words" not in tables:
            print("❌ 'words' table does not exist! Run alembic migrations first.")
            sys.exit(1)
        if "dictionary_entries" not in tables:
            print("❌ 'dictionary_entries' table does not exist! Run alembic migrations first.")
            sys.exit(1)

        word_count = conn.execute(text("SELECT COUNT(*) FROM words")).scalar()
        dict_count = conn.execute(text("SELECT COUNT(*) FROM dictionary_entries")).scalar()
        print(f"Current counts: {word_count} words, {dict_count} dictionary_entries")

    if not CSV_PATH.exists():
        print(f"❌ CSV not found at {CSV_PATH}")
        sys.exit(1)

    print(f"Reading CSV from {CSV_PATH}...")

    # --- Read CSV ---
    word_rows: list[dict] = []
    dict_rows: list[dict] = []
    seen_word_ids: set[str] = set()

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
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

            dict_rows.append({
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
                word_rows.append({
                    "id": word_id,
                    "ua": ua,
                    "en": en,
                    "level": level,
                    "definition": definition,
                    "example": example,
                })

    print(f"Parsed CSV: {len(word_rows)} unique words, {len(dict_rows)} dictionary entries")

    if not word_rows:
        print("❌ No rows parsed from CSV!")
        sys.exit(1)

    # --- Clear and insert ---
    word_sql = text(
        "INSERT INTO words (id, ua, en, level, definition, example) "
        "VALUES (:id, :ua, :en, :level, :definition, :example) "
        "ON CONFLICT (id) DO UPDATE SET ua = EXCLUDED.ua, en = EXCLUDED.en, "
        "level = EXCLUDED.level, definition = EXCLUDED.definition, example = EXCLUDED.example"
    )

    dict_sql = text(
        "INSERT INTO dictionary_entries (ua_word, en_word, part_of_speech, source, definition, example, created_at) "
        "VALUES (:ua_word, :en_word, :part_of_speech, :source, :definition, :example, :created_at) "
        "ON CONFLICT (ua_word, en_word) DO UPDATE SET "
        "definition = EXCLUDED.definition, example = EXCLUDED.example, source = EXCLUDED.source"
    )

    print("Inserting words...")
    with engine.begin() as conn:
        for i in range(0, len(word_rows), BATCH_SIZE):
            batch = word_rows[i:i + BATCH_SIZE]
            conn.execute(word_sql, batch)
            print(f"  words: {min(i + BATCH_SIZE, len(word_rows))}/{len(word_rows)}")

    print("Inserting dictionary entries...")
    with engine.begin() as conn:
        for i in range(0, len(dict_rows), BATCH_SIZE):
            batch = dict_rows[i:i + BATCH_SIZE]
            conn.execute(dict_sql, batch)
            print(f"  dict_entries: {min(i + BATCH_SIZE, len(dict_rows))}/{len(dict_rows)}")

    # --- Verify ---
    with engine.connect() as conn:
        final_words = conn.execute(text("SELECT COUNT(*) FROM words")).scalar()
        final_dict = conn.execute(text("SELECT COUNT(*) FROM dictionary_entries")).scalar()
        print(f"\n✅ DONE! Final counts: {final_words} words, {final_dict} dictionary_entries")

        # Show sample
        sample = conn.execute(
            text("SELECT id, ua, en, level FROM words ORDER BY RANDOM() LIMIT 5")
        ).fetchall()
        print("\nSample words:")
        for row in sample:
            print(f"  {row[0]:30s} | {row[1]:20s} | {row[2]:20s} | {row[3]}")


if __name__ == "__main__":
    main()

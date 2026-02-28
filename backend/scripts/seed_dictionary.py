from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.models import DictionaryEntry  # noqa: E402
from db import get_db, get_engine  # noqa: E402


def chunked_rows(csv_path: Path, chunk_size: int) -> Iterator[list[dict[str, str | None]]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        chunk: list[dict[str, str | None]] = []
        for row in reader:
            ua_word = (row.get("ua_word") or "").strip().lower()
            en_word = (row.get("en_word") or "").strip().lower()
            source = (row.get("source") or "").strip().lower()
            part_of_speech = (row.get("part_of_speech") or "").strip().lower() or None

            if not ua_word or not en_word or not source:
                continue

            chunk.append(
                {
                    "ua_word": ua_word,
                    "en_word": en_word,
                    "part_of_speech": part_of_speech,
                    "source": source,
                }
            )
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def maybe_prepare_dataset(csv_path: Path, repo_url: str, should_prepare: bool) -> None:
    if csv_path.exists() and not should_prepare:
        return

    root_dir = Path(__file__).resolve().parents[2]
    prepare_script = root_dir / "backend" / "scripts" / "prepare_dictionary.py"
    cmd = [sys.executable, str(prepare_script), "--repo-url", repo_url, "--output", str(csv_path.relative_to(root_dir))]
    subprocess.run(cmd, check=True)


def current_dictionary_size() -> int:
    with get_db() as session:
        return int(session.execute(text("SELECT COUNT(*) FROM dictionary_entries")).scalar_one())


def insert_chunk(rows: list[dict[str, str | None]]) -> int:
    if not rows:
        return 0

    table = DictionaryEntry.__table__
    dialect_name = get_engine().dialect.name

    with get_db() as session:
        if dialect_name == "postgresql":
            statement = pg_insert(table).values(rows)
            statement = statement.on_conflict_do_nothing(index_elements=["ua_word", "en_word"])
        elif dialect_name == "sqlite":
            statement = sqlite_insert(table).values(rows)
            statement = statement.on_conflict_do_nothing(index_elements=["ua_word", "en_word"])
        else:
            statement = table.insert().values(rows)

        result = session.execute(statement)
        if result.rowcount is None or result.rowcount < 0:
            return 0
        return int(result.rowcount)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dictionary_entries from cleaned CSV")
    parser.add_argument("--csv", default="backend/data/processed/dictionary_clean.csv")
    parser.add_argument(
        "--repo-url",
        default=os.getenv("DICTIONARY_REPO_URL", "https://github.com/pavlo-liapin/kindle-eng-ukr-dictionary.git"),
    )
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--prepare", action="store_true", help="Regenerate cleaned CSV before seeding")
    parser.add_argument("--force", action="store_true", help="Seed even if table already has rows")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[2]
    csv_path = (root_dir / args.csv).resolve()
    maybe_prepare_dataset(csv_path=csv_path, repo_url=args.repo_url, should_prepare=args.prepare)

    if not csv_path.exists():
        raise FileNotFoundError(f"Processed CSV not found: {csv_path}")

    existing_count = current_dictionary_size()
    if existing_count > 0 and not args.force:
        print(f"dictionary_entries already has {existing_count} rows; skipping seed (use --force to reseed).")
        return

    inserted_total = 0
    chunks_processed = 0
    for chunk in chunked_rows(csv_path=csv_path, chunk_size=max(1, args.chunk_size)):
        inserted_total += insert_chunk(chunk)
        chunks_processed += 1

    total_after = current_dictionary_size()
    print(f"Processed chunks: {chunks_processed}")
    print(f"Inserted rows in this run: {inserted_total}")
    print(f"Total rows in dictionary_entries: {total_after}")


if __name__ == "__main__":
    main()

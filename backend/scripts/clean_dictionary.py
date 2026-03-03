"""
One-time dictionary cleanup script.

1. Remove entries where English translation contains 2+ words (articles don't count).
2. Output cleaned CSV.

Usage:
    python scripts/clean_dictionary.py [input_csv] [output_csv]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


# Articles that don't count as "real" words
_ARTICLES = {"a", "an", "the"}


def is_multi_word(en_word: str) -> bool:
    """Return True if the English phrase has 2+ meaningful words (ignoring articles)."""
    cleaned = en_word.strip().lower()
    # Remove articles
    words = [w for w in cleaned.split() if w not in _ARTICLES]
    return len(words) >= 2


def clean_csv(input_path: str, output_path: str) -> None:
    kept = 0
    removed = 0
    with open(input_path, encoding="utf-8-sig") as f_in, \
         open(output_path, "w", encoding="utf-8", newline="") as f_out:
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)

        # Peek at first row to check for header
        first_row = next(reader, None)
        if first_row is None:
            print("Empty CSV file.")
            return

        # Detect header
        first_lower = [c.strip().lower() for c in first_row]
        header_keywords = {"ua_word", "en_word", "word", "source", "part_of_speech", "pos", "level", "ua", "en"}
        is_header = any(kw in header_keywords for kw in first_lower)

        if is_header:
            writer.writerow(first_row)  # preserve header
        else:
            # First row is data — process it
            if len(first_row) >= 2:
                en_word = first_row[1].strip()
                if is_multi_word(en_word):
                    removed += 1
                else:
                    writer.writerow(first_row)
                    kept += 1

        for row in reader:
            if len(row) < 2:
                continue
            en_word = row[1].strip()
            if is_multi_word(en_word):
                removed += 1
                continue
            writer.writerow(row)
            kept += 1

    print(f"✅ Kept: {kept}, Removed: {removed}")
    print(f"   Output: {output_path}")


def main() -> None:
    default_input = Path(__file__).parent.parent / "data" / "processed" / "dictionary_clean.csv"
    default_output = Path(__file__).parent.parent / "data" / "processed" / "dictionary_clean_filtered.csv"

    input_path = sys.argv[1] if len(sys.argv) > 1 else str(default_input)
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(default_output)

    if not Path(input_path).exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    clean_csv(input_path, output_path)


if __name__ == "__main__":
    main()

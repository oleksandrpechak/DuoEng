"""
Process dmklinger/ukrainian dictionary into a clean CSV for DuoVocab Duel.

Source: https://github.com/dmklinger/ukrainian
Format: words.json — 30k Ukrainian words with English definitions, POS, frequency.

Pipeline:
  1. Clone repo (if not already cloned)
  2. Parse words.json — extract (ua_word, en_word, pos, freq)
  3. Filter to single-word pairs only
  4. Assign CEFR levels based on word frequency
  5. Save to seeds/dmklinger_processed.csv

Usage:
    cd backend
    python -m seeds.process_dmklinger
"""

from __future__ import annotations

import csv
import json
import logging
import re
import subprocess
from collections import Counter
from pathlib import Path

logger = logging.getLogger("seeds.process_dmklinger")

REPO_URL = "https://github.com/dmklinger/ukrainian.git"
REPO_PATH = Path("/tmp/dmklinger_ukrainian")
OUTPUT_CSV = Path(__file__).parent / "dmklinger_processed.csv"

# ──────────────────────────────────────────────────────────────────
# CEFR assignment by frequency rank (the repo is pre-sorted by freq)
# ──────────────────────────────────────────────────────────────────
LEVEL_BUCKETS = [
    # (cumulative fraction of total, level)
    (0.05, "A1"),   # top 5%
    (0.12, "A2"),   # next 7%
    (0.30, "B1"),   # next 18%
    (0.55, "B2"),   # next 25%
    (0.80, "C1"),   # next 25%
    (1.00, "C2"),   # remaining 20%
]

# Words that should always be A1 regardless of frequency position
FORCE_A1 = {
    "be", "have", "do", "say", "get", "make", "go", "know", "take", "see",
    "come", "think", "look", "want", "give", "use", "find", "tell", "ask",
    "work", "feel", "try", "leave", "call", "good", "new", "big", "small",
    "house", "school", "family", "water", "food", "name", "day", "night",
    "mother", "father", "child", "friend", "city", "car", "dog", "cat",
    "book", "table", "door", "bed", "room", "love", "time", "year",
    "man", "woman", "boy", "girl", "one", "two", "three", "yes", "no",
    "I", "you", "he", "she", "we", "they", "not", "and", "but", "or",
}


# ──────────────────────────────────────────────────────────────────
# Step 1 — Clone repo
# ──────────────────────────────────────────────────────────────────

def clone_repo() -> bool:
    if (REPO_PATH / "words.json").exists():
        logger.info("words.json already present at %s", REPO_PATH)
        return True
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", REPO_URL, str(REPO_PATH)],
            check=True,
            capture_output=True,
        )
        logger.info("Cloned repo to %s", REPO_PATH)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to clone repo: %s", e.stderr.decode()[:200])
        return False


# ──────────────────────────────────────────────────────────────────
# Step 2 — Parse words.json
# ──────────────────────────────────────────────────────────────────

# Regex: strip ONLY combining acute accent (U+0301) — the stress marker.
# Do NOT strip the broad U+0300–U+036F range — that would destroy ї (і + U+0308).
_ACCENT_RE = re.compile("\u0301")


def _strip_accents(word: str) -> str:
    """Remove stress marks from Ukrainian words (e.g. бу́ти → бути).

    Only removes U+0301 (combining acute accent).
    Preserves ї, ё, and other legitimate diacritical letters.
    """
    return _ACCENT_RE.sub("", word).strip()


def _extract_best_en(defs: list[str]) -> str | None:
    """Extract the cleanest single English word from the definitions list.

    Tries each definition in order, stripping parenthetical context.
    Returns the first clean single-word English translation found.
    """
    for d in defs:
        # Remove parenthetical context: "house (building)" → "house"
        clean = re.sub(r"\s*\([^)]*\)\s*", "", d).strip()
        if clean and " " not in clean and re.match(r"^[a-zA-Z-]+$", clean):
            return clean.lower()

    # Fallback: extract just the first English word from def[0]
    if defs:
        m = re.match(r"^([a-zA-Z-]{2,})", defs[0].strip())
        if m:
            return m.group(1).lower()

    return None


# POS skip list — not useful for a vocabulary game
_SKIP_POS = {"particle", "phrase", "proverb", "symbol", "interfix",
             "abbreviations", "combining form"}


def parse_words_json() -> list[dict]:
    """Parse words.json into list of {ua, en, pos, freq} dicts."""
    json_path = REPO_PATH / "words.json"
    if not json_path.exists():
        logger.error("words.json not found at %s", json_path)
        return []

    with open(json_path, encoding="utf-8") as f:
        raw: list[dict] = json.load(f)

    logger.info("Loaded %d raw entries from words.json", len(raw))

    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in raw:
        ua_raw: str = item.get("word", "")
        pos: str = item.get("pos", "")
        defs: list[str] = item.get("defs", [])
        freq = item.get("freq")

        # Strip accents
        ua = _strip_accents(ua_raw)

        # Basic validation
        if not ua or len(ua) < 2:
            continue
        # Skip multi-word Ukrainian entries
        if " " in ua:
            continue
        # Skip POS we don't want in a vocab game
        if pos in _SKIP_POS:
            continue
        # Must have definitions
        if not defs:
            continue

        # Extract the best single-word English translation
        en = _extract_best_en(defs)
        if not en or len(en) < 2:
            continue
        # Skip multi-word English
        if " " in en:
            continue

        # Normalise POS
        pos_normalised = {
            "adj": "adjective",
            "participle": "adjective",
        }.get(pos, pos)

        # Deduplicate by (ua, en) pair
        key = (ua.lower(), en.lower())
        if key in seen:
            continue
        seen.add(key)

        entries.append({
            "ua": ua,
            "en": en,
            "pos": pos_normalised,
            "freq": freq,
        })

    logger.info("Parsed %d clean single-word entries", len(entries))
    return entries


# ──────────────────────────────────────────────────────────────────
# Step 3 — Assign CEFR levels
# ──────────────────────────────────────────────────────────────────

def assign_levels(entries: list[dict]) -> list[dict]:
    """Assign CEFR levels based on frequency rank.

    Entries with freq=None are placed at C2.
    The FORCE_A1 set overrides any frequency-based assignment.
    """
    # Sort by frequency (lower = more common).  None → end.
    sorted_entries = sorted(entries, key=lambda e: (e["freq"] is None, e["freq"] or 999999))
    total = len(sorted_entries)

    for i, entry in enumerate(sorted_entries):
        en_lower = entry["en"].lower()

        # Override for known basic words
        if en_lower in FORCE_A1:
            entry["level"] = "A1"
            continue

        # No frequency data → C2
        if entry["freq"] is None:
            entry["level"] = "C2"
            continue

        # Assign by position in sorted list
        ratio = i / total
        for threshold, level in LEVEL_BUCKETS:
            if ratio <= threshold:
                entry["level"] = level
                break
        else:
            entry["level"] = "C2"

    return sorted_entries


# ──────────────────────────────────────────────────────────────────
# Step 4 — Save to CSV
# ──────────────────────────────────────────────────────────────────

FIELDNAMES = ["ua_word", "en_word", "part_of_speech", "level"]


def save_csv(entries: list[dict]) -> None:
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "ua_word": e["ua"],
                "en_word": e["en"],
                "part_of_speech": e["pos"],
                "level": e["level"],
            })
    logger.info("Saved %d entries to %s", len(entries), OUTPUT_CSV)


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if OUTPUT_CSV.exists():
        line_count = sum(1 for _ in open(OUTPUT_CSV)) - 1
        if line_count > 100:
            print(f"✅ {OUTPUT_CSV.name} already exists with {line_count} entries.")
            print("   Delete it to re-run.")
            return

    print("📥 Step 1: Cloning dmklinger/ukrainian...")
    if not clone_repo():
        return

    print("📖 Step 2: Parsing words.json...")
    entries = parse_words_json()
    if not entries:
        print("❌ No entries parsed. Check the repo structure.")
        return
    print(f"   {len(entries)} clean single-word entries")

    print("🏷️  Step 3: Assigning CEFR levels...")
    levelled = assign_levels(entries)

    print("💾 Step 4: Saving to CSV...")
    save_csv(levelled)

    # Summary
    level_counts = Counter(e["level"] for e in levelled)
    pos_counts = Counter(e["pos"] for e in levelled)

    print(f"""
✅ Done! {len(levelled)} words saved to {OUTPUT_CSV.name}

  CEFR levels:
    A1: {level_counts.get("A1", 0)}
    A2: {level_counts.get("A2", 0)}
    B1: {level_counts.get("B1", 0)}
    B2: {level_counts.get("B2", 0)}
    C1: {level_counts.get("C1", 0)}
    C2: {level_counts.get("C2", 0)}

  POS breakdown (top 8):""")
    for pos_name, count in pos_counts.most_common(8):
        print(f"    {pos_name or '(none)'}: {count}")


if __name__ == "__main__":
    main()

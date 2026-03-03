"""
Process Oxford 5000 words:
1. Parse the Oxford 5000 dataset from the cloned repo
2. Translate each word to Ukrainian using Anthropic Claude
3. Filter out multi-word translations
4. Save to seeds/oxford_processed.csv
5. (Seeding into DB is handled by db.py at startup)

Usage:
    export ANTHROPIC_API_KEY=your_key_here
    git clone https://github.com/winterdl/oxford-5000-vocabulary-audio-definition.git /tmp/oxford5000
    cd backend
    python -m seeds.process_oxford
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path

import httpx

logger = logging.getLogger("seeds.process_oxford")

OXFORD_REPO_PATH = Path(os.environ.get("OXFORD_REPO_PATH", "/tmp/oxford5000"))
OUTPUT_CSV = Path(__file__).parent / "oxford_processed.csv"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Read API key from environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")

VALID_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}

# POS normalisation
POS_NORMALISE: dict[str, str] = {
    "indefinite article": "article",
    "modal verb": "verb",
    "auxiliary verb": "verb",
    "linking verb": "verb",
    "ordinal number": "number",
    "exclamation": "interjection",
}


# ---------------------------------------------------------------------------
# Step 1 — Parse Oxford 5000 data
# ---------------------------------------------------------------------------

def parse_oxford_data() -> list[dict]:
    """Parse Oxford 5000 repo into list of {word, level, pos, definition}."""
    words: list[dict] = []

    # Try JSON first (richer structure), fall back to CSV
    json_path = OXFORD_REPO_PATH / "data" / "oxford_5000.json"
    csv_path = OXFORD_REPO_PATH / "data" / "oxford_5000.csv"

    if json_path.exists():
        logger.info("Parsing Oxford JSON: %s", json_path)
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        items = data.values() if isinstance(data, dict) else data

        for item in items:
            word = (item.get("word") or "").strip().lower()
            level = (item.get("cefr") or "B1").strip().upper()
            pos = (item.get("type") or "").strip().lower()
            definition = (item.get("definition") or "").strip()
            example = (item.get("example") or "").strip()

            if not word:
                continue
            # Skip multi-word entries
            if " " in word:
                continue
            # Skip articles, determiners, pronouns — not useful for vocab game
            if pos in ("indefinite article", "determiner"):
                continue

            if level not in VALID_CEFR:
                level = "B1"

            # Normalise POS
            pos = POS_NORMALISE.get(pos, pos)

            words.append({
                "word": word,
                "level": level,
                "pos": pos,
                "definition": definition,
                "example": example,
            })

    elif csv_path.exists():
        logger.info("Parsing Oxford CSV: %s", csv_path)
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                word = (row.get("word") or "").strip().lower()
                level = (row.get("cefr") or "B1").strip().upper()
                pos = (row.get("type") or "").strip().lower()
                definition = (row.get("definition") or "").strip()
                example = (row.get("example") or "").strip()

                if not word or " " in word:
                    continue
                if pos in ("indefinite article", "determiner"):
                    continue
                if level not in VALID_CEFR:
                    level = "B1"
                pos = POS_NORMALISE.get(pos, pos)

                words.append({
                    "word": word,
                    "level": level,
                    "pos": pos,
                    "definition": definition,
                    "example": example,
                })
    else:
        logger.error(
            "Oxford 5000 data not found. Expected JSON at %s or CSV at %s",
            json_path, csv_path,
        )
        return []

    # De-duplicate by word (keep first occurrence = higher-frequency sense)
    seen: set[str] = set()
    unique: list[dict] = []
    for w in words:
        if w["word"] not in seen:
            seen.add(w["word"])
            unique.append(w)

    logger.info("Parsed %d unique Oxford words (from %d total entries)", len(unique), len(words))
    return unique


# ---------------------------------------------------------------------------
# Step 2 — Translate batches using Claude
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # exponential base


async def translate_batch(
    words_batch: list[dict],
    client: httpx.AsyncClient,
) -> list[dict]:
    """Translate a batch of English words to Ukrainian using Claude.

    Returns list of dicts with added 'ua_word' key.
    Includes retry logic with exponential backoff.
    """
    word_list = "\n".join(
        f"{i + 1}. {w['word']} ({w['pos']})"
        for i, w in enumerate(words_batch)
    )

    prompt = (
        "Translate these English words to Ukrainian.\n"
        "Rules:\n"
        "- Provide ONLY single Ukrainian words (no phrases, no articles, no multi-word translations)\n"
        "- If a word has multiple meanings, use the most common everyday meaning\n"
        "- If a single-word translation is impossible, write \"SKIP\"\n"
        "- Reply ONLY with a numbered list matching the input, format: \"1. слово\"\n"
        "- Do NOT add any explanation or additional text\n\n"
        f"Words to translate:\n{word_list}"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )

            if response.status_code == 429:
                # Rate limited — back off more aggressively
                wait = RETRY_BACKOFF ** attempt * 2
                logger.warning("Rate limited (429), retrying in %.1fs (attempt %d/%d)", wait, attempt, MAX_RETRIES)
                await asyncio.sleep(wait)
                continue

            if response.status_code != 200:
                logger.error("API error %d: %s", response.status_code, response.text[:200])
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)
                    continue
                return []

            text_body = response.json()["content"][0]["text"]
            lines = text_body.strip().split("\n")

            results: list[dict] = []
            for i, line in enumerate(lines):
                if i >= len(words_batch):
                    break
                # Parse "1. слово" format
                match = re.match(r"^\d+\.\s*(.+)$", line.strip())
                if match:
                    ua_word = match.group(1).strip()
                    # Skip invalid translations
                    if ua_word.upper() == "SKIP":
                        continue
                    if " " in ua_word:
                        continue
                    # Basic validation: must contain at least one Cyrillic char
                    if not re.search(r"[а-яіїєґ]", ua_word, re.IGNORECASE):
                        continue

                    results.append({
                        **words_batch[i],
                        "ua_word": ua_word.lower(),
                    })

            return results

        except httpx.TimeoutException:
            logger.warning("Timeout on attempt %d/%d", attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF ** attempt)
                continue
            return []
        except Exception as e:
            logger.error("Translation batch failed (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF ** attempt)
                continue
            return []

    return []


async def translate_all_words(oxford_words: list[dict]) -> list[dict]:
    """Translate all Oxford words to Ukrainian in batches."""
    BATCH_SIZE = 50
    RATE_LIMIT_DELAY = 1.5  # seconds between batches

    translated: list[dict] = []
    total_batches = (len(oxford_words) + BATCH_SIZE - 1) // BATCH_SIZE
    failed_batches = 0

    async with httpx.AsyncClient() as client:
        for i in range(0, len(oxford_words), BATCH_SIZE):
            batch = oxford_words[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            logger.info(
                "Translating batch %d/%d (%d words)...",
                batch_num, total_batches, len(batch),
            )

            results = await translate_batch(batch, client)
            if results:
                translated.extend(results)
                logger.info(
                    "Batch %d done: %d/%d translated (total: %d)",
                    batch_num, len(results), len(batch), len(translated),
                )
            else:
                failed_batches += 1
                logger.warning("Batch %d returned 0 results", batch_num)

            # Rate limiting
            if i + BATCH_SIZE < len(oxford_words):
                await asyncio.sleep(RATE_LIMIT_DELAY)

    logger.info(
        "Translation complete: %d/%d words translated (%d batches failed)",
        len(translated), len(oxford_words), failed_batches,
    )
    return translated


# ---------------------------------------------------------------------------
# Step 3 — Save / Load CSV
# ---------------------------------------------------------------------------

def save_to_csv(words: list[dict], output_path: Path) -> None:
    """Save processed words to CSV (includes definition + example from Oxford)."""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ua_word", "en_word", "level", "part_of_speech", "definition", "example"])
        for w in words:
            writer.writerow([
                w["ua_word"],
                w["word"],
                w["level"],
                w.get("pos", ""),
                w.get("definition", ""),
                w.get("example", ""),
            ])
    logger.info("Saved %d words to %s", len(words), output_path)


def csv_already_exists_and_valid(min_lines: int = 1000) -> bool:
    """Check if the output CSV already exists with enough data."""
    if not OUTPUT_CSV.exists():
        return False
    try:
        with open(OUTPUT_CSV, encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
        if line_count > min_lines:
            logger.info(
                "oxford_processed.csv already exists with %d lines — skipping translation",
                line_count,
            )
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if csv_already_exists_and_valid():
        print(f"✅ {OUTPUT_CSV} already exists and has >1000 lines. Skipping.")
        print("   Delete the file manually if you want to re-translate.")
        return

    if not ANTHROPIC_API_KEY:
        print("❌ ERROR: Set ANTHROPIC_API_KEY (or LLM_API_KEY) environment variable")
        return

    if not OXFORD_REPO_PATH.exists():
        print(f"❌ ERROR: Oxford repo not found at {OXFORD_REPO_PATH}")
        print("   Run: git clone https://github.com/winterdl/oxford-5000-vocabulary-audio-definition.git /tmp/oxford5000")
        return

    # Step 1: Parse Oxford data
    print("📖 Step 1: Parsing Oxford 5000 data...")
    oxford_words = parse_oxford_data()
    print(f"   Found {len(oxford_words)} single-word entries")

    if not oxford_words:
        print("❌ ERROR: No words parsed from Oxford repo. Check the repo structure.")
        return

    # Step 2: Translate to Ukrainian
    estimated_minutes = len(oxford_words) / 50 * 1.5 / 60
    print(f"🌐 Step 2: Translating to Ukrainian (~{estimated_minutes:.0f} minutes for {len(oxford_words)} words)...")
    start_time = time.time()
    translated = await translate_all_words(oxford_words)
    elapsed = time.time() - start_time
    print(f"   Translated {len(translated)} words in {elapsed:.0f}s")

    if not translated:
        print("❌ ERROR: Translation returned 0 results")
        return

    # Step 3: Save to CSV
    print("💾 Step 3: Saving to CSV...")
    save_to_csv(translated, OUTPUT_CSV)

    # Summary
    print(f"\n✅ Done! {len(translated)} words saved to {OUTPUT_CSV}")
    print("\nLevel distribution:")
    levels = Counter(w["level"] for w in translated)
    for level in ("A1", "A2", "B1", "B2", "C1"):
        print(f"  {level}: {levels.get(level, 0)}")

    print("\nPOS distribution:")
    pos_counts = Counter(w.get("pos", "") for w in translated)
    for p, c in pos_counts.most_common(10):
        print(f"  {p or '(none)'}: {c}")


if __name__ == "__main__":
    asyncio.run(main())

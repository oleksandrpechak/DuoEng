"""
Enrich oxford_processed.csv with copyright-free definitions and examples.

Pipeline (per word):
  1. Try Free Dictionary API  (instant, free, no AI cost)
  2. AI-rewrite fallback      (if word not found in free API)
  3. AI-generate from scratch (if no original definition to rewrite)
  4. Leave empty              (if both fail — never block seeding)

Output: seeds/oxford_enriched.csv

Usage:
    export ANTHROPIC_API_KEY=your_key_here
    cd backend
    python -m seeds.enrich_definitions
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger("seeds.enrich_definitions")

INPUT_CSV = Path(__file__).parent / "oxford_processed.csv"
OUTPUT_CSV = Path(__file__).parent / "oxford_enriched.csv"
FREE_DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


# ─── Free Dictionary API ───────────────────────────────────────────

async def fetch_free_dictionary(word: str, client: httpx.AsyncClient) -> dict | None:
    """Fetch definition from dictionaryapi.dev — no API key needed."""
    try:
        url = FREE_DICT_API.format(word=word.lower().strip())
        resp = await client.get(url, timeout=8.0)

        if resp.status_code == 404:
            return None  # Word not found

        if resp.status_code != 200:
            logger.warning("Free dict API error %d for '%s'", resp.status_code, word)
            return None

        data = resp.json()
        if not data or not isinstance(data, list):
            return None

        entry = data[0]
        meanings = entry.get("meanings", [])
        if not meanings:
            return None

        # Get first meaning
        meaning = meanings[0]
        pos = meaning.get("partOfSpeech", "")
        definitions = meaning.get("definitions", [])

        if not definitions:
            return None

        first_def = definitions[0]
        definition = first_def.get("definition", "").strip()
        example = first_def.get("example", "").strip()

        # Clean up definition (remove HTML tags if any)
        definition = re.sub(r"<[^>]+>", "", definition)
        example = re.sub(r"<[^>]+>", "", example)

        if not definition:
            return None

        return {
            "definition": definition,
            "example": example or "",
            "pos": pos,
            "source": "free_dictionary_api",
        }

    except Exception as e:
        logger.error("Free dict API failed for '%s': %s", word, e)
        return None


# ─── AI Definition Generator ───────────────────────────────────────

async def ai_generate_definition(
    en_word: str,
    ua_word: str,
    pos: str,
    original_definition: str,
    original_example: str,
    client: httpx.AsyncClient,
) -> dict | None:
    """Use AI to rewrite an existing definition or generate a fresh one."""
    if not ANTHROPIC_API_KEY:
        return None

    if original_definition:
        prompt = (
            "Rewrite this English dictionary definition completely in your own words.\n"
            "Do NOT copy the original wording. Create a fresh, clear definition "
            "suitable for English learners.\n\n"
            f'Word: "{en_word}" ({pos})\n'
            f'Ukrainian translation: "{ua_word}"\n'
            f'Original definition (DO NOT COPY): "{original_definition}"\n'
            f'Original example (DO NOT COPY): "{original_example}"\n\n'
            "Reply ONLY with a JSON object, no markdown, no extra text:\n"
            '{"definition": "your rewritten definition here", '
            '"example": "your original example sentence using the word"}'
        )
    else:
        prompt = (
            "Write a simple English dictionary definition for this word.\n"
            "Suitable for B1-B2 English learners. Use clear, simple language.\n\n"
            f'Word: "{en_word}" ({pos})\n'
            f'Ukrainian translation: "{ua_word}"\n\n'
            "Reply ONLY with a JSON object, no markdown, no extra text:\n"
            '{"definition": "simple definition here", '
            '"example": "a natural example sentence using the word"}'
        )

    for attempt in range(1, 4):
        try:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=15.0,
            )

            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue

            if resp.status_code != 200:
                logger.warning("AI API error %d for '%s'", resp.status_code, en_word)
                return None

            text = resp.json()["content"][0]["text"].strip()
            # Strip markdown fences if present
            text = re.sub(r"^```json\s*|\s*```$", "", text.strip())
            parsed = json.loads(text)

            return {
                "definition": parsed.get("definition", "").strip(),
                "example": parsed.get("example", "").strip(),
                "source": "ai_generated",
            }

        except json.JSONDecodeError:
            logger.warning("AI returned invalid JSON for '%s'", en_word)
            return None
        except httpx.TimeoutException:
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except Exception as e:
            logger.error("AI definition failed for '%s': %s", en_word, e)
            return None

    return None


# ─── Batch AI processor ────────────────────────────────────────────

async def ai_generate_batch(
    words_batch: list[dict],
    client: httpx.AsyncClient,
) -> list[dict]:
    """Process a batch of words needing AI definitions concurrently."""
    tasks = [
        ai_generate_definition(
            en_word=word["en_word"],
            ua_word=word["ua_word"],
            pos=word.get("part_of_speech", ""),
            original_definition=word.get("original_definition", ""),
            original_example=word.get("original_example", ""),
            client=client,
        )
        for word in words_batch
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = []
    for word, result in zip(words_batch, results):
        if isinstance(result, Exception) or result is None:
            enriched.append({**word, "definition": "", "example": "", "def_source": "none"})
        else:
            enriched.append({
                **word,
                "definition": result["definition"],
                "example": result["example"],
                "def_source": result["source"],
            })
    return enriched


# ─── Main enrichment pipeline ──────────────────────────────────────

async def enrich_all_words() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not INPUT_CSV.exists():
        print(f"ERROR: {INPUT_CSV} not found. Run process_oxford.py first.")
        return

    # Read input CSV
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        words = list(reader)

    print(f"Loaded {len(words)} words from {INPUT_CSV.name}")
    print(f"Columns: {headers}")

    # ── Resumability: load already-enriched words ──
    already_done: dict[str, dict] = {}
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, encoding="utf-8-sig") as f:
            existing = list(csv.DictReader(f))
        if len(existing) >= len(words) * 0.95:
            print(f"Output already exists with {len(existing)} words. Delete {OUTPUT_CSV.name} to re-run.")
            return
        # Partial output — resume from where we left off
        for row in existing:
            key = row.get("en_word", "").strip().lower()
            if key:
                already_done[key] = row
        if already_done:
            print(f"Resuming: {len(already_done)} words already enriched, skipping them.")

    # Flexible column access
    def get_col(row: dict, *candidates: str) -> str:
        for c in candidates:
            if c in row and row[c]:
                return row[c]
        return ""

    FREE_DICT_DELAY = 0.3  # seconds between free API calls
    AI_CONCURRENT = 10  # concurrent AI calls
    AI_DELAY = 0.5  # seconds between AI batches

    enriched_words: list[dict] = list(already_done.values())
    free_api_hits = sum(1 for r in enriched_words if r.get("def_source") == "free_dictionary_api")
    ai_hits = sum(1 for r in enriched_words if r.get("def_source") == "ai_generated")
    no_definition = sum(1 for r in enriched_words if r.get("def_source") == "none")

    # Helper to save progress (enables safe interruption)
    output_fields = [
        "ua_word", "en_word", "level", "part_of_speech",
        "definition", "example", "def_source",
    ]

    def _save_checkpoint(data: list[dict]) -> None:
        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    async with httpx.AsyncClient() as client:

        # PASS 1: Free Dictionary API (fast, free)
        remaining = [w for w in words if get_col(w, "en_word", "en", "word", "english").strip().lower() not in already_done]
        print(f"\nPass 1: Free Dictionary API ({len(remaining)} words remaining, {len(already_done)} already done)...")
        needs_ai: list[dict] = []

        for i, row in enumerate(remaining):
            en_word = get_col(row, "en_word", "en", "word", "english").strip()
            ua_word = get_col(row, "ua_word", "ua", "ukrainian").strip()
            level = get_col(row, "level", "cefr").strip().upper() or "B1"
            pos = get_col(row, "part_of_speech", "pos").strip()
            orig_def = get_col(row, "definition", "def").strip()
            orig_example = get_col(row, "example", "sentence").strip()

            if not en_word or not ua_word:
                continue

            result = await fetch_free_dictionary(en_word, client)

            if result:
                enriched_words.append({
                    "ua_word": ua_word,
                    "en_word": en_word,
                    "level": level if level in ("A1", "A2", "B1", "B2", "C1", "C2") else "B1",
                    "part_of_speech": result["pos"] or pos,
                    "definition": result["definition"],
                    "example": result["example"],
                    "def_source": "free_dictionary_api",
                })
                free_api_hits += 1
            else:
                # Queue for AI processing
                needs_ai.append({
                    "ua_word": ua_word,
                    "en_word": en_word,
                    "level": level if level in ("A1", "A2", "B1", "B2", "C1", "C2") else "B1",
                    "part_of_speech": pos,
                    "original_definition": orig_def,
                    "original_example": orig_example,
                })

            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{len(remaining)} — {free_api_hits} from API, {len(needs_ai)} need AI")

            # Checkpoint every 200 words so progress survives interruption
            if (i + 1) % 200 == 0:
                _save_checkpoint(enriched_words)

            await asyncio.sleep(FREE_DICT_DELAY)

        # Save after Pass 1 completes
        _save_checkpoint(enriched_words)
        print(f"\nPass 1 complete: {free_api_hits} from Free Dictionary API, {len(needs_ai)} need AI")

        # PASS 2: AI for words not found in free API
        if needs_ai and ANTHROPIC_API_KEY:
            print(f"\nPass 2: AI definitions for {len(needs_ai)} words...")

            for i in range(0, len(needs_ai), AI_CONCURRENT):
                batch = needs_ai[i : i + AI_CONCURRENT]
                results = await ai_generate_batch(batch, client)

                for r in results:
                    if r.get("definition"):
                        ai_hits += 1
                    else:
                        no_definition += 1

                    enriched_words.append({
                        "ua_word": r["ua_word"],
                        "en_word": r["en_word"],
                        "level": r["level"],
                        "part_of_speech": r.get("part_of_speech", ""),
                        "definition": r.get("definition", ""),
                        "example": r.get("example", ""),
                        "def_source": r.get("def_source", "none"),
                    })

                batch_num = i // AI_CONCURRENT + 1
                total_batches = (len(needs_ai) + AI_CONCURRENT - 1) // AI_CONCURRENT
                print(f"  AI batch {batch_num}/{total_batches} done")

                # Checkpoint after each AI batch
                _save_checkpoint(enriched_words)

                await asyncio.sleep(AI_DELAY)

        elif needs_ai and not ANTHROPIC_API_KEY:
            print(f"WARNING: No ANTHROPIC_API_KEY set. {len(needs_ai)} words will have no definition.")
            for word in needs_ai:
                enriched_words.append({
                    "ua_word": word["ua_word"],
                    "en_word": word["en_word"],
                    "level": word["level"],
                    "part_of_speech": word.get("part_of_speech", ""),
                    "definition": "",
                    "example": "",
                    "def_source": "none",
                })
                no_definition += 1

    # Final save
    _save_checkpoint(enriched_words)

    print(f"""
Enrichment complete:
  Total words:        {len(enriched_words)}
  From Free Dict API: {free_api_hits}
  AI generated:       {ai_hits}
  No definition:      {no_definition}
  Output saved to:    {OUTPUT_CSV}
""")


if __name__ == "__main__":
    asyncio.run(enrich_all_words())

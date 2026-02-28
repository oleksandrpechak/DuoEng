from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from html import unescape
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Iterable
import zipfile


REPO_URL_DEFAULT = "https://github.com/pavlo-liapin/kindle-eng-ukr-dictionary.git"
SOURCE_EXTERNAL = "external"
SOURCE_VARCON = "varcon"

HEADWORD_SPLIT_RE = re.compile(r"[|,;/]")
HEADWORD_SANITIZE_RE = re.compile(r"[^a-z0-9'\\-\\s]")
TAG_RE = re.compile(r"<[^>]+>")
POS_RE = re.compile(r"<font color=\"green\">([^<]+)</font>", flags=re.IGNORECASE)
CYRILLIC_RE = re.compile(r"[а-яіїєґ]", flags=re.IGNORECASE)

POS_ALIASES = {
    "n": "n",
    "v": "v",
    "adj": "adj",
    "adv": "adv",
    "prep": "prep",
    "conj": "conj",
    "pron": "pron",
    "pref": "pref",
    "num": "num",
    "interj": "interj",
    "pl": "n",
}

UA_PREFIX_LABELS = {
    "n",
    "v",
    "adj",
    "adv",
    "conj",
    "prep",
    "pron",
    "pref",
    "num",
    "int",
    "pl",
    "розм",
    "заст",
    "рідко",
    "книжн",
    "поет",
    "ірон",
    "жарт",
    "вульг",
    "анат",
    "бот",
    "біол",
    "військ",
    "геогр",
    "екон",
    "мат",
    "мед",
    "мор",
    "муз",
    "політ",
    "тех",
    "фіз",
    "фін",
    "хім",
    "церк",
    "юр",
    "ч",
    "ж",
    "імя",
    "скор",
    "від",
    "див",
    "тж",
}


@dataclass(frozen=True)
class AssetDetection:
    path: Path
    file_format: str


def run_command(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def clone_repository(repo_url: str, clone_to: Path) -> Path:
    repo_dir = clone_to / "kindle-eng-ukr-dictionary"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    run_command(["git", "clone", "--depth", "1", repo_url, str(repo_dir)])
    return repo_dir


def detect_assets(repo_dir: Path) -> tuple[AssetDetection, AssetDetection]:
    dictionary_candidates: list[AssetDetection] = []
    varcon_candidates: list[AssetDetection] = []

    for path in repo_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".txt", ".csv", ".dic", ".zip"}:
            continue

        lower_name = path.name.lower()
        if "varcon" in lower_name:
            varcon_candidates.append(AssetDetection(path=path, file_format=suffix.lstrip(".")))

        if any(token in lower_name for token in ("eng-ukr", "dictionary", "balla")):
            dictionary_candidates.append(AssetDetection(path=path, file_format=suffix.lstrip(".")))

    if not dictionary_candidates:
        raise RuntimeError("Dictionary source file was not found in external repository")
    if not varcon_candidates:
        raise RuntimeError("VarCon source file was not found in external repository")

    dictionary_asset = sorted(dictionary_candidates, key=lambda item: item.path.name)[0]
    varcon_asset = sorted(varcon_candidates, key=lambda item: item.path.name)[0]
    return dictionary_asset, varcon_asset


def extract_text_from_zip(zip_path: Path, marker: str, to_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        text_members = [name for name in archive.namelist() if name.lower().endswith(".txt")]
        if not text_members:
            raise RuntimeError(f"No .txt members in archive: {zip_path}")

        preferred = [name for name in text_members if marker in name.lower()]
        member = preferred[0] if preferred else text_members[0]
        output_path = to_dir / Path(member).name
        with archive.open(member) as source, output_path.open("wb") as target:
            target.write(source.read())
        return output_path


def normalize_headwords(raw_headword: str) -> list[str]:
    headword = unescape(raw_headword)
    headword = headword.replace("{", "").replace("}", "")
    headword = headword.replace("<<", "").replace(">>", "")
    headword = re.sub(r"\(.*?\)", " ", headword)
    headword = re.sub(r"\s+", " ", headword).strip()

    normalized: set[str] = set()
    for token in HEADWORD_SPLIT_RE.split(headword):
        candidate = token.strip().lower()
        candidate = HEADWORD_SANITIZE_RE.sub("", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if not candidate:
            continue
        if len(candidate) > 80:
            continue
        if not re.search(r"[a-z]", candidate):
            continue
        normalized.add(candidate)
    return sorted(normalized)


def extract_part_of_speech(raw_definition: str) -> str | None:
    for match in POS_RE.findall(raw_definition):
        token = match.strip().lower().replace(".", "")
        token = token.split()[0]
        mapped = POS_ALIASES.get(token)
        if mapped:
            return mapped
    return None


def extract_ua_terms(raw_definition: str) -> list[str]:
    text = raw_definition.replace("\\n", "\n")
    text = unescape(text)
    text = re.sub(r"\[m\d+\]", " ", text)
    text = text.replace("<<", " ").replace(">>", " ")
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\b\d+\)", ";", text)
    text = text.replace("—", ";")
    text = text.replace("–", ";")
    text = re.sub(r"\s+", " ", text).strip()

    unique: list[str] = []
    seen: set[str] = set()

    for chunk in re.split(r"[;]", text):
        for part in chunk.split(","):
            candidate = re.sub(r"\([^)]*\)", " ", part)
            candidate = re.sub(r"\s+", " ", candidate).strip(" .:-").lower()
            if not candidate:
                continue
            if candidate.startswith("скор. від") or candidate.startswith("див."):
                continue

            words = candidate.split()
            while words:
                normalized = re.sub(r"[^a-zа-яіїєґ0-9]", "", words[0], flags=re.IGNORECASE)
                if not normalized:
                    words.pop(0)
                    continue
                if normalized in UA_PREFIX_LABELS or re.fullmatch(r"[a-z]+", normalized):
                    words.pop(0)
                    continue
                break
            candidate = " ".join(words).strip()
            if not candidate:
                continue

            if len(candidate) < 2 or len(candidate) > 120:
                continue
            if not CYRILLIC_RE.search(candidate):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
    return unique


def parse_varcon_map(varcon_txt_path: Path) -> dict[str, set[str]]:
    variants: dict[str, set[str]] = {}
    with varcon_txt_path.open("r", encoding="latin-1") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            words: list[str] = []
            for segment in line.split("/"):
                if ": " not in segment:
                    continue
                _, value = segment.split(": ", 1)
                word = value.split("|", 1)[0].strip().lower().replace("_", " ")
                word = HEADWORD_SANITIZE_RE.sub("", word)
                word = re.sub(r"\s+", " ", word).strip()
                if not word or not re.search(r"[a-z]", word):
                    continue
                if len(word) > 80:
                    continue
                words.append(word)

            if len(words) < 2:
                continue

            unique_words = set(words)
            for word in unique_words:
                variants.setdefault(word, set()).update(unique_words - {word})
    return variants


def build_rows(
    dictionary_txt_path: Path,
    include_varcon: bool,
    varcon_map: dict[str, set[str]] | None = None,
) -> list[tuple[str, str, str | None, str]]:
    rows: set[tuple[str, str, str | None, str]] = set()
    en_to_ua: dict[str, set[tuple[str, str | None]]] = {}

    with dictionary_txt_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if "\t" not in line:
                continue
            headword_raw, definition_raw = line.split("\t", 1)
            headword_raw = headword_raw.strip()
            if not headword_raw or headword_raw == "_about" or headword_raw.startswith("##"):
                continue

            headwords = normalize_headwords(headword_raw)
            if not headwords:
                continue

            part_of_speech = extract_part_of_speech(definition_raw)
            ua_terms = extract_ua_terms(definition_raw)
            if not ua_terms:
                continue

            for en_word in headwords:
                bucket = en_to_ua.setdefault(en_word, set())
                for ua_word in ua_terms:
                    row = (ua_word, en_word, part_of_speech, SOURCE_EXTERNAL)
                    rows.add(row)
                    bucket.add((ua_word, part_of_speech))

    if include_varcon and varcon_map:
        for en_word, ua_entries in en_to_ua.items():
            related = varcon_map.get(en_word, set())
            for variant_word in related:
                if variant_word == en_word:
                    continue
                for ua_word, part_of_speech in ua_entries:
                    rows.add((ua_word, variant_word, part_of_speech, SOURCE_VARCON))

    return sorted(rows, key=lambda item: (item[1], item[0], item[3]))


def write_csv(rows: Iterable[tuple[str, str, str | None, str]], output_csv_path: Path) -> None:
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ua_word", "en_word", "part_of_speech", "source"])
        for ua_word, en_word, part_of_speech, source in rows:
            writer.writerow([ua_word, en_word, part_of_speech or "", source])


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare cleaned dictionary CSV from external repository")
    parser.add_argument("--repo-url", default=os.getenv("DICTIONARY_REPO_URL", REPO_URL_DEFAULT))
    parser.add_argument("--output", default="backend/data/processed/dictionary_clean.csv")
    parser.add_argument("--no-varcon", action="store_true")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[2]
    output_csv_path = (root_dir / args.output).resolve()

    include_varcon = not args.no_varcon

    with tempfile.TemporaryDirectory(prefix="duoeng-dictionary-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        repo_dir = clone_repository(args.repo_url, tmp_path)
        dictionary_asset, varcon_asset = detect_assets(repo_dir)

        print(f"Detected dictionary asset: {dictionary_asset.path} [{dictionary_asset.file_format}]")
        print(f"Detected varcon asset: {varcon_asset.path} [{varcon_asset.file_format}]")

        if dictionary_asset.path.suffix.lower() == ".zip":
            dictionary_txt_path = extract_text_from_zip(dictionary_asset.path, marker="eng-ukr", to_dir=tmp_path)
        else:
            dictionary_txt_path = dictionary_asset.path

        varcon_map: dict[str, set[str]] | None = None
        if include_varcon:
            if varcon_asset.path.suffix.lower() == ".zip":
                varcon_txt_path = extract_text_from_zip(varcon_asset.path, marker="varcon", to_dir=tmp_path)
            else:
                varcon_txt_path = varcon_asset.path
            varcon_map = parse_varcon_map(varcon_txt_path)

        rows = build_rows(
            dictionary_txt_path=dictionary_txt_path,
            include_varcon=include_varcon,
            varcon_map=varcon_map,
        )
        write_csv(rows, output_csv_path)

    print(f"Processed dictionary rows: {len(rows)}")
    print(f"Saved cleaned CSV to: {output_csv_path}")


if __name__ == "__main__":
    main()

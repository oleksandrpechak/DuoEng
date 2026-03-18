from __future__ import annotations

import logging

logger = logging.getLogger("duoeng.scoring")


def score_answer(player_answer: str, correct_word: str, ua_word: str = "", definition: str = "") -> int:
    """Instant local scoring with description and definition support.
    
    Scoring rules:
    - Exact match → 2 pts
    - High similarity (typo tolerance, ratio >= 0.75) → 2 pts
    - Medium similarity (ratio >= 0.50) → 1 pt
    - Substring match (answer contains correct or vice versa, min 3 chars) → 1 pt
    - Description check: if answer is 3+ words and contains the correct word → 1 pt
    - Description check: if correct word appears as a meaningful part of the answer → 1 pt
    - Definition match: if answer closely matches the word's stored definition → 1 pt
    """
    import difflib

    answer = player_answer.strip().lower()
    correct = correct_word.strip().lower()

    if not answer or not correct:
        return 0

    # Exact match
    if answer == correct:
        return 2

    # High similarity (typo tolerance)
    ratio = difflib.SequenceMatcher(None, answer, correct).ratio()
    if ratio >= 0.75:
        return 2
    if ratio >= 0.50:
        return 1

    # Check if answer is a substring or superstring (e.g. "run" in "running")
    if len(answer) >= 3 and len(correct) >= 3:
        if answer in correct or correct in answer:
            return 1

    # Description support: multi-word answer containing the correct word
    answer_words = answer.split()
    if len(answer_words) >= 2:
        # Check if the correct word appears in the description
        if correct in answer_words:
            return 1
        # Check if any word in the answer is very similar to the correct word
        for w in answer_words:
            if len(w) >= 3:
                word_ratio = difflib.SequenceMatcher(None, w, correct).ratio()
                if word_ratio >= 0.75:
                    return 1

    # Check individual words of a compound correct answer
    correct_words = correct.split()
    if len(correct_words) >= 2:
        # Multi-word correct answer: check if answer matches any word
        for cw in correct_words:
            if len(cw) >= 3 and answer == cw:
                return 1

    # ── Definition-based scoring ──
    # If the word has a stored definition, check if the player's answer
    # describes the word correctly (matches the definition text).
    if definition and len(answer) >= 5:
        def_lower = definition.strip().lower()
        if def_lower:
            # Check similarity between answer and definition
            def_ratio = difflib.SequenceMatcher(None, answer, def_lower).ratio()
            if def_ratio >= 0.65:
                return 1

            # Check if the answer is a significant substring of the definition
            if len(answer) >= 8 and answer in def_lower:
                return 1

            # Check if the definition is contained in the answer
            if len(def_lower) >= 8 and def_lower in answer:
                return 1

            # Check word overlap between answer and definition
            def_words = set(def_lower.split())
            answer_word_set = set(answer_words) if answer_words else set(answer.split())
            # Remove common stop words for better matching
            stop_words = {"a", "an", "the", "is", "are", "was", "were", "be", "been",
                         "to", "of", "in", "for", "on", "with", "at", "by", "it",
                         "that", "this", "and", "or", "but", "not", "no", "so"}
            meaningful_def = def_words - stop_words
            meaningful_ans = answer_word_set - stop_words
            if meaningful_def and meaningful_ans:
                overlap = meaningful_def & meaningful_ans
                # If 50%+ of meaningful answer words appear in the definition
                overlap_ratio = len(overlap) / max(len(meaningful_ans), 1)
                if overlap_ratio >= 0.5 and len(overlap) >= 2:
                    return 1

    return 0



from __future__ import annotations

import logging

logger = logging.getLogger("duoeng.scoring")


def score_answer(player_answer: str, correct_word: str, ua_word: str = "") -> int:
    """Instant local scoring with description support.
    
    Scoring rules:
    - Exact match → 2 pts
    - High similarity (typo tolerance, ratio >= 0.75) → 2 pts
    - Medium similarity (ratio >= 0.50) → 1 pt
    - Substring match (answer contains correct or vice versa, min 3 chars) → 1 pt
    - Description check: if answer is 3+ words and contains the correct word → 1 pt
    - Description check: if correct word appears as a meaningful part of the answer → 1 pt
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

    return 0



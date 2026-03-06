from __future__ import annotations

from difflib import SequenceMatcher
import logging

logger = logging.getLogger("duoeng.scoring")


def score_answer(player_answer: str, correct_word: str) -> int:
    answer = player_answer.strip().lower()
    correct = correct_word.strip().lower()
    if answer == correct:
        return 2
    import difflib
    ratio = difflib.SequenceMatcher(None, answer, correct).ratio()
    if ratio >= 0.75:
        return 2
    if ratio >= 0.55:
        return 1
    return 0

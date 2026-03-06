from __future__ import annotations

import logging

logger = logging.getLogger("duoeng.scoring")

async def score_answer(player_answer: str, correct_word: str, ua_word: str = "") -> int:
    import difflib
    
    answer = player_answer.strip().lower()
    correct = correct_word.strip().lower()
    
    # FAST PATH — never call LLM, instant response
    
    # Exact match
    if answer == correct:
        return 2
    
    # High similarity
    ratio = difflib.SequenceMatcher(None, answer, correct).ratio()
    if ratio >= 0.75:
        return 2
    if ratio >= 0.50:
        return 1
    
    # Always return 0 for wrong — no LLM call ever
    return 0



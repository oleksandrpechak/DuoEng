from __future__ import annotations


def expected_score(r_a: int, r_b: int) -> float:
    return 1 / (1 + 10 ** ((r_b - r_a) / 400))


def update_elo(rating: int, expected: float, actual: float, k: int = 32) -> int:
    return round(rating + k * (actual - expected))

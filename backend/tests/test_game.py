import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.db import get_db, init_db, reset_database_engine, seed_sample_words_if_empty
from app.elo import expected_score, update_elo
from app.game_service import GameService, generate_room_code
from app.scoring import LLMScorer, ScoreResult


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    original_db_url = settings.database_url
    test_db = tmp_path / "duoeng-test.db"

    test_url = f"sqlite:///{test_db}"
    object.__setattr__(settings, "database_url", test_url)
    reset_database_engine(test_url)

    init_db()
    seed_sample_words_if_empty()

    try:
        yield
    finally:
        object.__setattr__(settings, "database_url", original_db_url)
        reset_database_engine(original_db_url)


def test_elo_update_formula():
    expected = expected_score(1000, 1000)
    assert round(expected, 4) == 0.5

    winner_new = update_elo(1000, expected, 1, k=32)
    loser_new = update_elo(1000, expected, 0, k=32)

    assert winner_new == 1016
    assert loser_new == 984


def test_room_code_generator_entropy_and_charset():
    codes = {generate_room_code(length=8) for _ in range(1000)}
    assert len(codes) >= 995

    for code in codes:
        assert len(code) == 8
        assert code.isalnum()
        assert code.upper() == code


def test_scoring_fallback_when_llm_unavailable(monkeypatch):
    scorer = LLMScorer()

    async def fake_llm(*_args, **_kwargs):
        return None

    monkeypatch.setattr(scorer, "_call_llm", fake_llm)

    result = asyncio.run(scorer.score("determine", "completely unrelated answer"))
    assert result.source == "fallback_semantic_lite"
    assert result.score in {0, 1}


def test_end_to_end_game_flow_updates_elo_and_stats():
    service = GameService(scorer=LLMScorer())

    p1 = service.create_guest("Alice")
    p2 = service.create_guest("Bob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=1,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]

    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state_p1 = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    state_p2 = service.room_state_for_player(room_code, p2["player_id"], ip="127.0.0.2")

    current_turn_player = state_p1["current_turn_player_id"]
    assert current_turn_player in {p1["player_id"], p2["player_id"]}

    if current_turn_player == p1["player_id"]:
        assert state_p1["current_word_ua"] is not None
        assert state_p2["current_word_ua"] is None
        acting_player = p1
        acting_ip = "127.0.0.1"
    else:
        assert state_p2["current_word_ua"] is not None
        assert state_p1["current_word_ua"] is None
        acting_player = p2
        acting_ip = "127.0.0.2"

    with get_db() as conn:
        room = conn.execute(
            text("SELECT current_word_en FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        correct_answer = room["current_word_en"]

    move_result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer=correct_answer,
            ip=acting_ip,
        )
    )

    assert move_result["game_over"] is True
    assert move_result["points"] == 2
    assert move_result["winner_id"] == acting_player["player_id"]

    leaderboard = service.leaderboard(limit=2)
    assert len(leaderboard) == 2
    assert leaderboard[0]["elo"] > leaderboard[1]["elo"]

    winner_stats = service.player_stats(move_result["winner_id"])
    assert winner_stats["wins"] == 1
    assert winner_stats["total_games"] == 1
    assert winner_stats["total_moves"] >= 1


def test_llm_score_can_be_used(monkeypatch):
    scorer = LLMScorer()

    async def fake_llm(_correct: str, _answer: str):
        return ScoreResult(score=1, source="llm", used_llm=True)

    monkeypatch.setattr(scorer, "_call_llm", fake_llm)
    result = asyncio.run(scorer.score("determine", "to figure out"))

    assert result.source == "llm"
    assert result.score == 1

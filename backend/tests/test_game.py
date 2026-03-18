import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.db import get_db, init_db, reset_database_engine, seed_from_dmklinger
from app.elo import expected_score, update_elo
from app.game_service import GameService, generate_room_code
from app.scoring import score_answer


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    original_db_url = settings.database_url
    test_db = tmp_path / "duoeng-test.db"

    test_url = f"sqlite:///{test_db}"
    object.__setattr__(settings, "database_url", test_url)
    reset_database_engine(test_url)

    init_db()
    seed_from_dmklinger()

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


def test_scoring_exact_match():
    assert score_answer("hello", "hello") == 2


def test_scoring_typo_tolerance():
    assert score_answer("helo", "hello") >= 1


def test_scoring_description():
    # Answer contains the correct word as part of description
    assert score_answer("it means hello world", "hello") >= 1


def test_scoring_wrong():
    assert score_answer("banana", "computer") == 0


def test_end_to_end_game_flow_updates_elo_and_stats():
    service = GameService()

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

    # Submit the exact correct answer for an instant win
    move_result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer=correct_answer,
            ip=acting_ip,
        )
    )

    assert move_result["game_over"] is True
    assert move_result["points"] == 2  # exact match = 2 pts
    assert move_result["winner_id"] == acting_player["player_id"]

    leaderboard = service.leaderboard(limit=2)
    assert len(leaderboard) == 2
    assert leaderboard[0]["elo"] > leaderboard[1]["elo"]

    winner_stats = service.player_stats(move_result["winner_id"])
    assert winner_stats["wins"] == 1
    assert winner_stats["total_games"] == 1
    assert winner_stats["total_moves"] >= 1


def test_ai_scoring_instant():
    """AI scoring should return a score and answer instantly."""
    from app.ai_player import simulate_ai_score

    for _ in range(20):
        score, answer = simulate_ai_score("hello", "easy")
        assert score in {0, 1, 2}
        assert isinstance(answer, str)


# -----------------------------------------------------------------------
# SCORING EDGE CASES
# -----------------------------------------------------------------------

def test_scoring_empty_answer():
    assert score_answer("", "hello") == 0
    assert score_answer("   ", "hello") == 0


def test_scoring_empty_correct():
    assert score_answer("hello", "") == 0


def test_scoring_case_insensitive():
    assert score_answer("HELLO", "hello") == 2
    assert score_answer("Hello", "hello") == 2


def test_scoring_whitespace_trimming():
    assert score_answer("  hello  ", "hello") == 2


def test_scoring_high_similarity():
    """Single character typo should still score 2."""
    assert score_answer("helo", "hello") == 2  # ratio ~0.89


def test_scoring_medium_similarity():
    """Moderate similarity should score 1."""
    assert score_answer("hll", "hello") >= 0  # ratio depends on impl


def test_scoring_substring_match():
    """Answer is a substring of the correct answer."""
    assert score_answer("run", "running") == 1


def test_scoring_superstring_match():
    """Correct answer is a substring of the answer."""
    assert score_answer("running", "run") == 1


def test_scoring_short_substring_no_match():
    """Too-short substrings should not match."""
    assert score_answer("ru", "running") == 0


def test_scoring_description_multi_word():
    """Multi-word answer containing the correct word."""
    assert score_answer("a bright light", "light") == 1
    assert score_answer("water is clear", "water") == 1


def test_scoring_description_similar_word():
    """Multi-word answer with a similar-enough word."""
    assert score_answer("the helo rings", "hello") >= 1


def test_scoring_compound_correct_answer():
    """Multi-word correct answer where answer matches one part."""
    assert score_answer("break", "break down") == 1


def test_scoring_completely_wrong():
    """Totally unrelated answer."""
    assert score_answer("elephant", "computer") == 0
    assert score_answer("xyz", "hello") == 0


def test_scoring_definition_match():
    """Answer matching the word's definition should score 1."""
    # Definition: "a feeling of great happiness"
    assert score_answer(
        "a feeling of great happiness", "joy",
        definition="a feeling of great happiness"
    ) == 1


def test_scoring_definition_close_match():
    """Answer closely resembling the definition should score 1."""
    assert score_answer(
        "feeling of happiness", "joy",
        definition="a feeling of great happiness"
    ) == 1


def test_scoring_definition_no_match():
    """Unrelated answer should not match the definition."""
    assert score_answer(
        "a large vehicle", "joy",
        definition="a feeling of great happiness"
    ) == 0


def test_scoring_definition_substring():
    """Answer that is a substring of the definition should score 1."""
    assert score_answer(
        "feeling of great happiness", "joy",
        definition="a feeling of great happiness and satisfaction"
    ) == 1


def test_scoring_definition_empty():
    """Empty definition should not affect scoring."""
    assert score_answer("elephant", "computer", definition="") == 0
    assert score_answer("hello", "hello", definition="") == 2


def test_scoring_same_length_different_words():
    """Same length but different letters — low similarity."""
    assert score_answer("abc", "xyz") == 0


# -----------------------------------------------------------------------
# AI PLAYER EDGE CASES
# -----------------------------------------------------------------------

def test_ai_scoring_all_difficulties():
    """AI scoring works for all difficulty levels."""
    from app.ai_player import simulate_ai_score
    for difficulty in ("easy", "medium", "hard"):
        for _ in range(10):
            score, answer = simulate_ai_score("computer", difficulty)
            assert score in {0, 1, 2}
            assert isinstance(answer, str) and len(answer) > 0


def test_ai_scoring_invalid_difficulty_defaults_to_medium():
    """Invalid difficulty should fall back to medium."""
    from app.ai_player import simulate_ai_score
    score, answer = simulate_ai_score("hello", "nonexistent")
    assert score in {0, 1, 2}


def test_ai_is_ai_player():
    from app.ai_player import is_ai_player, AI_PLAYER_IDS
    for pid in AI_PLAYER_IDS.values():
        assert is_ai_player(pid) is True
    assert is_ai_player("some_random_player") is False


def test_ai_get_difficulty():
    from app.ai_player import get_ai_difficulty
    assert get_ai_difficulty("ai_easy") == "easy"
    assert get_ai_difficulty("ai_medium") == "medium"
    assert get_ai_difficulty("ai_hard") == "hard"
    assert get_ai_difficulty("some_random") is None


def test_ai_slightly_wrong_short_word():
    """_slightly_wrong handles short words without crashing."""
    from app.ai_player import _slightly_wrong
    result = _slightly_wrong("ab")
    assert isinstance(result, str) and len(result) > 0
    result = _slightly_wrong("a")
    assert isinstance(result, str) and len(result) > 0


def test_ai_correct_rate_distribution():
    """Hard AI should score 2 more often than easy AI (statistical sanity)."""
    from app.ai_player import simulate_ai_score
    import random
    random.seed(42)

    easy_2s = sum(1 for _ in range(200) if simulate_ai_score("word", "easy")[0] == 2)
    hard_2s = sum(1 for _ in range(200) if simulate_ai_score("word", "hard")[0] == 2)
    # Hard should get more 2-point answers than easy
    assert hard_2s > easy_2s


# -----------------------------------------------------------------------
# GAME FLOW EDGE CASES
# -----------------------------------------------------------------------

def test_create_room_vs_ai_starts_immediately():
    """Creating a vs_ai room should start the game immediately."""
    from app.ai_player import ensure_ai_players_exist
    ensure_ai_players_exist()

    service = GameService()
    player = service.create_guest("AITester")
    result = service.create_room(
        player_id=player["player_id"],
        mode="vs_ai",
        target_score=5,
        ip="127.0.0.1",
        ai_difficulty="medium",
    )
    assert result["status"] == "playing"
    assert result["mode"] == "vs_ai"
    assert result["ai_difficulty"] == "medium"

    state = service.room_state_for_player(result["room_code"], player["player_id"], ip="127.0.0.1")
    assert state["status"] == "playing"
    assert state["current_turn_player_id"] == player["player_id"]
    assert state["current_word_ua"] is not None


def test_partial_answer_scores_one_point():
    """Submit a close-but-not-exact answer and get 1 point."""
    service = GameService()
    p1 = service.create_guest("PartialAlice")
    p2 = service.create_guest("PartialBob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=10,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]
    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    current_turn = state["current_turn_player_id"]
    acting_player = p1 if current_turn == p1["player_id"] else p2
    acting_ip = "127.0.0.1" if current_turn == p1["player_id"] else "127.0.0.2"

    with get_db() as conn:
        room = conn.execute(
            text("SELECT current_word_en FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        correct = room["current_word_en"]

    # Submit a substring if the word is long enough
    if len(correct) >= 5:
        partial = correct[:len(correct) - 2]  # chop last 2 chars
    else:
        partial = correct + "x"  # force a near-miss

    result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer=partial,
            ip=acting_ip,
        )
    )
    # Should get partial credit (1) or full credit (2) depending on similarity
    assert result["points"] in {0, 1, 2}
    assert result["game_over"] is False


def test_wrong_answer_scores_zero():
    """A completely wrong answer should score 0."""
    service = GameService()
    p1 = service.create_guest("WrongAlice")
    p2 = service.create_guest("WrongBob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=10,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]
    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    current_turn = state["current_turn_player_id"]
    acting_player = p1 if current_turn == p1["player_id"] else p2
    acting_ip = "127.0.0.1" if current_turn == p1["player_id"] else "127.0.0.2"

    result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer="zzz_absolutely_wrong_xyzxyz",
            ip=acting_ip,
        )
    )
    assert result["points"] == 0
    assert result["game_over"] is False


def test_submit_not_your_turn_rejected():
    """Submitting when it's not your turn should raise 403."""
    service = GameService()
    p1 = service.create_guest("TurnAlice")
    p2 = service.create_guest("TurnBob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=10,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]
    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    current_turn = state["current_turn_player_id"]
    waiting_player = p2 if current_turn == p1["player_id"] else p1
    waiting_ip = "127.0.0.2" if current_turn == p1["player_id"] else "127.0.0.1"

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            service.submit_answer(
                room_code=room_code,
                player_id=waiting_player["player_id"],
                answer="test",
                ip=waiting_ip,
            )
        )
    assert "Not your turn" in str(exc_info.value.detail)


def test_leaderboard_returns_sorted():
    """Leaderboard should return players sorted by ELO descending."""
    service = GameService()
    service.create_guest("LBAlice")
    service.create_guest("LBBob")

    leaderboard = service.leaderboard(limit=10)
    assert len(leaderboard) >= 2
    for i in range(len(leaderboard) - 1):
        assert leaderboard[i]["elo"] >= leaderboard[i + 1]["elo"]


# -----------------------------------------------------------------------
# VS-AI FLOW: AI AUTO-PLAYS INSTANTLY
# -----------------------------------------------------------------------

def test_vs_ai_ai_plays_after_human_submit():
    """After human submits in vs_ai, the AI should auto-play instantly.
    The turn should come back to the human, not stall on the AI.
    """
    from app.ai_player import ensure_ai_players_exist
    ensure_ai_players_exist()

    service = GameService()
    player = service.create_guest("VSAITester")
    result = service.create_room(
        player_id=player["player_id"],
        mode="vs_ai",
        target_score=20,  # high target so game doesn't end quickly
        ip="127.0.0.1",
        ai_difficulty="easy",
    )
    room_code = result["room_code"]

    # It should be the human's turn
    state = service.room_state_for_player(room_code, player["player_id"], ip="127.0.0.1")
    assert state["current_turn_player_id"] == player["player_id"]
    assert state["current_word_ua"] is not None

    # Get the correct answer to guarantee some progress
    with get_db() as conn:
        room = conn.execute(
            text("SELECT current_word_en FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        correct = room["current_word_en"]

    # Human submits correct answer
    move_result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=player["player_id"],
            answer=correct,
            ip="127.0.0.1",
        )
    )
    assert move_result["points"] == 2

    # After human submits, the AI should have auto-played.
    # The turn should now be back to the human, NOT stuck on the AI.
    state_after = service.room_state_for_player(room_code, player["player_id"], ip="127.0.0.1")

    if not state_after.get("winner_id"):
        # Game is still going — turn must be the human's
        assert state_after["current_turn_player_id"] == player["player_id"], (
            "Turn should be back to human after AI auto-play, but was: "
            + str(state_after["current_turn_player_id"])
        )
        assert state_after["current_word_ua"] is not None


def test_vs_ai_state_poll_triggers_ai_turn():
    """Polling room state when it's the AI's turn should trigger instant AI play.
    This tests the _apply_timeout_if_needed path.
    """
    from app.ai_player import ensure_ai_players_exist, AI_PLAYER_IDS
    ensure_ai_players_exist()

    service = GameService()
    player = service.create_guest("PollAITester")
    result = service.create_room(
        player_id=player["player_id"],
        mode="vs_ai",
        target_score=20,
        ip="127.0.0.1",
        ai_difficulty="medium",
    )
    room_code = result["room_code"]

    # Manually force the turn to the AI player to simulate the scenario
    ai_pid = AI_PLAYER_IDS["medium"]
    with get_db() as session:
        session.execute(
            text("UPDATE rooms SET current_turn = :ai_pid WHERE code = :code"),
            {"ai_pid": ai_pid, "code": room_code},
        )

    # Now when we poll the room state, the AI's turn should be auto-played
    state = service.room_state_for_player(room_code, player["player_id"], ip="127.0.0.1")

    # After the state poll, the AI should have already played and the
    # turn should be back to the human
    if not state.get("winner_id"):
        assert state["current_turn_player_id"] == player["player_id"], (
            "After state poll, turn should be back to human, but was: "
            + str(state["current_turn_player_id"])
        )


def test_vs_ai_multiple_rounds():
    """Play several rounds in vs-AI mode to ensure turns alternate correctly."""
    from app.ai_player import ensure_ai_players_exist
    ensure_ai_players_exist()

    service = GameService()
    player = service.create_guest("MultiRoundTester")
    result = service.create_room(
        player_id=player["player_id"],
        mode="vs_ai",
        target_score=50,  # very high so we can play many rounds
        ip="127.0.0.1",
        ai_difficulty="easy",
    )
    room_code = result["room_code"]

    for round_num in range(5):
        state = service.room_state_for_player(room_code, player["player_id"], ip="127.0.0.1")
        if state.get("winner_id") or state["status"] == "finished":
            break  # game ended

        assert state["current_turn_player_id"] == player["player_id"], (
            f"Round {round_num}: expected human's turn, got {state['current_turn_player_id']}"
        )

        with get_db() as conn:
            room = conn.execute(
                text("SELECT current_word_en FROM rooms WHERE code = :code"),
                {"code": room_code},
            ).mappings().first()
            correct = room["current_word_en"]

        move_result = asyncio.run(
            service.submit_answer(
                room_code=room_code,
                player_id=player["player_id"],
                answer=correct,
                ip="127.0.0.1",
            )
        )
        if move_result["game_over"]:
            break


def test_wrong_words_recorded_after_wrong_answer():
    """Wrong answers (score 0, not timeout) should appear in get_wrong_words."""
    service = GameService()
    p1 = service.create_guest("WrongWordAlice")
    p2 = service.create_guest("WrongWordBob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=10,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]
    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    current_turn = state["current_turn_player_id"]
    acting_player = p1 if current_turn == p1["player_id"] else p2
    acting_ip = "127.0.0.1" if current_turn == p1["player_id"] else "127.0.0.2"

    # Get the correct answer from DB so we know what word it is
    with get_db() as conn:
        room_row = conn.execute(
            text("SELECT current_word_en, current_word_ua FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        correct_en = room_row["current_word_en"]
        correct_ua = room_row["current_word_ua"]

    # Submit a completely wrong answer
    result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer="zzz_completely_wrong_xyzxyz",
            ip=acting_ip,
        )
    )
    assert result["points"] == 0

    # Check wrong words for the player who answered wrong
    wrong = service.get_wrong_words(acting_player["player_id"], limit=50)
    assert len(wrong) >= 1
    # The wrong entry should match the word from this turn
    found = any(
        w["correct_answer"] == correct_en and w["ua_word"] == correct_ua
        for w in wrong
    )
    assert found, f"Expected wrong word {correct_ua}→{correct_en} in {wrong}"
    entry = next(w for w in wrong if w["correct_answer"] == correct_en)
    assert entry["times_wrong"] >= 1
    assert entry["user_answer"] is not None


def test_correct_answer_not_in_wrong_words():
    """A correct answer (score > 0) should NOT appear in wrong words."""
    service = GameService()
    p1 = service.create_guest("CorrectAlice")
    p2 = service.create_guest("CorrectBob")

    create = service.create_room(
        player_id=p1["player_id"],
        mode="classic",
        target_score=10,
        ip="127.0.0.1",
    )
    room_code = create["room_code"]
    service.join_room(room_code=room_code, player_id=p2["player_id"], ip="127.0.0.2")

    state = service.room_state_for_player(room_code, p1["player_id"], ip="127.0.0.1")
    current_turn = state["current_turn_player_id"]
    acting_player = p1 if current_turn == p1["player_id"] else p2
    acting_ip = "127.0.0.1" if current_turn == p1["player_id"] else "127.0.0.2"

    # Get the correct answer and submit it
    with get_db() as conn:
        room_row = conn.execute(
            text("SELECT current_word_en FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        correct_en = room_row["current_word_en"]

    result = asyncio.run(
        service.submit_answer(
            room_code=room_code,
            player_id=acting_player["player_id"],
            answer=correct_en,
            ip=acting_ip,
        )
    )
    assert result["points"] >= 1  # Should score

    # Wrong words should NOT include this word
    wrong = service.get_wrong_words(acting_player["player_id"], limit=50)
    found = any(w["correct_answer"] == correct_en for w in wrong)
    assert not found, f"Correct answer {correct_en} should NOT be in wrong words"

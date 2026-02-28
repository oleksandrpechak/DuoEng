import asyncio
import importlib
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import pytest
import requests

import server as server_module

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _localhost_bind_allowed() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


LOCALHOST_BIND_ALLOWED = _localhost_bind_allowed()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def api_server(tmp_path):
    if not LOCALHOST_BIND_ALLOWED:
        pytest.skip("Localhost socket binding is blocked in this sandbox environment")

    db_path = tmp_path / "duovocab-test.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}/api"

    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)
    env["JWT_SECRET"] = "test-secret-with-adequate-length-123456"
    env["JWT_EXP_MINUTES"] = "60"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + 20
    started = False
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/", timeout=0.5)
            if response.status_code == 200:
                started = True
                break
        except requests.RequestException:
            time.sleep(0.2)

    if not started:
        output = ""
        if process.stdout:
            output = process.stdout.read()
        process.terminate()
        raise RuntimeError(f"Uvicorn did not start in time. Output:\n{output}")

    try:
        yield base_url, db_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def create_user(base_url: str, nickname: str):
    response = requests.post(
        f"{base_url}/auth/guest", json={"nickname": nickname}, timeout=3
    )
    assert response.status_code == 200
    data = response.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return data["user_id"], headers


def create_started_room(base_url: str, mode: str = "challenge", target_score: int = 5):
    user1_id, user1_headers = create_user(base_url, "PlayerOne")
    user2_id, user2_headers = create_user(base_url, "PlayerTwo")

    create_room = requests.post(
        f"{base_url}/rooms",
        headers=user1_headers,
        json={"mode": mode, "target_score": target_score},
        timeout=3,
    )
    assert create_room.status_code == 200
    code = create_room.json()["code"]

    join_room = requests.post(f"{base_url}/rooms/{code}/join", headers=user2_headers, timeout=3)
    assert join_room.status_code == 200

    return code, (user1_id, user1_headers), (user2_id, user2_headers)


def test_protected_routes_require_jwt(api_server):
    base_url, _ = api_server
    response = requests.post(
        f"{base_url}/rooms", json={"mode": "classic", "target_score": 10}, timeout=3
    )
    assert response.status_code == 401


def test_state_hides_word_for_non_current_player_and_checks_membership(api_server):
    base_url, _ = api_server
    code, (user1_id, user1_headers), (_, user2_headers) = create_started_room(base_url)

    state1 = requests.get(f"{base_url}/rooms/{code}/state", headers=user1_headers, timeout=3)
    state2 = requests.get(f"{base_url}/rooms/{code}/state", headers=user2_headers, timeout=3)
    assert state1.status_code == 200
    assert state2.status_code == 200

    turn1 = state1.json()["current_turn"]
    turn2 = state2.json()["current_turn"]
    assert turn1 is not None
    assert turn2 is not None

    if turn1["current_player_id"] == user1_id:
        assert turn1["word_ua"] is not None
        assert turn2["word_ua"] is None
    else:
        assert turn2["word_ua"] is not None
        assert turn1["word_ua"] is None

    _, intruder_headers = create_user(base_url, "Intruder")
    forbidden_state = requests.get(
        f"{base_url}/rooms/{code}/state", headers=intruder_headers, timeout=3
    )
    forbidden_turn = requests.post(
        f"{base_url}/rooms/{code}/turn",
        headers=intruder_headers,
        json={"answer": "hello"},
        timeout=3,
    )
    assert forbidden_state.status_code == 403
    assert forbidden_turn.status_code == 403


def test_timeout_expiry_advances_to_single_next_turn(api_server):
    base_url, db_path = api_server
    code, (_, headers1), (_, headers2) = create_started_room(base_url, mode="challenge")

    state_before = requests.get(f"{base_url}/rooms/{code}/state", headers=headers1, timeout=3)
    assert state_before.status_code == 200
    active_turn_id = state_before.json()["current_turn"]["turn_id"]
    active_player_user_id = state_before.json()["current_turn"]["current_player_id"]

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE turns SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", active_turn_id),
        )
        conn.commit()

    first_poll = requests.get(f"{base_url}/rooms/{code}/state", headers=headers1, timeout=3)
    second_poll = requests.get(f"{base_url}/rooms/{code}/state", headers=headers2, timeout=3)
    assert first_poll.status_code == 200
    assert second_poll.status_code == 200

    next_turn = second_poll.json()["current_turn"]
    assert next_turn is not None
    assert next_turn["turn_id"] != active_turn_id
    assert next_turn["current_player_id"] != active_player_user_id

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        counts = conn.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM turns t
            JOIN game_rooms gr ON gr.id = t.room_id
            WHERE gr.code = ?
            GROUP BY status
            """,
            (code,),
        ).fetchall()

    by_status = {row["status"]: row["cnt"] for row in counts}
    assert by_status.get("active", 0) == 1
    assert by_status.get("expired", 0) == 1


def test_strict_validation_on_mode_target_and_answer(api_server):
    base_url, _ = api_server
    _, headers = create_user(base_url, "Validator")

    invalid_mode = requests.post(
        f"{base_url}/rooms",
        headers=headers,
        json={"mode": "arcade", "target_score": 10},
        timeout=3,
    )
    invalid_score = requests.post(
        f"{base_url}/rooms",
        headers=headers,
        json={"mode": "classic", "target_score": 0},
        timeout=3,
    )

    room_resp = requests.post(
        f"{base_url}/rooms",
        headers=headers,
        json={"mode": "classic", "target_score": 5},
        timeout=3,
    )
    assert room_resp.status_code == 200
    code = room_resp.json()["code"]

    answer_with_spaces = requests.post(
        f"{base_url}/rooms/{code}/turn",
        headers=headers,
        json={"answer": "   "},
        timeout=3,
    )

    assert invalid_mode.status_code == 422
    assert invalid_score.status_code == 422
    assert answer_with_spaces.status_code == 422


def test_create_room_retries_on_code_collision(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "collision-test.db"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-adequate-length-123456")
    monkeypatch.setenv("JWT_EXP_MINUTES", "60")
    server = importlib.reload(server_module)

    user = asyncio.run(server.guest_auth(server.GuestAuthRequest(nickname="CollisionUser")))

    monkeypatch.setattr(server, "generate_room_code", lambda: "AAAAAA")
    first_room = asyncio.run(
        server.create_room(
            server.CreateRoomRequest(mode="classic", target_score=10),
            current_user_id=user.user_id,
        )
    )
    assert first_room.code == "AAAAAA"

    code_iter = iter(["AAAAAA", "BBBBBB"])
    monkeypatch.setattr(server, "generate_room_code", lambda: next(code_iter))
    second_room = asyncio.run(
        server.create_room(
            server.CreateRoomRequest(mode="classic", target_score=10),
            current_user_id=user.user_id,
        )
    )
    assert second_room.code == "BBBBBB"

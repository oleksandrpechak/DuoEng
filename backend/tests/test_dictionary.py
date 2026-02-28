from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import get_db, init_db, reset_database_engine, seed_sample_words_if_empty
from app.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    original_db_url = settings.database_url
    test_db = tmp_path / "duoeng-dictionary-test.db"
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


def test_dictionary_search_requires_auth():
    client = TestClient(app)
    response = client.get("/dictionary/search", params={"q": "tree"})
    assert response.status_code == 401


def test_dictionary_search_returns_limited_results():
    client = TestClient(app)

    auth_response = client.post("/api/auth/guest", json={"nickname": "DictUser"})
    assert auth_response.status_code == 200
    token = auth_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with get_db() as session:
        session.execute(
            text(
                """
                INSERT INTO dictionary_entries (ua_word, en_word, part_of_speech, source, created_at)
                VALUES (:ua_word, :en_word, :part_of_speech, :source, CURRENT_TIMESTAMP)
                """
            ),
            [
                {
                    "ua_word": f"дерево-{idx}",
                    "en_word": f"tree{idx:02d}",
                    "part_of_speech": "n",
                    "source": "test",
                }
                for idx in range(25)
            ],
        )

    response = client.get("/dictionary/search", params={"q": "tree"}, headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert len(payload) == 20
    assert payload[0]["en_word"].startswith("tree")
    assert payload[0]["source"] == "test"

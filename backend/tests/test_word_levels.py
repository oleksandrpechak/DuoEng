from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.db import init_db, reset_database_engine, seed_sample_words_if_empty
from app.main import app
from app.services.gemini_service import GeminiConfigurationError, GeminiServiceError, GeminiServiceTimeoutError


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    original_db_url = settings.database_url
    test_db = tmp_path / "duoeng-word-levels-test.db"
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


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post("/api/auth/guest", json={"nickname": "WordTestUser"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_word_levels_validation_error():
    client = TestClient(app)
    headers = _auth_headers(client)
    response = client.post("/api/v1/words/level", json={"words": []}, headers=headers)
    assert response.status_code == 422


def test_word_levels_success(monkeypatch):
    client = TestClient(app)
    headers = _auth_headers(client)

    async def fake_classify(words: list[str]) -> list[dict[str, str]]:
        return [{"word": word, "level": "B1"} for word in words]

    monkeypatch.setattr("app.routers.word_levels.classify_words_cefr", fake_classify)
    response = client.post("/api/v1/words/level", json={"words": ["apple", "analyze"]}, headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {"word": "apple", "level": "B1"},
        {"word": "analyze", "level": "B1"},
    ]


def test_word_levels_timeout(monkeypatch):
    client = TestClient(app)
    headers = _auth_headers(client)

    async def fake_timeout(_words: list[str]) -> list[dict[str, str]]:
        raise GeminiServiceTimeoutError("timeout")

    monkeypatch.setattr("app.routers.word_levels.classify_words_cefr", fake_timeout)
    response = client.post("/api/v1/words/level", json={"words": ["apple"]}, headers=headers)

    assert response.status_code == 504
    assert response.json()["detail"] == "Word level classification timed out"


def test_word_levels_configuration_error(monkeypatch):
    client = TestClient(app)
    headers = _auth_headers(client)

    async def fake_config(_words: list[str]) -> list[dict[str, str]]:
        raise GeminiConfigurationError("missing project")

    monkeypatch.setattr("app.routers.word_levels.classify_words_cefr", fake_config)
    response = client.post("/api/v1/words/level", json={"words": ["apple"]}, headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "Word levels service is not configured"


def test_word_levels_service_error(monkeypatch):
    client = TestClient(app)
    headers = _auth_headers(client)

    async def fake_service_error(_words: list[str]) -> list[dict[str, str]]:
        raise GeminiServiceError("invalid response")

    monkeypatch.setattr("app.routers.word_levels.classify_words_cefr", fake_service_error)
    response = client.post("/api/v1/words/level", json={"words": ["apple"]}, headers=headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "Word levels classification failed"


def test_word_levels_in_openapi():
    client = TestClient(app)
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/words/level" in spec.json()["paths"]

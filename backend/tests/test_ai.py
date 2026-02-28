from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.db import init_db, reset_database_engine, seed_sample_words_if_empty
from app.main import app
from app.services.gemini_service import GeminiConfigurationError, GeminiServiceTimeoutError


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    original_db_url = settings.database_url
    test_db = tmp_path / "duoeng-ai-test.db"
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


def test_ai_generate_prompt_validation():
    client = TestClient(app)
    response = client.post("/api/ai/generate", json={"prompt": ""})
    assert response.status_code == 422


def test_ai_generate_success(monkeypatch):
    client = TestClient(app)

    async def fake_generate(prompt: str) -> str:
        return f"generated:{prompt}"

    monkeypatch.setattr("app.routers.ai.generate_text", fake_generate)

    response = client.post("/api/ai/generate", json={"prompt": "Write a sentence"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "generated:Write a sentence"


def test_ai_generate_direct_route(monkeypatch):
    client = TestClient(app)

    async def fake_generate(prompt: str) -> str:
        return f"ok:{prompt}"

    monkeypatch.setattr("app.routers.ai.generate_text", fake_generate)
    response = client.post("/ai/generate", json={"prompt": "ping"})

    assert response.status_code == 200
    assert response.json() == {"result": "ok:ping"}


def test_ai_generate_timeout(monkeypatch):
    client = TestClient(app)

    async def fake_timeout(_prompt: str) -> str:
        raise GeminiServiceTimeoutError("timeout")

    monkeypatch.setattr("app.routers.ai.generate_text", fake_timeout)
    response = client.post("/api/ai/generate", json={"prompt": "hello"})

    assert response.status_code == 504
    assert response.json()["detail"] == "AI generation timed out"


def test_ai_generate_configuration_error(monkeypatch):
    client = TestClient(app)

    async def fake_config_error(_prompt: str) -> str:
        raise GeminiConfigurationError("missing project")

    monkeypatch.setattr("app.routers.ai.generate_text", fake_config_error)
    response = client.post("/api/ai/generate", json={"prompt": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "AI service is not configured"

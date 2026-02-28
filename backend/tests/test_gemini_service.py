import asyncio

from app.services.gemini_service import GeminiRuntimeConfig, GeminiService


def test_generate_text_returns_content(monkeypatch):
    service = GeminiService(
        GeminiRuntimeConfig(
            project="test-project",
            location="us-central1",
            model="gemini-2.0-flash",
            timeout_seconds=1.0,
            max_output_tokens=64,
            temperature=0.2,
        )
    )

    def fake_generate_sync(prompt: str) -> str:
        return f"echo:{prompt}"

    monkeypatch.setattr(service, "_generate_sync", fake_generate_sync)
    result = asyncio.run(service.generate_text("hello"))

    assert result == "echo:hello"

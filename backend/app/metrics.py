try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
except ImportError:  # pragma: no cover - local fallback when metrics package is absent
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    class _DummyMetric:
        def labels(self, **_kwargs):
            return self

        def inc(self, *_args, **_kwargs):
            return None

        def set(self, *_args, **_kwargs):
            return None

    def Counter(*_args, **_kwargs):  # type: ignore[misc]
        return _DummyMetric()

    def Gauge(*_args, **_kwargs):  # type: ignore[misc]
        return _DummyMetric()

    def generate_latest() -> bytes:
        return b""

REQUESTS_TOTAL = Counter(
    "requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
LLM_CALLS_TOTAL = Counter("llm_calls_total", "Total LLM scoring calls")
LLM_TIMEOUTS_TOTAL = Counter("llm_timeouts_total", "Total LLM call timeouts")
ACTIVE_ROOMS = Gauge("active_rooms", "Number of active websocket rooms")


__all__ = [
    "CONTENT_TYPE_LATEST",
    "REQUESTS_TOTAL",
    "LLM_CALLS_TOTAL",
    "LLM_TIMEOUTS_TOTAL",
    "ACTIVE_ROOMS",
    "generate_latest",
]

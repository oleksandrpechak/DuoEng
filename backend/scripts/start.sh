#!/bin/sh
set -eu

echo "[startup] running database migrations..."
alembic upgrade head

echo "[startup] starting API server..."
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"

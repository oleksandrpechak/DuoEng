#!/bin/sh
set -eu

normalize_database_url() {
  python3 - "$1" <<'PY'
import sys

raw = (sys.argv[1] or "").strip()
if not raw:
    print("")
    raise SystemExit(0)

if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
    raw = raw[1:-1].strip()

if "://" not in raw:
    raise SystemExit("Invalid DATABASE_URL: missing scheme")

scheme, suffix = raw.split("://", 1)
scheme = scheme.lower()

if scheme in {
    "postgres",
    "postgresql",
    "postgresql+psycopg",
    "postgresql+asyncpg",
    "postgresql+pg8000",
    "postgresql+psycopg2",
}:
    print(f"postgresql+psycopg2://{suffix}")
    raise SystemExit(0)

if scheme == "sqlite":
    print(raw)
    raise SystemExit(0)

raise SystemExit(f"Unsupported DATABASE_URL scheme: {scheme}")
PY
}

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[startup] normalizing DATABASE_URL..."
  DATABASE_URL="$(normalize_database_url "${DATABASE_URL}")"
  export DATABASE_URL
  DB_SCHEME="${DATABASE_URL%%://*}"
  echo "[startup] database scheme: ${DB_SCHEME}"
fi

echo "[startup] running database migrations..."
alembic upgrade head

echo "[startup] starting API server..."
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"

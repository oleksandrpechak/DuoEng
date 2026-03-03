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

detect_alembic_bootstrap_revision() {
  python3 - "$1" <<'PY'
import sys

from sqlalchemy import create_engine, inspect, text

url = (sys.argv[1] or "").strip()
if not url:
    print("none")
    raise SystemExit(0)

engine = create_engine(url, pool_pre_ping=True)
inspector = inspect(engine)
tables = set(inspector.get_table_names())

if "alembic_version" in tables:
    with engine.connect() as conn:
        revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    # Broken legacy states can have the table created but no applied revision row.
    if revisions:
        print("none")
        raise SystemExit(0)

if "players" not in tables:
    print("none")
    raise SystemExit(0)

if "dictionary_entries" in tables:
    print("head")
else:
    print("0001_initial")
PY
}

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[startup] normalizing DATABASE_URL..."
  DATABASE_URL="$(normalize_database_url "${DATABASE_URL}")"
  export DATABASE_URL
  DB_SCHEME="${DATABASE_URL%%://*}"
  echo "[startup] database scheme: ${DB_SCHEME}"
fi

BOOTSTRAP_REVISION="none"
if [ "${SKIP_ALEMBIC_BOOTSTRAP:-0}" != "1" ] && [ -n "${DATABASE_URL:-}" ]; then
  echo "[startup] checking alembic bootstrap state..."
  BOOTSTRAP_REVISION="$(detect_alembic_bootstrap_revision "${DATABASE_URL}")"
  if [ "${BOOTSTRAP_REVISION}" != "none" ]; then
    echo "[startup] legacy schema detected, stamping alembic revision: ${BOOTSTRAP_REVISION}"
    alembic stamp "${BOOTSTRAP_REVISION}"
  fi
fi

# Clear stale bytecode to ensure fresh migration files are used
find . -path '*/alembic/versions/__pycache__' -exec rm -rf {} + 2>/dev/null || true

# Widen the alembic_version.version_num column if it exists and is too narrow (PG only)
if [ -n "${DATABASE_URL:-}" ]; then
  python3 - "${DATABASE_URL}" <<'PY'
import sys
from sqlalchemy import create_engine, text

url = sys.argv[1].strip()
if not url:
    raise SystemExit(0)

engine = create_engine(url, pool_pre_ping=True)
if engine.dialect.name != "postgresql":
    raise SystemExit(0)

with engine.begin() as conn:
    row = conn.execute(text(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name='alembic_version' AND column_name='version_num' AND table_schema='public'"
    )).scalar()
    if row is not None and int(row) < 128:
        conn.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
        print("[startup] widened alembic_version.version_num to VARCHAR(128)")
    else:
        print("[startup] alembic_version.version_num already wide enough (or table absent)")
PY
fi

echo "[startup] running database migrations..."
echo "[startup] alembic current revision:"
alembic current 2>&1 || true
echo "[startup] alembic heads:"
alembic heads 2>&1 || true
alembic upgrade head

echo "[startup] starting API server..."
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"

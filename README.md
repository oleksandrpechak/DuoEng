# DuoEng

FastAPI + React multiplayer vocabulary duel with:
- JWT auth, room membership checks, server-side turn/timer validation
- WebSocket room updates + HTTP polling fallback
- LLM scoring (timeout + cache + fallback)
- ELO, persistent stats, leaderboard
- Rate limiting and temporary bans

## Backend (local)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python migrate.py
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Database configuration

`DATABASE_URL` is read from env:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db_name
```

Fallback (dev only) when not set:

```bash
DATABASE_URL=sqlite:///./duoeng.db
```

## Alembic migrations

```bash
cd backend
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "your_change"
alembic revision --autogenerate -m "add dictionary table"
alembic upgrade head
```

`python migrate.py` runs `alembic upgrade head`, verifies DB connection, and seeds default words.

## Dictionary dataset pipeline

Raw dataset is handled outside `backend/app` and kept separate from runtime code:

- raw cache dir: `backend/data/raw/`
- processed dataset: `backend/data/processed/dictionary_clean.csv`
- attribution: [`ATTRIBUTION.md`](ATTRIBUTION.md)
- dataset license note: [`backend/data/LICENSE_VARCON.txt`](backend/data/LICENSE_VARCON.txt)

Generate/refresh cleaned CSV from upstream source:

```bash
cd backend
./venv/bin/python scripts/prepare_dictionary.py
```

Seed into DB with chunked transactional inserts (`chunk_size=1000`):

```bash
cd backend
./venv/bin/python scripts/seed_dictionary.py --chunk-size 1000
```

Reseed even if table has rows:

```bash
./venv/bin/python scripts/seed_dictionary.py --force
```

For containerized environment:

```bash
docker exec backend python scripts/seed_dictionary.py --chunk-size 1000
```

On Render you can run the same seed command as a one-off shell task.
The seeder is idempotent and skips import when `dictionary_entries` is not empty.

## Production Docker (Render backend)

Backend uses [`backend/Dockerfile`](backend/Dockerfile):
- `python:3.11-slim`
- installs `requirements.txt`
- runs `gunicorn` + `uvicorn.workers.UvicornWorker`
- binds to `0.0.0.0:${PORT}`

## Render deployment

### 1) Create PostgreSQL service
1. In Render Dashboard: `New` -> `PostgreSQL`.
2. Choose region/plan.
3. After provisioning, copy **Internal Database URL**.

Set backend env var:

```bash
DATABASE_URL=postgresql://...
```

### 2) Deploy backend Web Service
1. `New` -> `Web Service`
2. Repo: this project
3. Root Directory: `backend`
4. Dockerfile Path: `Dockerfile`
5. Runtime env vars: use [`backend/.env.example`](backend/.env.example) as template
6. Required production vars: `SECRET_KEY`, `DATABASE_URL`, `PORT`, `LLM_TIMEOUT`, `ENABLE_LLM_SCORING`, `GEMINI_PROJECT`, `GEMINI_MODEL`

### 3) Service Account security (Render Secret File)
1. In backend service: `Environment` -> `Secret Files`
2. Upload GCP key as `/etc/secrets/gcp-key.json`
3. Set env:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcp-key.json
```

Rules:
- do not commit key JSON to git
- do not print key content in logs

## Gemini via Vertex AI (ADC)

The backend uses `google-genai` with Vertex AI and Application Default Credentials.
No API key is used.

Install dependencies:

```bash
cd backend
pip install google-genai>=0.8.0,<2.0.0 google-auth>=2.35.0,<3.0.0
```

Required env vars:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcp-key.json
GEMINI_PROJECT=<your-gcp-project-id>
GEMINI_LOCATION=us-central1
GEMINI_MODEL=gemini-2.0-flash
LLM_TIMEOUT=1.5
GEMINI_MAX_OUTPUT_TOKENS=512
GEMINI_TEMPERATURE=0.2
```

API endpoint:
- `POST /ai/generate`
- `POST /api/ai/generate` (same handler under API prefix)

Request:

```json
{ "prompt": "Write one short English sentence about teamwork." }
```

Response:

```json
{ "result": "Teamwork helps people solve problems faster." }
```

### 4) Deploy frontend Static Site
1. `New` -> `Static Site`
2. Root Directory: `frontend`
3. Build Command: `yarn build`
4. Publish Directory: `build`
5. Env var:

```bash
VITE_API_URL=https://backend-service.onrender.com
```

Frontend API base URL is read in [`frontend/src/lib/api.js`](frontend/src/lib/api.js) from `import.meta.env.VITE_API_URL` (with safe fallbacks).

## Security checklist implemented

- room code generation uses `secrets` + `[A-Z0-9]` + length >= 8
- turn ownership validated on server
- timer enforced on server (`TURN_TIMEOUT_SECONDS`)
- timeout turn flow writes move + advances turn atomically in one DB transaction
- room membership validated before state/move actions
- `word_ua` hidden for non-current player
- LLM called only from backend
- HTTP + WS rate limiting enabled
- dictionary search endpoint requires auth (`GET /dictionary/search?q=`)

## Health and startup checks

- `GET /health` -> DB-backed health check
- `GET /api/health` -> API health check
- startup performs DB connection check + init + seed + cache cleanup
- structured JSON logging enabled

## Acceptance tests

### Guest auth

```bash
curl -s -X POST "http://localhost:8000/api/auth/guest" \
  -H "Content-Type: application/json" \
  -d '{"nickname":"PlayerA"}'
```

### Create/join/submit (HTTP fallback)

```bash
TOKEN="<JWT_PLAYER_A>"
TOKEN2="<JWT_PLAYER_B>"

ROOM=$(curl -s -X POST "http://localhost:8000/api/rooms" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"classic","target_score":10}' | jq -r '.room_code')

curl -s -X POST "http://localhost:8000/api/rooms/$ROOM/join" \
  -H "Authorization: Bearer $TOKEN2"

curl -s -X POST "http://localhost:8000/api/rooms/$ROOM/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answer":"tree"}'
```

### WebSocket flow

```js
const token = "<JWT>";
const room = "<ROOM_CODE>";
const ws = new WebSocket(`wss://backend-url/ws/rooms/${room}?token=${token}`, ["jwt", token]);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.onopen = () => {
  ws.send(JSON.stringify({ type: "ping" }));
  ws.send(JSON.stringify({ type: "submit", answer: "tree" }));
};
```

### LLM timeout fallback

```bash
export ENABLE_LLM_SCORING=true
export LLM_API_URL=https://slow-endpoint.example.com/score
export LLM_TIMEOUT=0.2
```

Submit answer and verify response `scoring_source` starts with `fallback_`.

### Leaderboard/stats

```bash
curl -s "http://localhost:8000/api/leaderboard?limit=10"
curl -s "http://localhost:8000/api/players/<PLAYER_ID>/stats"
```

### Dictionary search (auth required)

```bash
curl -s "http://localhost:8000/dictionary/search?q=tree" \
  -H "Authorization: Bearer <JWT>"
```

### AI generate (Gemini)

```bash
curl -s -X POST "http://localhost:8000/api/ai/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write one short sentence about focus."}'
```

## CI

GitHub Actions workflow runs:
- `flake8`
- `pytest`
- Dockerfile lint (`hadolint`)

## Pre-deploy checklist

1. Set `SECRET_KEY` and `DATABASE_URL` in Render backend env.
2. Upload GCP key via Secret File and set `GOOGLE_APPLICATION_CREDENTIALS`.
3. Run `alembic upgrade head`.
4. Verify `GET /health` returns `200`.
5. Verify WebSocket submit + leaderboard update.
6. Verify frontend `VITE_API_URL` points to backend service URL.
7. Run dictionary seed and verify `GET /dictionary/search?q=<term>` with auth.

## Third-Party Data Sources

- Source repository: `pavlo-liapin/kindle-eng-ukr-dictionary`
- Dataset files are not mixed with backend application code.
- Code license: repository license.
- Dataset attribution/license: `ATTRIBUTION.md` and `backend/data/LICENSE_VARCON.txt`.

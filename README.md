# DuoEng — Multiplayer Vocabulary Duel

A real-time two-player English vocabulary game where players take turns describing words and an AI judge scores their answers.

## How It Works

1. **Create or join a room** — pick a CEFR difficulty level (A1–C2) and share the room link
2. **Describe the word** — each turn shows an English word; type a description of its meaning
3. **AI scores your answer** — Gemini 2.0 Flash judges whether the description is correct (+1 point) or not (0 points)
4. **First to target score wins** — ELO ratings update after each match

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic |
| **Frontend** | React 19, Tailwind CSS, Radix UI, React Router 7 |
| **Database** | PostgreSQL (production), SQLite (development) |
| **AI Scoring** | Google Gemini 2.0 Flash via Vertex AI |
| **Auth** | JWT (guest sessions + Google OAuth) |
| **Deployment** | Render (backend web service + frontend static site) |

## Features

- **Real-time gameplay** — WebSocket room updates with HTTP polling fallback
- **AI-powered scoring** — LLM judges descriptions with 4s timeout, caching, and keyword fallback
- **CEFR difficulty levels** — A1 (Beginner) through C2 (Mastery) word selection per room
- **ELO rating system** — persistent player rankings with K-factor 32
- **Leaderboard** — filterable by Today / This Week / All Time
- **Game history** — paginated match history with opponent info and scores
- **Google Sign-In** — OAuth 2.0 alongside guest access
- **Room sharing** — shareable join links with copy/native share support
- **Dictionary search** — English–Ukrainian word lookup with CEFR level filtering
- **Rate limiting** — per-IP and per-player with temporary bans
- **Security hardened** — CORS restrictions, security headers, request size limits, input sanitization

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, routes, WebSocket handler, middleware
│   ├── game_service.py      # Game logic (rooms, turns, scoring, ELO, history)
│   ├── scoring.py           # LLM scoring (Gemini + fallback + cache)
│   ├── models.py            # SQLAlchemy models (Player, Room, Match, Move, Word)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── config.py            # Settings from environment variables
│   ├── security.py          # JWT token creation and verification
│   ├── routers/
│   │   ├── oauth.py         # Google OAuth endpoints
│   │   └── word_levels.py   # CEFR word classification endpoint
│   └── services/
│       └── gemini_service.py # Vertex AI / Gemini integration
├── alembic/                  # Database migrations
├── tests/                    # Pytest test suite (19 tests)
├── data/processed/           # Dictionary CSV data
└── scripts/                  # Seed and data preparation scripts

frontend/
├── src/
│   ├── App.js               # Routes: /, /join/:code, /lobby/:code, /game/:code, /end/:code
│   ├── pages/
│   │   ├── LandingPage.jsx  # Home: auth, create/join room, leaderboard, history, dictionary
│   │   ├── LobbyPage.jsx    # Room lobby: settings display, link sharing, wait for opponent
│   │   ├── GamePage.jsx     # Gameplay: word display, description input, timer, scoreboard
│   │   ├── EndPage.jsx      # Results: winner, final scores, play again
│   │   └── JoinPage.jsx     # Auto-join from shared link
│   ├── components/
│   │   └── CefrBadge.jsx    # Reusable CEFR level badge (color-coded)
│   └── lib/
│       └── api.js           # Axios instance with auth interceptor
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/guest` | — | Create guest session, get JWT |
| GET | `/api/auth/google` | — | Start Google OAuth flow |
| GET | `/api/auth/google/callback` | — | Handle OAuth callback |
| POST | `/api/rooms` | ✅ | Create room (mode, target score, CEFR level) |
| POST | `/api/rooms/{code}/join` | ✅ | Join room |
| GET | `/api/rooms/{code}/state` | ✅ | Get room state (polling fallback) |
| POST | `/api/rooms/{code}/submit` | ✅ | Submit word description |
| GET | `/api/leaderboard` | — | Leaderboard (`?period=today\|week\|all`) |
| GET | `/api/players/{id}/history` | ✅ | Paginated match history |
| GET | `/api/dictionary/search` | ✅ | Dictionary search (`?q=&level=`) |
| WS | `/ws/rooms/{code}` | ✅ | Real-time game state updates |

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (production) or SQLite (development)

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit with your values
python migrate.py             # run database migrations
uvicorn server:app --reload   # start on http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env          # set REACT_APP_BACKEND_URL
npm start                     # start on http://localhost:3000
```

### Docker
```bash
docker-compose up --build     # backend :8000, frontend :3000, redis :6379
```

## Environment Variables

See [`backend/.env.example`](backend/.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | JWT signing key (min 32 chars in production) |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `FRONTEND_URL` | ✅ | Frontend origin for CORS and room links |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP service account JSON (for Gemini) |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v                     # 19 tests: game flow, scoring, dictionary, AI, word levels
```

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:
1. **Python tests** — pytest on Python 3.11 + 3.13 matrix
2. **HTTP integration tests** — boots uvicorn, runs live endpoint tests
3. **Dockerfile lint** — Hadolint

## Dictionary Data

| Source | License | URL |
|--------|---------|-----|
| **VarCon** (Variant Conversion Info) | LGPL | [wordlist.aspell.net/varcon](http://wordlist.aspell.net/varcon/) |

The processed dictionary (`backend/data/processed/dictionary_clean.csv`) is derived from VarCon
and supplemented with manually curated entries.
VarCon is © Kevin Atkinson, released under the
[GNU Lesser General Public License (LGPL)](https://www.gnu.org/licenses/lgpl-3.0.html).

## License

MIT
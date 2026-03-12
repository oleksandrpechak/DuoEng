# DuoEng — Multiplayer Vocabulary Duel

A real-time two-player English vocabulary game where players take turns translating Ukrainian words into English. Play against a friend or challenge an AI opponent with configurable difficulty.

## How It Works

1. **Create or join a room** — pick a CEFR difficulty level (A1–C2), choose vs-human or vs-AI mode, and share the room link
2. **Translate the word** — each turn shows a Ukrainian word; type the English translation, a close synonym, or a description
3. **Instant scoring** — answers are scored locally in under 50ms: exact match → 2 pts, close/partial → 1 pt, wrong → 0 pts
4. **First to target score wins** — ELO ratings update after each match

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| **Frontend** | React 19, Tailwind CSS, Radix UI, React Router 7 |
| **Database** | PostgreSQL (production), SQLite (development) |
| **Scoring** | Instant local scoring (difflib similarity + substring matching) |
| **AI Opponent** | Configurable difficulty (easy/medium/hard), instant probabilistic moves |
| **Auth** | JWT (guest sessions + Google OAuth) |
| **Deployment** | Render (backend web service + frontend static site) |

## Features

- **Real-time gameplay** — WebSocket room updates with HTTP polling fallback; all responses under 2 seconds
- **Instant local scoring** — no LLM dependency; uses sequence matching, typo tolerance, substring matching, and description detection
- **vs-AI mode** — play against an AI opponent (easy/medium/hard) that responds instantly with difficulty-tuned accuracy
- **CEFR difficulty levels** — A1 (Beginner) through C2 (Mastery) word selection per room
- **Flexible answer support** — exact translations, close spellings, synonyms, and multi-word descriptions all earn points
- **ELO rating system** — persistent player rankings with K-factor 32
- **Leaderboard** — filterable by Today / This Week / All Time
- **Game history** — paginated match history with opponent info and scores
- **Favourite words** — save and practice specific words
- **Custom words** — add your own word pairs for practice
- **Wrong words practice** — replay words you've gotten wrong
- **Second chance / steal** — opponent can steal points on a wrong answer
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
│   ├── game_service.py      # Game logic (rooms, turns, scoring, ELO, AI auto-move, history)
│   ├── scoring.py           # Instant local scoring (difflib + substring + description matching)
│   ├── ai_player.py         # AI opponent (difficulty-tuned probabilistic scoring, no delays)
│   ├── models.py            # SQLAlchemy models (Player, Room, Match, Move, Word)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── config.py            # Settings from environment variables
│   ├── security.py          # JWT token creation and verification
│   ├── ws_manager.py        # WebSocket connection manager (rooms, broadcast, pause)
│   ├── elo.py               # ELO rating calculation
│   ├── rate_limit.py        # Sliding window rate limiter + violation tracking
│   ├── routers/
│   │   ├── ai.py            # AI text generation endpoint (Gemini)
│   │   ├── oauth.py         # Google OAuth endpoints
│   │   └── word_levels.py   # CEFR word classification endpoint
│   └── services/
│       └── gemini_service.py # Vertex AI / Gemini integration
├── alembic/                  # Database migrations
├── tests/                    # Pytest test suite (50 tests)
├── data/processed/           # Dictionary CSV data
└── scripts/                  # Seed and data preparation scripts

frontend/
├── src/
│   ├── App.js               # Routes: /, /join/:code, /lobby/:code, /game/:code, /end/:code
│   ├── pages/
│   │   ├── LandingPage.jsx  # Home: auth, create/join room, leaderboard, history, dictionary
│   │   ├── LobbyPage.jsx    # Room lobby: settings display, link sharing, wait for opponent
│   │   ├── GamePage.jsx     # Gameplay: word display, answer input, timer, scoreboard, AI turns
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
| POST | `/api/rooms` | ✅ | Create room (mode, target score, CEFR level, AI difficulty) |
| POST | `/api/rooms/{code}/join` | ✅ | Join room |
| GET | `/api/rooms/{code}/state` | ✅ | Get room state (polling fallback) |
| POST | `/api/rooms/{code}/submit` | ✅ | Submit word translation |
| POST | `/api/rooms/{code}/leave` | ✅ | Leave room (forfeit) |
| POST | `/api/rooms/{code}/second-chance` | ✅ | Submit second chance / steal answer |
| GET | `/api/leaderboard` | — | Leaderboard (`?period=today\|week\|all`) |
| GET | `/api/players/{id}/stats` | ✅ | Player stats |
| GET | `/api/players/{id}/history` | ✅ | Paginated match history |
| POST | `/api/players/{id}/nickname` | ✅ | Change nickname |
| GET | `/api/dictionary/search` | ✅ | Dictionary search (`?q=&level=`) |
| POST | `/api/favourites` | ✅ | Add favourite word |
| GET | `/api/favourites` | ✅ | List favourite words |
| DELETE | `/api/favourites/{word_id}` | ✅ | Remove favourite word |
| POST | `/api/custom-words` | ✅ | Add custom word pair |
| GET | `/api/custom-words` | ✅ | List custom words |
| DELETE | `/api/custom-words/{id}` | ✅ | Delete custom word |
| GET | `/api/wrong-words` | ✅ | Get words you've gotten wrong |
| WS | `/ws/rooms/{code}` | ✅ | Real-time game state updates |

## Scoring System

All scoring is **instant and local** (no external API calls). Response times are consistently under 50ms.

| Answer Quality | Points | Example |
|---------------|--------|---------|
| **Exact match** | 2 | "hello" for "hello" |
| **High similarity** (ratio ≥ 0.75) | 2 | "helo" for "hello" (typo tolerance) |
| **Medium similarity** (ratio ≥ 0.50) | 1 | Recognizable but imprecise |
| **Substring match** (min 3 chars) | 1 | "run" for "running" |
| **Description containing the word** | 1 | "a bright light" for "light" |
| **Similar word in description** | 1 | Multi-word answer with a close match |
| **Partial match on compound word** | 1 | "break" for "break down" |
| **Wrong / unrelated** | 0 | "banana" for "computer" |

## AI Opponent

The **vs-AI** mode lets you play against an instant AI opponent. The AI:

- Responds **immediately** — no delays, no DB lookups for wrong answers
- Uses **probability-based scoring** tuned per difficulty level
- Does **not check words** — it simulates realistic play with configurable accuracy

| Difficulty | Correct (2 pts) | Partial (1 pt) | Wrong (0 pts) |
|------------|:----------------:|:---------------:|:-------------:|
| Easy | 35% | 15% | 50% |
| Medium | 60% | 20% | 20% |
| Hard | 85% | 10% | 5% |

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
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP service account JSON (for Gemini AI text generation) |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |

> **Note:** Gemini credentials are only needed for the `/api/ai/generate` and `/api/v1/words/level` endpoints. Core game scoring and AI opponent work without any external API keys.

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v                     # 50 tests: scoring, AI, game flow, dictionary, word levels
```

Test coverage includes:
- **Scoring**: exact match, typo tolerance, case insensitivity, substring/superstring, descriptions, compound words, empty inputs, wrong answers
- **AI opponent**: all difficulty levels, probability distributions, helper functions, fallback behavior
- **Game flow**: room creation, join, turn validation, submit answer, ELO updates, leaderboard, vs-AI mode
- **vs-AI turns**: AI auto-plays instantly after human submit, AI plays on state-poll, multi-round turn alternation
- **API**: dictionary search, word level classification, AI text generation, auth, error handling

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

## Credits

- Ukrainian-English dictionary data: [dmklinger/ukrainian](https://github.com/dmklinger/ukrainian) — CC BY-SA 3.0
- MIT License — your code
- CC BY-SA 3.0 — dictionary data (see NOTICE)
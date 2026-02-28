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
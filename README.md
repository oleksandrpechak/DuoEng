# DuoVocab Duel

Two-player Ukrainian→English vocabulary game.

## Features

- **Create/Join Room**: Share 6-character room code with friends
- **Guest Authentication**: Simple nickname-based auth
- **Turn-based Play**: Alternate turns translating words
- **Live Scoreboard**: Real-time score updates via polling
- **Two Game Modes**:
  - **Classic**: No time limit, relaxed play
  - **Challenge**: 30-second timer per turn

## Scoring Rules

- **Correct translation** = +2 points
- **English sentence/description containing the word** = +1 point
- **Wrong answer or timeout** = 0 points

## Word Database

- 50 sample words included (25 B1, 25 B2 level)
- CSV import pipeline for adding more words

### Import Words

```bash
cd /app/backend
python import_words.py path/to/your_words.csv
```

CSV format:
```csv
ua,en,level
привіт,hello,B1
незважаючи на,despite,B2
```

## Tech Stack

- **Frontend**: React 19, Tailwind CSS, Shadcn UI
- **Backend**: FastAPI (Python)
- **Database**: SQLite

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/guest` | Create guest user |
| POST | `/api/rooms` | Create game room |
| POST | `/api/rooms/{code}/join` | Join room |
| GET | `/api/rooms/{code}/state` | Get game state (polling) |
| POST | `/api/rooms/{code}/turn` | Submit answer |
| GET | `/api/words/count` | Get word statistics |

## Database Schema

- `users` - Guest players
- `words` - UA→EN vocabulary (B1/B2 levels)
- `game_rooms` - Game sessions
- `game_players` - Player-room relationships
- `user_word_history` - Track seen words per user
- `turns` - Turn history with timing

## Test Checklist

- [ ] Create room with nickname
- [ ] Copy room code
- [ ] Second player joins with code
- [ ] Game starts automatically
- [ ] Correct answer awards +2 points
- [ ] Description answer awards +1 point
- [ ] Wrong answer awards 0 points
- [ ] Challenge mode timer works
- [ ] Timer expiry awards 0 points
- [ ] Win condition triggers at target score
- [ ] End screen shows final scores
- [ ] Play again returns to home

## Local Development Setup

### Option 1: Docker Compose (Recommended)

```bash
# Clone and run
docker-compose up --build

# Access:
# Frontend: http://localhost:3000
# Backend:  http://localhost:8001
```

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8001:8001"
    environment:
      - CORS_ORIGINS=http://localhost:3000
    volumes:
      - ./backend:/app
  
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_BACKEND_URL=http://localhost:8001
    depends_on:
      - backend
```

### Option 2: Manual Setup (npm/yarn)

**Terminal 1 - Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment
export CORS_ORIGINS="http://localhost:3000"

# Run server
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
yarn install

# Create .env.local
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env.local

# Run dev server
yarn start
```

### Quick Test
```bash
# Check backend
curl http://localhost:8001/api/
# {"message":"DuoVocab Duel API"}

# Check word count
curl http://localhost:8001/api/words/count
# {"total":50,"by_level":{"B1":25,"B2":25}}
```

from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import sqlite3
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import random
import string
from contextlib import contextmanager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# SQLite database path
DB_PATH = ROOT_DIR / 'duovocab.db'

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='server.log'
)
logger = logging.getLogger(__name__)

# Database connection helper
@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Initialize SQLite database with all required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table (guest auth)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Words table (UA→EN vocabulary)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS words (
                id TEXT PRIMARY KEY,
                ua TEXT NOT NULL,
                en TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('B1', 'B2'))
            )
        ''')
        
        # Game rooms
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_rooms (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('classic', 'challenge')),
                target_score INTEGER NOT NULL DEFAULT 10,
                status TEXT NOT NULL CHECK(status IN ('waiting', 'playing', 'finished')),
                created_at TEXT NOT NULL,
                winner_id TEXT
            )
        ''')
        
        # Game players (links users to rooms)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_players (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                player_order INTEGER NOT NULL,
                FOREIGN KEY (room_id) REFERENCES game_rooms(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(room_id, user_id)
            )
        ''')
        
        # User word history (track seen words)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_word_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                word_id TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (word_id) REFERENCES words(id),
                UNIQUE(user_id, word_id)
            )
        ''')
        
        # Turns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                word_id TEXT NOT NULL,
                answer TEXT,
                points_earned INTEGER,
                started_at TEXT NOT NULL,
                expires_at TEXT,
                completed_at TEXT,
                status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'expired')),
                FOREIGN KEY (room_id) REFERENCES game_rooms(id),
                FOREIGN KEY (player_id) REFERENCES game_players(id),
                FOREIGN KEY (word_id) REFERENCES words(id)
            )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")

# Initialize database on startup
init_db()

# Seed sample words if empty
def seed_sample_words():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM words")
        count = cursor.fetchone()['cnt']
        
        if count == 0:
            # Sample Ukrainian-English vocabulary (50 words)
            sample_words = [
                # B1 Level (25 words)
                ("привіт", "hello", "B1"),
                ("дякую", "thank you", "B1"),
                ("будь ласка", "please", "B1"),
                ("добрий ранок", "good morning", "B1"),
                ("на добраніч", "good night", "B1"),
                ("так", "yes", "B1"),
                ("ні", "no", "B1"),
                ("вода", "water", "B1"),
                ("хліб", "bread", "B1"),
                ("молоко", "milk", "B1"),
                ("яблуко", "apple", "B1"),
                ("книга", "book", "B1"),
                ("стіл", "table", "B1"),
                ("стілець", "chair", "B1"),
                ("вікно", "window", "B1"),
                ("двері", "door", "B1"),
                ("будинок", "house", "B1"),
                ("машина", "car", "B1"),
                ("собака", "dog", "B1"),
                ("кіт", "cat", "B1"),
                ("друг", "friend", "B1"),
                ("сім'я", "family", "B1"),
                ("любов", "love", "B1"),
                ("час", "time", "B1"),
                ("день", "day", "B1"),
                # B2 Level (25 words)
                ("незважаючи на", "despite", "B2"),
                ("однак", "however", "B2"),
                ("отже", "therefore", "B2"),
                ("насправді", "actually", "B2"),
                ("очевидно", "obviously", "B2"),
                ("можливо", "perhaps", "B2"),
                ("зрештою", "eventually", "B2"),
                ("здебільшого", "mostly", "B2"),
                ("зазвичай", "usually", "B2"),
                ("визначати", "determine", "B2"),
                ("досягати", "achieve", "B2"),
                ("впливати", "influence", "B2"),
                ("порівнювати", "compare", "B2"),
                ("враження", "impression", "B2"),
                ("досвід", "experience", "B2"),
                ("середовище", "environment", "B2"),
                ("розвиток", "development", "B2"),
                ("суспільство", "society", "B2"),
                ("уряд", "government", "B2"),
                ("економіка", "economy", "B2"),
                ("культура", "culture", "B2"),
                ("освіта", "education", "B2"),
                ("наука", "science", "B2"),
                ("технологія", "technology", "B2"),
                ("здоров'я", "health", "B2"),
            ]
            
            for ua, en, level in sample_words:
                cursor.execute(
                    "INSERT INTO words (id, ua, en, level) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), ua, en, level)
                )
            
            conn.commit()
            logger.info(f"Seeded {len(sample_words)} sample words")

seed_sample_words()

# Pydantic Models
class GuestAuthRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)

class GuestAuthResponse(BaseModel):
    user_id: str
    nickname: str

class CreateRoomRequest(BaseModel):
    user_id: str
    mode: str = "classic"
    target_score: int = 10

class JoinRoomRequest(BaseModel):
    user_id: str

class SubmitAnswerRequest(BaseModel):
    user_id: str
    answer: str

class PlayerInfo(BaseModel):
    user_id: str
    nickname: str
    score: int
    is_current_turn: bool

class TurnInfo(BaseModel):
    turn_id: str
    word_ua: str
    time_remaining: Optional[int] = None
    current_player_id: str

class GameStateResponse(BaseModel):
    room_id: str
    code: str
    mode: str
    target_score: int
    status: str
    players: List[PlayerInfo]
    current_turn: Optional[TurnInfo] = None
    last_feedback: Optional[dict] = None
    winner: Optional[dict] = None

class RoomCreatedResponse(BaseModel):
    room_id: str
    code: str

# Helper functions
def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_unseen_word_for_user(conn, user_id: str) -> Optional[dict]:
    """Get a random word the user hasn't seen"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT w.id, w.ua, w.en, w.level 
        FROM words w 
        WHERE w.id NOT IN (
            SELECT word_id FROM user_word_history WHERE user_id = ?
        )
        ORDER BY RANDOM() 
        LIMIT 1
    ''', (user_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    # If all words seen, reset history and get random word
    cursor.execute("DELETE FROM user_word_history WHERE user_id = ?", (user_id,))
    cursor.execute("SELECT id, ua, en, level FROM words ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    return dict(row) if row else None

def check_answer(user_answer: str, correct_en: str, word_ua: str) -> tuple:
    """
    Check answer and return (points, feedback_type)
    - Exact match: +2 points
    - Contains correct word in description: +1 point
    - Wrong: 0 points
    """
    user_answer = user_answer.strip().lower()
    correct_en = correct_en.strip().lower()
    
    # Exact match
    if user_answer == correct_en:
        return 2, "correct"
    
    # Check if it's a valid description containing the word
    if correct_en in user_answer and len(user_answer) > len(correct_en):
        return 1, "partial"
    
    # Wrong answer
    return 0, "wrong"

def get_current_player_turn(conn, room_id: str) -> Optional[str]:
    """Get the player ID whose turn it is"""
    cursor = conn.cursor()
    
    # Count completed turns to determine whose turn
    cursor.execute('''
        SELECT COUNT(*) as turn_count FROM turns 
        WHERE room_id = ? AND status IN ('completed', 'expired')
    ''', (room_id,))
    turn_count = cursor.fetchone()['turn_count']
    
    # Get players ordered by player_order
    cursor.execute('''
        SELECT gp.id, gp.user_id FROM game_players gp
        WHERE gp.room_id = ?
        ORDER BY gp.player_order
    ''', (room_id,))
    players = cursor.fetchall()
    
    if not players:
        return None
    
    # Alternate turns
    current_idx = turn_count % len(players)
    return players[current_idx]['id']

# API Endpoints

@api_router.get("/")
async def root():
    return {"message": "DuoVocab Duel API"}

@api_router.post("/auth/guest", response_model=GuestAuthResponse)
async def guest_auth(request: GuestAuthRequest):
    """Create a guest user with nickname"""
    with get_db() as conn:
        cursor = conn.cursor()
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute(
            "INSERT INTO users (id, nickname, created_at) VALUES (?, ?, ?)",
            (user_id, request.nickname, now)
        )
        
        return GuestAuthResponse(user_id=user_id, nickname=request.nickname)

@api_router.post("/rooms", response_model=RoomCreatedResponse)
async def create_room(request: CreateRoomRequest):
    """Create a new game room"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify user exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (request.user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
        
        room_id = str(uuid.uuid4())
        code = generate_room_code()
        now = datetime.now(timezone.utc).isoformat()
        
        # Create room
        cursor.execute('''
            INSERT INTO game_rooms (id, code, mode, target_score, status, created_at)
            VALUES (?, ?, ?, ?, 'waiting', ?)
        ''', (room_id, code, request.mode, request.target_score, now))
        
        # Add creator as first player
        player_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO game_players (id, room_id, user_id, score, player_order)
            VALUES (?, ?, ?, 0, 1)
        ''', (player_id, room_id, request.user_id))
        
        return RoomCreatedResponse(room_id=room_id, code=code)

@api_router.post("/rooms/{code}/join")
async def join_room(code: str, request: JoinRoomRequest):
    """Join an existing room"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Find room
        cursor.execute("SELECT * FROM game_rooms WHERE code = ?", (code.upper(),))
        room = cursor.fetchone()
        
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        room = dict(room)
        
        if room['status'] != 'waiting':
            raise HTTPException(status_code=400, detail="Room is not accepting players")
        
        # Check if user already in room
        cursor.execute('''
            SELECT id FROM game_players WHERE room_id = ? AND user_id = ?
        ''', (room['id'], request.user_id))
        if cursor.fetchone():
            return {"message": "Already in room", "room_id": room['id']}
        
        # Count current players
        cursor.execute("SELECT COUNT(*) as cnt FROM game_players WHERE room_id = ?", (room['id'],))
        player_count = cursor.fetchone()['cnt']
        
        if player_count >= 2:
            raise HTTPException(status_code=400, detail="Room is full")
        
        # Add player
        player_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO game_players (id, room_id, user_id, score, player_order)
            VALUES (?, ?, ?, 0, 2)
        ''', (player_id, room['id'], request.user_id))
        
        # Start game if 2 players
        cursor.execute("UPDATE game_rooms SET status = 'playing' WHERE id = ?", (room['id'],))
        
        # Create first turn
        first_player_id = get_current_player_turn(conn, room['id'])
        if first_player_id:
            cursor.execute("SELECT user_id FROM game_players WHERE id = ?", (first_player_id,))
            first_user = cursor.fetchone()
            if first_user:
                word = get_unseen_word_for_user(conn, first_user['user_id'])
                if word:
                    turn_id = str(uuid.uuid4())
                    now = datetime.now(timezone.utc)
                    expires_at = None
                    if room['mode'] == 'challenge':
                        expires_at = (now + timedelta(seconds=30)).isoformat()
                    
                    cursor.execute('''
                        INSERT INTO turns (id, room_id, player_id, word_id, started_at, expires_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'active')
                    ''', (turn_id, room['id'], first_player_id, word['id'], now.isoformat(), expires_at))
                    
                    # Mark word as seen
                    cursor.execute('''
                        INSERT OR IGNORE INTO user_word_history (id, user_id, word_id, seen_at)
                        VALUES (?, ?, ?, ?)
                    ''', (str(uuid.uuid4()), first_user['user_id'], word['id'], now.isoformat()))
        
        return {"message": "Joined room", "room_id": room['id']}

@api_router.get("/rooms/{code}/state", response_model=GameStateResponse)
async def get_room_state(code: str, user_id: str):
    """Get current game state (for polling)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Find room
        cursor.execute("SELECT * FROM game_rooms WHERE code = ?", (code.upper(),))
        room = cursor.fetchone()
        
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        room = dict(room)
        
        # Check for expired turns in challenge mode
        if room['mode'] == 'challenge' and room['status'] == 'playing':
            cursor.execute('''
                SELECT * FROM turns 
                WHERE room_id = ? AND status = 'active' AND expires_at IS NOT NULL
            ''', (room['id'],))
            active_turn = cursor.fetchone()
            
            if active_turn:
                active_turn = dict(active_turn)
                expires_at = datetime.fromisoformat(active_turn['expires_at'])
                if datetime.now(timezone.utc) > expires_at:
                    # Expire the turn
                    cursor.execute('''
                        UPDATE turns SET status = 'expired', points_earned = 0, completed_at = ?
                        WHERE id = ?
                    ''', (datetime.now(timezone.utc).isoformat(), active_turn['id']))
                    conn.commit()
        
        # Get players
        cursor.execute('''
            SELECT gp.*, u.nickname 
            FROM game_players gp 
            JOIN users u ON gp.user_id = u.id 
            WHERE gp.room_id = ?
            ORDER BY gp.player_order
        ''', (room['id'],))
        players_rows = cursor.fetchall()
        
        # Get current turn player
        current_player_id = get_current_player_turn(conn, room['id'])
        
        players = []
        for p in players_rows:
            p = dict(p)
            players.append(PlayerInfo(
                user_id=p['user_id'],
                nickname=p['nickname'],
                score=p['score'],
                is_current_turn=(p['id'] == current_player_id)
            ))
        
        # Get active turn
        current_turn = None
        cursor.execute('''
            SELECT t.*, w.ua, w.en, gp.user_id as player_user_id
            FROM turns t 
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            WHERE t.room_id = ? AND t.status = 'active'
        ''', (room['id'],))
        turn_row = cursor.fetchone()
        
        if turn_row:
            turn_row = dict(turn_row)
            time_remaining = None
            if turn_row['expires_at']:
                expires = datetime.fromisoformat(turn_row['expires_at'])
                remaining = (expires - datetime.now(timezone.utc)).total_seconds()
                time_remaining = max(0, int(remaining))
            
            current_turn = TurnInfo(
                turn_id=turn_row['id'],
                word_ua=turn_row['ua'],
                time_remaining=time_remaining,
                current_player_id=turn_row['player_user_id']
            )
        
        # Get last feedback (last completed turn)
        last_feedback = None
        cursor.execute('''
            SELECT t.*, w.ua, w.en, u.nickname
            FROM turns t 
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            JOIN users u ON gp.user_id = u.id
            WHERE t.room_id = ? AND t.status IN ('completed', 'expired')
            ORDER BY t.completed_at DESC
            LIMIT 1
        ''', (room['id'],))
        last_turn = cursor.fetchone()
        
        if last_turn:
            last_turn = dict(last_turn)
            last_feedback = {
                "player_nickname": last_turn['nickname'],
                "word_ua": last_turn['ua'],
                "correct_en": last_turn['en'],
                "answer": last_turn['answer'] or "(no answer)",
                "points": last_turn['points_earned'],
                "status": last_turn['status']
            }
        
        # Check winner
        winner = None
        if room['status'] == 'finished' and room['winner_id']:
            cursor.execute('''
                SELECT u.nickname FROM users u WHERE u.id = ?
            ''', (room['winner_id'],))
            winner_row = cursor.fetchone()
            if winner_row:
                winner = {"user_id": room['winner_id'], "nickname": winner_row['nickname']}
        
        return GameStateResponse(
            room_id=room['id'],
            code=room['code'],
            mode=room['mode'],
            target_score=room['target_score'],
            status=room['status'],
            players=players,
            current_turn=current_turn,
            last_feedback=last_feedback,
            winner=winner
        )

@api_router.post("/rooms/{code}/turn")
async def submit_answer(code: str, request: SubmitAnswerRequest):
    """Submit an answer for current turn"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Find room
        cursor.execute("SELECT * FROM game_rooms WHERE code = ?", (code.upper(),))
        room = cursor.fetchone()
        
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        room = dict(room)
        
        if room['status'] != 'playing':
            raise HTTPException(status_code=400, detail="Game is not in progress")
        
        # Get active turn
        cursor.execute('''
            SELECT t.*, w.en, gp.user_id as player_user_id, gp.id as game_player_id, w.ua
            FROM turns t 
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            WHERE t.room_id = ? AND t.status = 'active'
        ''', (room['id'],))
        turn = cursor.fetchone()
        
        if not turn:
            raise HTTPException(status_code=400, detail="No active turn")
        
        turn = dict(turn)
        
        # Verify it's this player's turn
        if turn['player_user_id'] != request.user_id:
            raise HTTPException(status_code=403, detail="Not your turn")
        
        # Check if expired (challenge mode)
        if turn['expires_at']:
            expires = datetime.fromisoformat(turn['expires_at'])
            if datetime.now(timezone.utc) > expires:
                # Mark as expired
                cursor.execute('''
                    UPDATE turns SET status = 'expired', points_earned = 0, completed_at = ?
                    WHERE id = ?
                ''', (datetime.now(timezone.utc).isoformat(), turn['id']))
                
                # Create next turn
                await _create_next_turn(conn, room, turn['game_player_id'])
                
                return {"message": "Turn expired", "points": 0, "correct_answer": turn['en']}
        
        # Check answer
        points, feedback_type = check_answer(request.answer, turn['en'], turn['ua'])
        
        # Update turn
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            UPDATE turns SET answer = ?, points_earned = ?, completed_at = ?, status = 'completed'
            WHERE id = ?
        ''', (request.answer, points, now, turn['id']))
        
        # Update player score
        cursor.execute('''
            UPDATE game_players SET score = score + ? WHERE id = ?
        ''', (points, turn['game_player_id']))
        
        # Check for winner
        cursor.execute("SELECT score FROM game_players WHERE id = ?", (turn['game_player_id'],))
        new_score = cursor.fetchone()['score']
        
        if new_score >= room['target_score']:
            # Game over!
            cursor.execute('''
                UPDATE game_rooms SET status = 'finished', winner_id = ? WHERE id = ?
            ''', (turn['player_user_id'], room['id']))
            
            return {
                "message": "You win!",
                "points": points,
                "feedback": feedback_type,
                "correct_answer": turn['en'],
                "game_over": True
            }
        
        # Create next turn
        await _create_next_turn(conn, room, turn['game_player_id'])
        
        return {
            "message": "Answer submitted",
            "points": points,
            "feedback": feedback_type,
            "correct_answer": turn['en']
        }

async def _create_next_turn(conn, room: dict, last_player_id: str):
    """Create the next turn for the other player"""
    cursor = conn.cursor()
    
    # Get next player
    cursor.execute('''
        SELECT gp.id, gp.user_id FROM game_players gp
        WHERE gp.room_id = ? AND gp.id != ?
    ''', (room['id'], last_player_id))
    next_player = cursor.fetchone()
    
    if not next_player:
        return
    
    next_player = dict(next_player)
    
    # Get unseen word for next player
    word = get_unseen_word_for_user(conn, next_player['user_id'])
    if not word:
        return
    
    turn_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = None
    if room['mode'] == 'challenge':
        expires_at = (now + timedelta(seconds=30)).isoformat()
    
    cursor.execute('''
        INSERT INTO turns (id, room_id, player_id, word_id, started_at, expires_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
    ''', (turn_id, room['id'], next_player['id'], word['id'], now.isoformat(), expires_at))
    
    # Mark word as seen
    cursor.execute('''
        INSERT OR IGNORE INTO user_word_history (id, user_id, word_id, seen_at)
        VALUES (?, ?, ?, ?)
    ''', (str(uuid.uuid4()), next_player['user_id'], word['id'], now.isoformat()))

@api_router.get("/words/count")
async def get_word_count():
    """Get total word count"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total, level FROM words GROUP BY level")
        results = cursor.fetchall()
        counts = {r['level']: r['total'] for r in results}
        return {"total": sum(counts.values()), "by_level": counts}

# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

port = int(os.getenv("PORT", 8001))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)

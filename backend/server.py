from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import random
import sqlite3
import string
from typing import Annotated, Literal, Optional
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Path as PathParam
import jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# SQLite database path
DB_PATH = Path(os.getenv("DB_PATH", ROOT_DIR / "duovocab.db"))
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", "720"))
ROOM_CODE_ATTEMPTS = 8
CHALLENGE_TURN_SECONDS = 30

RoomCodeParam = Annotated[
    str,
    PathParam(min_length=6, max_length=6, pattern=r"^[A-Za-z0-9]{6}$"),
]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="server.log",
)
logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    """Yield a SQLite connection with FK checks enabled."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Initialize SQLite database with all required tables."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Users table (guest auth)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Words table (UA→EN vocabulary)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                id TEXT PRIMARY KEY,
                ua TEXT NOT NULL,
                en TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('B1', 'B2'))
            )
            """
        )

        # Game rooms
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_rooms (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('classic', 'challenge')),
                target_score INTEGER NOT NULL DEFAULT 10,
                status TEXT NOT NULL CHECK(status IN ('waiting', 'playing', 'finished')),
                created_at TEXT NOT NULL,
                winner_id TEXT,
                FOREIGN KEY (winner_id) REFERENCES users(id)
            )
            """
        )

        # Game players (links users to rooms)
        cursor.execute(
            """
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
            """
        )

        # User word history (track seen words)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_word_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                word_id TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (word_id) REFERENCES words(id),
                UNIQUE(user_id, word_id)
            )
            """
        )

        # Turns table
        cursor.execute(
            """
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
            """
        )

        logger.info("Database initialized successfully")


# Initialize database on startup
init_db()


def seed_sample_words():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM words")
        count = cursor.fetchone()["cnt"]

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
                    (str(uuid.uuid4()), ua, en, level),
                )

            logger.info("Seeded %s sample words", len(sample_words))


seed_sample_words()


# Pydantic models
class GuestAuthRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nickname: str = Field(..., min_length=2, max_length=20)


class GuestAuthResponse(BaseModel):
    user_id: str
    nickname: str
    access_token: str
    token_type: str = "bearer"


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["classic", "challenge"] = "classic"
    target_score: int = Field(default=10, ge=1, le=100)


class SubmitAnswerRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    answer: str = Field(..., min_length=1, max_length=200)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Answer cannot be empty")
        return value


class PlayerInfo(BaseModel):
    user_id: str
    nickname: str
    score: int
    is_current_turn: bool


class TurnInfo(BaseModel):
    turn_id: str
    word_ua: Optional[str] = None
    time_remaining: Optional[int] = None
    current_player_id: str


class GameStateResponse(BaseModel):
    room_id: str
    code: str
    mode: str
    target_score: int
    status: str
    players: list[PlayerInfo]
    current_turn: Optional[TurnInfo] = None
    last_feedback: Optional[dict] = None
    winner: Optional[dict] = None


class RoomCreatedResponse(BaseModel):
    room_id: str
    code: str


# Helper functions

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXP_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id


def ensure_user_exists(conn: sqlite3.Connection, user_id: str) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=401, detail="Unknown user")


def generate_room_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def get_room_by_code(conn: sqlite3.Connection, code: str) -> Optional[dict]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM game_rooms WHERE code = ?", (code.upper(),))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_room_player(
    conn: sqlite3.Connection, room_id: str, user_id: str
) -> Optional[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM game_players WHERE room_id = ? AND user_id = ?",
        (room_id, user_id),
    )
    return cursor.fetchone()


def get_unseen_word_for_user(conn: sqlite3.Connection, user_id: str) -> Optional[dict]:
    """Get a random word the user hasn't seen."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT w.id, w.ua, w.en, w.level
        FROM words w
        WHERE w.id NOT IN (
            SELECT word_id FROM user_word_history WHERE user_id = ?
        )
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    if row:
        return dict(row)

    # If all words seen, reset history and get random word
    cursor.execute("DELETE FROM user_word_history WHERE user_id = ?", (user_id,))
    cursor.execute("SELECT id, ua, en, level FROM words ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    return dict(row) if row else None


def check_answer(user_answer: str, correct_en: str) -> tuple[int, str]:
    """Return (points, feedback_type)."""
    normalized_answer = user_answer.strip().lower()
    normalized_correct = correct_en.strip().lower()

    if normalized_answer == normalized_correct:
        return 2, "correct"

    if normalized_correct in normalized_answer and len(normalized_answer) > len(normalized_correct):
        return 1, "partial"

    return 0, "wrong"


def get_current_player_turn(conn: sqlite3.Connection, room_id: str) -> Optional[str]:
    """Get the game_player id whose turn it should be."""
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) as turn_count FROM turns
        WHERE room_id = ? AND status IN ('completed', 'expired')
        """,
        (room_id,),
    )
    turn_count = cursor.fetchone()["turn_count"]

    cursor.execute(
        """
        SELECT gp.id
        FROM game_players gp
        WHERE gp.room_id = ?
        ORDER BY gp.player_order
        """,
        (room_id,),
    )
    players = cursor.fetchall()
    if not players:
        return None

    current_idx = turn_count % len(players)
    return players[current_idx]["id"]


def _create_turn_for_player(conn: sqlite3.Connection, room: dict, player_id: str) -> bool:
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM game_players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    if not player:
        return False

    word = get_unseen_word_for_user(conn, player["user_id"])
    if not word:
        return False

    turn_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = None
    if room["mode"] == "challenge":
        expires_at = (now + timedelta(seconds=CHALLENGE_TURN_SECONDS)).isoformat()

    cursor.execute(
        """
        INSERT INTO turns (id, room_id, player_id, word_id, started_at, expires_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
        """,
        (turn_id, room["id"], player_id, word["id"], now.isoformat(), expires_at),
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO user_word_history (id, user_id, word_id, seen_at)
        VALUES (?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), player["user_id"], word["id"], now.isoformat()),
    )

    return True


def _create_next_turn(conn: sqlite3.Connection, room: dict, last_player_id: str) -> None:
    """Create the next turn for the other player if no active turn exists."""
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM turns WHERE room_id = ? AND status = 'active' LIMIT 1",
        (room["id"],),
    )
    if cursor.fetchone():
        return

    cursor.execute(
        """
        SELECT gp.id
        FROM game_players gp
        WHERE gp.room_id = ? AND gp.id != ?
        ORDER BY gp.player_order
        LIMIT 1
        """,
        (room["id"], last_player_id),
    )
    next_player = cursor.fetchone()
    if not next_player:
        return

    _create_turn_for_player(conn, room, next_player["id"])


def _expire_active_turn_if_needed(conn: sqlite3.Connection, room: dict) -> bool:
    if room["mode"] != "challenge" or room["status"] != "playing":
        return False

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.id, t.player_id, t.expires_at
        FROM turns t
        WHERE t.room_id = ? AND t.status = 'active' AND t.expires_at IS NOT NULL
        ORDER BY t.started_at ASC
        LIMIT 1
        """,
        (room["id"],),
    )
    active_turn = cursor.fetchone()
    if not active_turn:
        return False

    expires_at = datetime.fromisoformat(active_turn["expires_at"])
    now = datetime.now(timezone.utc)
    if now <= expires_at:
        return False

    cursor.execute(
        """
        UPDATE turns
        SET status = 'expired', points_earned = 0, completed_at = ?
        WHERE id = ? AND status = 'active'
        """,
        (now.isoformat(), active_turn["id"]),
    )
    if cursor.rowcount != 1:
        return False

    _create_next_turn(conn, room, active_turn["player_id"])
    return True


# API endpoints
@api_router.get("/")
async def root():
    return {"message": "DuoVocab Duel API"}


@api_router.post("/auth/guest", response_model=GuestAuthResponse)
async def guest_auth(request: GuestAuthRequest):
    """Create a guest user and return a signed auth token."""
    with get_db() as conn:
        cursor = conn.cursor()
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            "INSERT INTO users (id, nickname, created_at) VALUES (?, ?, ?)",
            (user_id, request.nickname, now),
        )

        return GuestAuthResponse(
            user_id=user_id,
            nickname=request.nickname,
            access_token=create_access_token(user_id),
        )


@api_router.post("/rooms", response_model=RoomCreatedResponse)
async def create_room(
    request: CreateRoomRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Create a new game room for the authenticated user."""
    with get_db() as conn:
        cursor = conn.cursor()
        ensure_user_exists(conn, current_user_id)

        room_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        code = None
        for _ in range(ROOM_CODE_ATTEMPTS):
            candidate = generate_room_code()
            try:
                cursor.execute(
                    """
                    INSERT INTO game_rooms (id, code, mode, target_score, status, created_at)
                    VALUES (?, ?, ?, ?, 'waiting', ?)
                    """,
                    (room_id, candidate, request.mode, request.target_score, now),
                )
                code = candidate
                break
            except sqlite3.IntegrityError as exc:
                if "game_rooms.code" in str(exc).lower():
                    continue
                raise HTTPException(status_code=400, detail="Failed to create room") from exc

        if not code:
            raise HTTPException(
                status_code=503,
                detail="Failed to allocate a unique room code. Please retry.",
            )

        player_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO game_players (id, room_id, user_id, score, player_order)
            VALUES (?, ?, ?, 0, 1)
            """,
            (player_id, room_id, current_user_id),
        )

        return RoomCreatedResponse(room_id=room_id, code=code)


@api_router.post("/rooms/{code}/join")
async def join_room(code: RoomCodeParam, current_user_id: str = Depends(get_current_user_id)):
    """Join an existing room as the authenticated user."""
    with get_db() as conn:
        cursor = conn.cursor()
        ensure_user_exists(conn, current_user_id)

        room = get_room_by_code(conn, code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        existing_player = get_room_player(conn, room["id"], current_user_id)
        if existing_player:
            return {"message": "Already in room", "room_id": room["id"]}

        if room["status"] != "waiting":
            raise HTTPException(status_code=400, detail="Room is not accepting players")

        cursor.execute("SELECT COUNT(*) as cnt FROM game_players WHERE room_id = ?", (room["id"],))
        player_count = cursor.fetchone()["cnt"]
        if player_count >= 2:
            raise HTTPException(status_code=400, detail="Room is full")

        player_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO game_players (id, room_id, user_id, score, player_order)
            VALUES (?, ?, ?, 0, ?)
            """,
            (player_id, room["id"], current_user_id, player_count + 1),
        )

        # Start game when second player joins.
        cursor.execute("UPDATE game_rooms SET status = 'playing' WHERE id = ?", (room["id"],))
        room["status"] = "playing"

        # Create first turn if it does not exist yet.
        cursor.execute(
            "SELECT 1 FROM turns WHERE room_id = ? AND status = 'active' LIMIT 1",
            (room["id"],),
        )
        if not cursor.fetchone():
            first_player_id = get_current_player_turn(conn, room["id"])
            if first_player_id:
                _create_turn_for_player(conn, room, first_player_id)

        return {"message": "Joined room", "room_id": room["id"]}


@api_router.get("/rooms/{code}/state", response_model=GameStateResponse)
async def get_room_state(code: RoomCodeParam, current_user_id: str = Depends(get_current_user_id)):
    """Get the game state visible to the authenticated room member."""
    with get_db() as conn:
        cursor = conn.cursor()
        ensure_user_exists(conn, current_user_id)

        room = get_room_by_code(conn, code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        current_member = get_room_player(conn, room["id"], current_user_id)
        if not current_member:
            raise HTTPException(status_code=403, detail="You are not a member of this room")

        _expire_active_turn_if_needed(conn, room)

        cursor.execute(
            """
            SELECT gp.*, u.nickname
            FROM game_players gp
            JOIN users u ON gp.user_id = u.id
            WHERE gp.room_id = ?
            ORDER BY gp.player_order
            """,
            (room["id"],),
        )
        players_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT t.*, w.ua, w.en, gp.user_id as player_user_id
            FROM turns t
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            WHERE t.room_id = ? AND t.status = 'active'
            LIMIT 1
            """,
            (room["id"],),
        )
        active_turn = cursor.fetchone()

        current_player_game_id = None
        current_turn = None
        if active_turn:
            turn_row = dict(active_turn)
            current_player_game_id = turn_row["player_id"]
            time_remaining = None
            if turn_row["expires_at"]:
                expires = datetime.fromisoformat(turn_row["expires_at"])
                remaining = (expires - datetime.now(timezone.utc)).total_seconds()
                time_remaining = max(0, int(remaining))

            visible_word = turn_row["ua"] if turn_row["player_user_id"] == current_user_id else None
            current_turn = TurnInfo(
                turn_id=turn_row["id"],
                word_ua=visible_word,
                time_remaining=time_remaining,
                current_player_id=turn_row["player_user_id"],
            )
        else:
            current_player_game_id = get_current_player_turn(conn, room["id"])

        players = [
            PlayerInfo(
                user_id=row["user_id"],
                nickname=row["nickname"],
                score=row["score"],
                is_current_turn=(row["id"] == current_player_game_id),
            )
            for row in players_rows
        ]

        last_feedback = None
        cursor.execute(
            """
            SELECT t.*, w.ua, w.en, u.nickname
            FROM turns t
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            JOIN users u ON gp.user_id = u.id
            WHERE t.room_id = ? AND t.status IN ('completed', 'expired')
            ORDER BY t.completed_at DESC
            LIMIT 1
            """,
            (room["id"],),
        )
        last_turn = cursor.fetchone()
        if last_turn:
            last_feedback = {
                "player_nickname": last_turn["nickname"],
                "word_ua": last_turn["ua"],
                "correct_en": last_turn["en"],
                "answer": last_turn["answer"] or "(no answer)",
                "points": last_turn["points_earned"],
                "status": last_turn["status"],
            }

        winner = None
        if room["status"] == "finished" and room["winner_id"]:
            cursor.execute("SELECT nickname FROM users WHERE id = ?", (room["winner_id"],))
            winner_row = cursor.fetchone()
            if winner_row:
                winner = {"user_id": room["winner_id"], "nickname": winner_row["nickname"]}

        return GameStateResponse(
            room_id=room["id"],
            code=room["code"],
            mode=room["mode"],
            target_score=room["target_score"],
            status=room["status"],
            players=players,
            current_turn=current_turn,
            last_feedback=last_feedback,
            winner=winner,
        )


@api_router.post("/rooms/{code}/turn")
async def submit_answer(
    code: RoomCodeParam,
    request: SubmitAnswerRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Submit an answer for the authenticated player's room turn."""
    with get_db() as conn:
        cursor = conn.cursor()
        ensure_user_exists(conn, current_user_id)

        room = get_room_by_code(conn, code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        if room["status"] != "playing":
            raise HTTPException(status_code=400, detail="Game is not in progress")

        current_member = get_room_player(conn, room["id"], current_user_id)
        if not current_member:
            raise HTTPException(status_code=403, detail="You are not a member of this room")

        _expire_active_turn_if_needed(conn, room)

        cursor.execute(
            """
            SELECT t.*, w.en, w.ua, gp.user_id as player_user_id, gp.id as game_player_id
            FROM turns t
            JOIN words w ON t.word_id = w.id
            JOIN game_players gp ON t.player_id = gp.id
            WHERE t.room_id = ? AND t.status = 'active'
            LIMIT 1
            """,
            (room["id"],),
        )
        turn = cursor.fetchone()
        if not turn:
            raise HTTPException(status_code=400, detail="No active turn")

        turn = dict(turn)
        if turn["player_user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not your turn")

        # Handle the edge case where turn expires between read and write.
        if turn["expires_at"]:
            expires = datetime.fromisoformat(turn["expires_at"])
            now_dt = datetime.now(timezone.utc)
            if now_dt > expires:
                cursor.execute(
                    """
                    UPDATE turns
                    SET status = 'expired', points_earned = 0, completed_at = ?
                    WHERE id = ? AND status = 'active'
                    """,
                    (now_dt.isoformat(), turn["id"]),
                )
                if cursor.rowcount == 1:
                    _create_next_turn(conn, room, turn["game_player_id"])
                return {
                    "message": "Turn expired",
                    "points": 0,
                    "feedback": "expired",
                    "correct_answer": turn["en"],
                }

        points, feedback_type = check_answer(request.answer, turn["en"])
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            UPDATE turns
            SET answer = ?, points_earned = ?, completed_at = ?, status = 'completed'
            WHERE id = ? AND status = 'active'
            """,
            (request.answer, points, now, turn["id"]),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=409, detail="Turn was already processed")

        cursor.execute(
            "UPDATE game_players SET score = score + ? WHERE id = ?",
            (points, turn["game_player_id"]),
        )

        cursor.execute("SELECT score FROM game_players WHERE id = ?", (turn["game_player_id"],))
        new_score = cursor.fetchone()["score"]

        if new_score >= room["target_score"]:
            cursor.execute(
                "UPDATE game_rooms SET status = 'finished', winner_id = ? WHERE id = ?",
                (turn["player_user_id"], room["id"]),
            )
            room["status"] = "finished"
            return {
                "message": "You win!",
                "points": points,
                "feedback": feedback_type,
                "correct_answer": turn["en"],
                "game_over": True,
            }

        _create_next_turn(conn, room, turn["game_player_id"])

        return {
            "message": "Answer submitted",
            "points": points,
            "feedback": feedback_type,
            "correct_answer": turn["en"],
        }


@api_router.get("/words/count")
async def get_word_count():
    """Get total word count."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total, level FROM words GROUP BY level")
        results = cursor.fetchall()
        counts = {row["level"]: row["total"] for row in results}
        return {"total": sum(counts.values()), "by_level": counts}


# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

port = int(os.getenv("PORT", 8001))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)

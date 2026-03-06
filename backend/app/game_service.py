from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import secrets
import string
from typing import Any, Mapping, Optional
import uuid
import random

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, seed_from_dmklinger
from .elo import expected_score, update_elo
from .rate_limit import SlidingWindowLimiter, ViolationTracker
from .scoring import LLMScorer
from .security import AuthContext, create_access_token
from .ai_player import ai_take_turn
from . import ws_manager

logger = logging.getLogger("duoeng.game")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: datetime | str | None) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def generate_room_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# In-memory word cache
_word_cache: dict[str, list] = {}


def _get_cached_words(level: str) -> list:
    """Load words for a level into memory cache."""
    if level not in _word_cache or len(_word_cache[level]) < 10:
        with get_db() as session:
            rows = session.execute(
                text(
                    """
                SELECT id, ua, en, level FROM words
                WHERE level = :level
                ORDER BY RANDOM()
                LIMIT 200
            """
                ),
                {"level": level},
            ).mappings().all()
            _word_cache[level] = [dict(r) for r in rows]
    return _word_cache[level]


def pick_next_word(room_code: str) -> dict:
    # Fetch room and level
    with get_db() as session:
        room = session.execute(
            text("SELECT word_level FROM rooms WHERE code = :code"),
            {"code": room_code},
        ).mappings().first()
        level = room["word_level"] if room and room["word_level"] else "B1"
    words = _get_cached_words(level)
    if not words:
        with get_db() as session:
            row = session.execute(
                text("SELECT id, ua, en, level FROM words ORDER BY RANDOM() LIMIT 1")
            ).mappings().first()
            return dict(row)
    word = words.pop(random.randint(0, len(words) - 1))
    return word


class GameService:
    def __init__(self, scorer: LLMScorer) -> None:
        self.scorer = scorer
        self.submit_limiter = SlidingWindowLimiter()
        self.ws_message_limiter = SlidingWindowLimiter()
        self.join_fail_tracker = ViolationTracker()
        self.violation_tracker = ViolationTracker()
        # Room code → player_id mapping for "use favourites" mode
        self._favourite_rooms: dict[str, str] = {}
        # Room code → player_id mapping for "use custom words" mode
        self._custom_word_rooms: dict[str, str] = {}
        # Room code → list of specific word_ids for "practice wrong words" mode
        self._word_id_rooms: dict[str, list[str]] = {}
        # Room code → AI difficulty for AI rooms
        self._ai_rooms: dict[str, str] = {}
        # Active second-chance tasks (room_code → asyncio.Task)
        self._second_chance_tasks: dict[str, asyncio.Task] = {}

    # ---------- SQL helpers ----------
    def _one(
        self,
        session: Session,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[Mapping[str, Any]]:
        return session.execute(text(query), params or {}).mappings().first()

    def _all(
        self,
        session: Session,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[Mapping[str, Any]]:
        return list(session.execute(text(query), params or {}).mappings().all())

    def _scalar(
        self,
        session: Session,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        return session.execute(text(query), params or {}).scalar_one()

    # ---------- Auth / Players ----------
    def create_guest(self, nickname: str) -> dict[str, Any]:
        candidate = nickname.strip()
        if len(candidate) < 2:
            raise HTTPException(status_code=422, detail="Nickname too short")

        player_id = str(uuid.uuid4())
        created_at = _utc_now()

        with get_db() as session:
            final_name = candidate
            suffix_attempt = 0
            while True:
                try:
                    session.execute(
                        text(
                            """
                            INSERT INTO players (
                                id, nickname, elo, wins, losses,
                                total_games, total_response_time, total_moves, created_at
                            )
                            VALUES (
                                :id, :nickname, :elo, :wins, :losses,
                                :total_games, :total_response_time, :total_moves, :created_at
                            )
                            """
                        ),
                        {
                            "id": player_id,
                            "nickname": final_name,
                            "elo": settings.default_elo,
                            "wins": 0,
                            "losses": 0,
                            "total_games": 0,
                            "total_response_time": 0.0,
                            "total_moves": 0,
                            "created_at": created_at,
                        },
                    )
                    break
                except IntegrityError:
                    session.rollback()
                    suffix_attempt += 1
                    if suffix_attempt > 20:
                        raise HTTPException(status_code=409, detail="Nickname already taken")
                    final_name = f"{candidate}{secrets.randbelow(9000) + 1000}"

        is_admin = final_name.lower() in settings.admin_nicknames
        token = create_access_token(player_id=player_id, nickname=final_name, is_admin=is_admin)
        logger.info(
            "Guest auth success",
            extra={"event": "auth_success", "player_id": player_id, "nickname": final_name},
        )
        return {
            "user_id": player_id,
            "player_id": player_id,
            "nickname": final_name,
            "access_token": token,
            "token_type": "bearer",
        }

    def ensure_player_exists(self, player_id: str) -> None:
        with get_db() as session:
            row = self._one(
                session,
                "SELECT id FROM players WHERE id = :player_id",
                {"player_id": player_id},
            )
            if not row:
                raise HTTPException(status_code=401, detail="Player not found")

    # ---------- Security / bans ----------
    def _is_banned(self, session: Session, entity_type: str, entity_id: str) -> bool:
        row = self._one(
            session,
            """
            SELECT banned_until
            FROM bans
            WHERE entity_type = :entity_type AND entity_id = :entity_id
            ORDER BY banned_until DESC
            LIMIT 1
            """,
            {"entity_type": entity_type, "entity_id": entity_id},
        )
        if not row:
            return False
        banned_until = _parse_dt(row["banned_until"])
        return bool(banned_until and banned_until > _utc_now())

    def _ban_entity(
        self,
        session: Session,
        entity_type: str,
        entity_id: str,
        reason: str,
        seconds: Optional[int] = None,
    ) -> None:
        ban_seconds = seconds if seconds is not None else settings.ban_seconds
        banned_until = _utc_now() + timedelta(seconds=ban_seconds)
        session.execute(
            text(
                """
                INSERT INTO bans (entity_type, entity_id, reason, banned_until, created_at)
                VALUES (:entity_type, :entity_id, :reason, :banned_until, :created_at)
                """
            ),
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "reason": reason,
                "banned_until": banned_until,
                "created_at": _utc_now(),
            },
        )
        logger.warning(
            "Entity temporarily banned",
            extra={
                "event": "temporary_ban",
                "reason": reason,
                "player_id": entity_id if entity_type == "player" else None,
                "ip": entity_id if entity_type == "ip" else None,
            },
        )

    def _ensure_not_banned(self, session: Session, player_id: str, ip: str) -> None:
        if self._is_banned(session, "player", player_id):
            raise HTTPException(status_code=403, detail="Player is temporarily banned")
        if self._is_banned(session, "ip", ip):
            raise HTTPException(status_code=403, detail="IP is temporarily banned")

    def _record_violation(self, session: Session, player_id: str, reason: str) -> None:
        record = self.violation_tracker.record(player_id, period_seconds=60)
        logger.warning(
            "Suspicious behavior detected",
            extra={"event": "suspicious_action", "player_id": player_id, "reason": reason},
        )
        if record.count >= settings.suspicious_attempts_per_min:
            self._ban_entity(session, "player", player_id, f"too_many_violations:{reason}")

    # ---------- Room helpers ----------
    def _fetch_room(self, session: Session, room_code: str) -> Optional[Mapping[str, Any]]:
        return self._one(
            session,
            "SELECT * FROM rooms WHERE code = :code",
            {"code": room_code.upper()},
        )

    def _fetch_membership(
        self,
        session: Session,
        room_code: str,
        player_id: str,
    ) -> Optional[Mapping[str, Any]]:
        return self._one(
            session,
            "SELECT * FROM room_players WHERE room_code = :room_code AND player_id = :player_id",
            {"room_code": room_code.upper(), "player_id": player_id},
        )

    def _fetch_room_players(self, session: Session, room_code: str) -> list[Mapping[str, Any]]:
        return self._all(
            session,
            """
            SELECT rp.player_id, rp.player_order, rp.score, p.nickname, p.elo
            FROM room_players rp
            JOIN players p ON p.id = rp.player_id
            WHERE rp.room_code = :room_code
            ORDER BY rp.player_order
            """,
            {"room_code": room_code.upper()},
        )

    def _pick_random_word(self, session: Session, word_level: str = "B1", favourite_player_id: str | None = None, custom_word_player_id: str | None = None, word_ids: list[str] | None = None) -> Mapping[str, Any]:
        # If specific word_ids provided (practice wrong words mode)
        if word_ids:
            row = self._one(
                session,
                """
                SELECT ua, en FROM words WHERE id IN ({})
                ORDER BY RANDOM() LIMIT 1
                """.format(",".join(f"'{wid}'" for wid in word_ids[:200])),
            )
            if row:
                return row

        # If custom_word_player_id is set, try to pick from their custom words first
        if custom_word_player_id:
            row = self._one(
                session,
                """
                SELECT ua_word AS ua, en_word AS en FROM custom_words
                WHERE player_id = :player_id AND approved = 1
                ORDER BY RANDOM() LIMIT 1
                """,
                {"player_id": custom_word_player_id},
            )
            if row:
                return row

        # If favourite_player_id is set, try to pick from their favourites first
        if favourite_player_id:
            row = self._one(
                session,
                """
                SELECT w.ua, w.en FROM favourite_words fw
                JOIN words w ON w.id = fw.word_id
                WHERE fw.player_id = :player_id
                ORDER BY RANDOM() LIMIT 1
                """,
                {"player_id": favourite_player_id},
            )
            if row:
                return row
            # If no favourites, fall through to normal selection

        row = self._one(
            session,
            "SELECT ua, en FROM words WHERE level = :level ORDER BY RANDOM() LIMIT 1",
            {"level": word_level},
        )
        if not row:
            # Fallback to B1 if requested level has no words
            logger.warning(
                "No words for level %s, falling back to B1",
                word_level,
                extra={"event": "word_level_fallback", "requested_level": word_level},
            )
            row = self._one(session, "SELECT ua, en FROM words WHERE level = 'B1' ORDER BY RANDOM() LIMIT 1")
        if not row:
            # Last resort: any word at all
            row = self._one(session, "SELECT ua, en FROM words ORDER BY RANDOM() LIMIT 1")
        if not row:
            # Final fallback: try dictionary_entries table (seeding may still be in progress)
            logger.warning(
                "words table empty, falling back to dictionary_entries",
                extra={"event": "word_fallback_dict_entries"},
            )
            row = self._one(
                session,
                "SELECT ua_word AS ua, en_word AS en FROM dictionary_entries ORDER BY RANDOM() LIMIT 1",
            )
        if not row:
            # Emergency: both tables empty — trigger synchronous seed right now
            logger.critical(
                "Both words and dictionary_entries tables are empty! Triggering emergency seed.",
                extra={"event": "emergency_seed"},
            )
            try:
                seed_from_dmklinger(force=False)
                # After seeding, retry the query
                row = self._one(
                    session,
                    "SELECT ua, en FROM words WHERE level = :level ORDER BY RANDOM() LIMIT 1",
                    {"level": word_level},
                )
                if not row:
                    row = self._one(session, "SELECT ua, en FROM words ORDER BY RANDOM() LIMIT 1")
                if not row:
                    row = self._one(
                        session,
                        "SELECT ua_word AS ua, en_word AS en FROM dictionary_entries ORDER BY RANDOM() LIMIT 1",
                    )
            except Exception:
                logger.exception("Emergency seed failed")
        if not row:
            raise HTTPException(status_code=500, detail="No words available — database seeding may have failed. Please restart the server.")
        return row

    def _elapsed_seconds(self, room: Mapping[str, Any]) -> float:
        started_at = _parse_dt(room.get("turn_started_at"))
        if not started_at:
            return 0.0
        return max(0.0, (_utc_now() - started_at).total_seconds())

    def _other_player_id(self, session: Session, room_code: str, player_id: str) -> Optional[str]:
        row = self._one(
            session,
            """
            SELECT player_id
            FROM room_players
            WHERE room_code = :room_code AND player_id != :player_id
            ORDER BY player_order
            LIMIT 1
            """,
            {"room_code": room_code.upper(), "player_id": player_id},
        )
        return str(row["player_id"]) if row else None

    def _apply_timeout_if_needed(self, session: Session, room_code: str) -> bool:
        room = self._fetch_room(session, room_code)
        if not room or room["status"] != "playing" or not room["current_turn"]:
            return False

        elapsed = self._elapsed_seconds(room)
        if elapsed <= settings.turn_timeout_seconds:
            return False

        match_id = room["match_id"]
        if not match_id:
            return False

        existing_move = self._one(
            session,
            "SELECT id FROM moves WHERE match_id = :match_id AND turn_number = :turn_number",
            {"match_id": match_id, "turn_number": room["turn_number"]},
        )
        if existing_move:
            return False

        session.execute(
            text(
                """
                INSERT INTO moves (
                    id, match_id, room_code, turn_number, player_id,
                    ua_word, correct_answer, user_answer, score_awarded,
                    response_time, scoring_source, is_timeout, created_at
                ) VALUES (
                    :id, :match_id, :room_code, :turn_number, :player_id,
                    :ua_word, :correct_answer, :user_answer, :score_awarded,
                    :response_time, :scoring_source, :is_timeout, :created_at
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "match_id": match_id,
                "room_code": room["code"],
                "turn_number": room["turn_number"],
                "player_id": room["current_turn"],
                "ua_word": room["current_word_ua"] or "",
                "correct_answer": room["current_word_en"] or "",
                "user_answer": "",
                "score_awarded": 0,
                "response_time": float(settings.turn_timeout_seconds),
                "scoring_source": "timeout",
                "is_timeout": True,
                "created_at": _utc_now(),
            },
        )

        session.execute(
            text(
                """
                UPDATE players
                SET total_response_time = total_response_time + :response_time,
                    total_moves = total_moves + 1
                WHERE id = :player_id
                """
            ),
            {"response_time": float(settings.turn_timeout_seconds), "player_id": room["current_turn"]},
        )

        self._advance_turn(session, room, str(room["current_turn"]))
        logger.info(
            "Turn timeout applied",
            extra={"event": "turn_timeout", "room_code": room["code"], "player_id": room["current_turn"]},
        )
        return True

    def _advance_turn(self, session: Session, room: Mapping[str, Any], last_player_id: str) -> None:
        next_player_id = self._other_player_id(session, str(room["code"]), last_player_id)
        if not next_player_id:
            return

        word_level = room.get("word_level") or "B1"
        room_code = str(room["code"])
        fav_player = self._favourite_rooms.get(room_code)
        custom_player = self._custom_word_rooms.get(room_code)
        word_ids = self._word_id_rooms.get(room_code)
        word = self._pick_random_word(
            session,
            word_level=word_level,
            favourite_player_id=fav_player,
            custom_word_player_id=custom_player,
            word_ids=word_ids,
        )
        next_turn_number = int(room["turn_number"]) + 1
        session.execute(
            text(
                """
                UPDATE rooms
                SET current_turn = :current_turn,
                    turn_started_at = :turn_started_at,
                    turn_number = :turn_number,
                    current_word_ua = :current_word_ua,
                    current_word_en = :current_word_en
                WHERE code = :code
                """
            ),
            {
                "current_turn": next_player_id,
                "turn_started_at": _utc_now(),
                "turn_number": next_turn_number,
                "current_word_ua": word["ua"],
                "current_word_en": word["en"],
                "code": room["code"],
            },
        )

    def _finish_match(self, session: Session, room: Mapping[str, Any], winner_id: str) -> None:
        loser_id = self._other_player_id(session, str(room["code"]), winner_id)
        if not loser_id:
            return

        winner = self._one(
            session,
            "SELECT elo FROM players WHERE id = :player_id",
            {"player_id": winner_id},
        )
        loser = self._one(
            session,
            "SELECT elo FROM players WHERE id = :player_id",
            {"player_id": loser_id},
        )
        if not winner or not loser:
            return

        expected_winner = expected_score(winner["elo"], loser["elo"])
        expected_loser = expected_score(loser["elo"], winner["elo"])

        winner_new_elo = update_elo(winner["elo"], expected_winner, 1, k=settings.k_factor)
        loser_new_elo = update_elo(loser["elo"], expected_loser, 0, k=settings.k_factor)

        session.execute(
            text(
                """
                UPDATE players
                SET elo = :elo, wins = wins + 1, total_games = total_games + 1
                WHERE id = :player_id
                """
            ),
            {"elo": winner_new_elo, "player_id": winner_id},
        )
        session.execute(
            text(
                """
                UPDATE players
                SET elo = :elo, losses = losses + 1, total_games = total_games + 1
                WHERE id = :player_id
                """
            ),
            {"elo": loser_new_elo, "player_id": loser_id},
        )

        session.execute(
            text(
                """
                UPDATE matches
                SET winner_id = :winner_id, finished_at = :finished_at
                WHERE id = :match_id
                """
            ),
            {"winner_id": winner_id, "finished_at": _utc_now(), "match_id": room["match_id"]},
        )

        session.execute(
            text(
                """
                UPDATE rooms
                SET status = 'finished',
                    current_turn = NULL,
                    turn_started_at = NULL,
                    current_word_ua = NULL,
                    current_word_en = NULL
                WHERE code = :room_code
                """
            ),
            {"room_code": room["code"]},
        )

        recent_wins = self._scalar(
            session,
            """
            SELECT COUNT(*)
            FROM matches
            WHERE winner_id = :winner_id
              AND finished_at >= :window_start
              AND ((player_a = :winner_id AND player_b = :loser_id)
                   OR (player_a = :loser_id AND player_b = :winner_id))
            """,
            {
                "winner_id": winner_id,
                "loser_id": loser_id,
                "window_start": _utc_now() - timedelta(minutes=1),
            },
        )

        if int(recent_wins) >= settings.farm_wins_per_min_threshold:
            self._ban_entity(
                session,
                "player",
                winner_id,
                reason="anti_farm_triggered",
                seconds=settings.ban_seconds,
            )

    # ---------- Public game operations ----------
    def create_room(self, player_id: str, mode: str, target_score: int, ip: str, word_level: str = "B1", use_favourites: bool = False, use_custom_words: bool = False, ai_difficulty: str | None = None, word_ids: list[str] | None = None) -> dict[str, Any]:
        with get_db() as session:
            self._ensure_not_banned(session, player_id, ip)

            player = self._one(
                session,
                "SELECT id FROM players WHERE id = :player_id",
                {"player_id": player_id},
            )
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")

            # For vs_ai mode, determine the AI player
            actual_mode = mode
            if mode == "vs_ai" and not ai_difficulty:
                ai_difficulty = "medium"

            code = None
            for _ in range(settings.room_code_attempts):
                candidate = generate_room_code(settings.room_code_length)
                try:
                    session.execute(
                        text(
                            """
                            INSERT INTO rooms (
                                code, created_at, status, current_turn, turn_started_at,
                                mode, target_score, turn_number, word_level, ai_difficulty
                            ) VALUES (
                                :code, :created_at, 'waiting', NULL, NULL,
                                :mode, :target_score, 0, :word_level, :ai_difficulty
                            )
                            """
                        ),
                        {
                            "code": candidate,
                            "created_at": _utc_now(),
                            "mode": actual_mode,
                            "target_score": target_score,
                            "word_level": word_level,
                            "ai_difficulty": ai_difficulty if mode == "vs_ai" else None,
                        },
                    )
                    code = candidate
                    break
                except IntegrityError:
                    session.rollback()
                    continue

            if not code:
                raise HTTPException(status_code=503, detail="Could not allocate unique room code")

            session.execute(
                text(
                    """
                    INSERT INTO room_players (room_code, player_id, player_order, score, joined_at)
                    VALUES (:room_code, :player_id, 1, 0, :joined_at)
                    """
                ),
                {"room_code": code, "player_id": player_id, "joined_at": _utc_now()},
            )

            # For vs_ai: auto-join the AI player and start the game immediately
            if mode == "vs_ai" and ai_difficulty:
                from .ai_player import AI_PLAYER_IDS
                ai_player_id = AI_PLAYER_IDS.get(ai_difficulty, AI_PLAYER_IDS["medium"])

                session.execute(
                    text(
                        """
                        INSERT INTO room_players (room_code, player_id, player_order, score, joined_at)
                        VALUES (:room_code, :player_id, 2, 0, :joined_at)
                        """
                    ),
                    {"room_code": code, "player_id": ai_player_id, "joined_at": _utc_now()},
                )

                # Start the match immediately
                match_id = str(uuid.uuid4())
                fav_player = None
                custom_player = None
                wids = word_ids
                if use_favourites:
                    fav_player = player_id
                if use_custom_words:
                    custom_player = player_id
                word = self._pick_random_word(
                    session,
                    word_level=word_level,
                    favourite_player_id=fav_player,
                    custom_word_player_id=custom_player,
                    word_ids=wids,
                )

                session.execute(
                    text(
                        """
                        INSERT INTO matches (id, room_code, player_a, player_b, started_at)
                        VALUES (:id, :room_code, :player_a, :player_b, :started_at)
                        """
                    ),
                    {
                        "id": match_id,
                        "room_code": code,
                        "player_a": player_id,
                        "player_b": ai_player_id,
                        "started_at": _utc_now(),
                    },
                )

                session.execute(
                    text(
                        """
                        UPDATE rooms
                        SET status = 'playing',
                            current_turn = :current_turn,
                            turn_started_at = :turn_started_at,
                            turn_number = 1,
                            current_word_ua = :current_word_ua,
                            current_word_en = :current_word_en,
                            match_id = :match_id
                        WHERE code = :code
                        """
                    ),
                    {
                        "current_turn": player_id,
                        "turn_started_at": _utc_now(),
                        "current_word_ua": word["ua"],
                        "current_word_en": word["en"],
                        "match_id": match_id,
                        "code": code,
                    },
                )

                self._ai_rooms[code] = ai_difficulty

        # Track favourite rooms
        if use_favourites:
            self._favourite_rooms[code] = player_id
        if use_custom_words:
            self._custom_word_rooms[code] = player_id
        if word_ids:
            self._word_id_rooms[code] = word_ids
        if mode == "vs_ai" and ai_difficulty:
            self._ai_rooms[code] = ai_difficulty

        return {
            "room_code": code,
            "code": code,
            "status": "playing" if mode == "vs_ai" else "waiting",
            "room_link": f"{settings.frontend_url}/join/{code}" if mode != "vs_ai" else None,
            "word_level": word_level,
            "mode": actual_mode,
            "ai_difficulty": ai_difficulty,
        }

    def join_room(self, room_code: str, player_id: str, ip: str) -> dict[str, Any]:
        normalized_code = room_code.upper()

        with get_db() as session:
            self._ensure_not_banned(session, player_id, ip)

            room = self._fetch_room(session, normalized_code)
            if not room:
                failure = self.join_fail_tracker.record(f"{player_id}:{ip}", 60)
                if failure.count >= settings.max_join_failures_per_min:
                    self._ban_entity(session, "player", player_id, "room_code_bruteforce")
                    self._ban_entity(session, "ip", ip, "room_code_bruteforce")
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(session, normalized_code, player_id)
            if membership:
                return {"room_code": normalized_code, "code": normalized_code, "status": room["status"]}

            player_count = int(
                self._scalar(
                    session,
                    "SELECT COUNT(*) FROM room_players WHERE room_code = :room_code",
                    {"room_code": normalized_code},
                )
            )

            if player_count >= 2:
                raise HTTPException(status_code=400, detail="Room is full")

            if room["status"] == "finished":
                raise HTTPException(status_code=400, detail="Room already finished")

            session.execute(
                text(
                    """
                    INSERT INTO room_players (room_code, player_id, player_order, score, joined_at)
                    VALUES (:room_code, :player_id, :player_order, 0, :joined_at)
                    """
                ),
                {
                    "room_code": normalized_code,
                    "player_id": player_id,
                    "player_order": player_count + 1,
                    "joined_at": _utc_now(),
                },
            )

            if player_count + 1 == 2 and room["status"] == "waiting":
                players = self._fetch_room_players(session, normalized_code)
                match_id = str(uuid.uuid4())
                word_level = room.get("word_level") or "B1"
                fav_player = self._favourite_rooms.get(normalized_code)
                custom_player = self._custom_word_rooms.get(normalized_code)
                word_ids_list = self._word_id_rooms.get(normalized_code)
                word = self._pick_random_word(
                    session,
                    word_level=word_level,
                    favourite_player_id=fav_player,
                    custom_word_player_id=custom_player,
                    word_ids=word_ids_list,
                )
                turn_player_id = players[0]["player_id"]

                session.execute(
                    text(
                        """
                        INSERT INTO matches (id, room_code, player_a, player_b, started_at)
                        VALUES (:id, :room_code, :player_a, :player_b, :started_at)
                        """
                    ),
                    {
                        "id": match_id,
                        "room_code": normalized_code,
                        "player_a": players[0]["player_id"],
                        "player_b": players[1]["player_id"],
                        "started_at": _utc_now(),
                    },
                )

                session.execute(
                    text(
                        """
                        UPDATE rooms
                        SET status = 'playing',
                            current_turn = :current_turn,
                            turn_started_at = :turn_started_at,
                            turn_number = 1,
                            current_word_ua = :current_word_ua,
                            current_word_en = :current_word_en,
                            match_id = :match_id
                        WHERE code = :code
                        """
                    ),
                    {
                        "current_turn": turn_player_id,
                        "turn_started_at": _utc_now(),
                        "current_word_ua": word["ua"],
                        "current_word_en": word["en"],
                        "match_id": match_id,
                        "code": normalized_code,
                    },
                )

            status = self._fetch_room(session, normalized_code)["status"]
            return {
                "room_code": normalized_code,
                "code": normalized_code,
                "status": status,
                "room_link": f"{settings.frontend_url}/join/{normalized_code}",
                "word_level": room.get("word_level") or "B1",
            }

    async def submit_answer(
        self,
        room_code: str,
        player_id: str,
        answer: str,
        ip: str,
        channel: str = "http",
    ) -> dict[str, Any]:
        normalized_code = room_code.upper()
        if not self.submit_limiter.allow(
            f"submit:{player_id}:{normalized_code}",
            settings.rate_limit_submits_per_min,
            60,
        ):
            with get_db() as session:
                self._ban_entity(session, "player", player_id, "submit_rate_limit")
            raise HTTPException(status_code=429, detail="Too many submit attempts")

        with get_db() as session:
            self._ensure_not_banned(session, player_id, ip)
            room = self._fetch_room(session, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(session, normalized_code, player_id)
            if not membership:
                self._record_violation(session, player_id, "submit_without_membership")
                raise HTTPException(status_code=403, detail="You are not in this room")

            self._apply_timeout_if_needed(session, normalized_code)
            room = self._fetch_room(session, normalized_code)
            if room["status"] != "playing":
                raise HTTPException(status_code=400, detail="Match is not active")

            if room["current_turn"] != player_id:
                self._record_violation(session, player_id, "submit_not_your_turn")
                raise HTTPException(status_code=403, detail="Not your turn")

            elapsed = self._elapsed_seconds(room)
            if elapsed > settings.turn_timeout_seconds:
                self._apply_timeout_if_needed(session, normalized_code)
                raise HTTPException(status_code=409, detail="Turn expired")

            existing_move = self._one(
                session,
                "SELECT id FROM moves WHERE match_id = :match_id AND turn_number = :turn_number",
                {"match_id": room["match_id"], "turn_number": room["turn_number"]},
            )
            if existing_move:
                self._record_violation(session, player_id, "double_submit")
                raise HTTPException(status_code=409, detail="Turn already submitted")

            turn_snapshot = {
                "match_id": room["match_id"],
                "turn_number": room["turn_number"],
                "correct_answer": room["current_word_en"] or "",
                "ua_word": room["current_word_ua"] or "",
                "response_time": elapsed,
            }

        # Use description-based scoring: the player describes/translates the Ukrainian word in English
        scoring = await self.scorer.score_description(
            turn_snapshot["correct_answer"], answer, ua_word=turn_snapshot["ua_word"]
        )

        with get_db() as session:
            self._ensure_not_banned(session, player_id, ip)
            room = self._fetch_room(session, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            if room["status"] != "playing":
                raise HTTPException(status_code=400, detail="Match is not active")

            if (
                room["match_id"] != turn_snapshot["match_id"]
                or room["turn_number"] != turn_snapshot["turn_number"]
                or room["current_turn"] != player_id
            ):
                raise HTTPException(status_code=409, detail="Turn changed, retry with fresh state")

            existing_move = self._one(
                session,
                "SELECT id FROM moves WHERE match_id = :match_id AND turn_number = :turn_number",
                {"match_id": room["match_id"], "turn_number": room["turn_number"]},
            )
            if existing_move:
                raise HTTPException(status_code=409, detail="Turn already submitted")

            session.execute(
                text(
                    """
                    INSERT INTO moves (
                        id, match_id, room_code, turn_number, player_id,
                        ua_word, correct_answer, user_answer, score_awarded,
                        response_time, scoring_source, is_timeout, created_at
                    ) VALUES (
                        :id, :match_id, :room_code, :turn_number, :player_id,
                        :ua_word, :correct_answer, :user_answer, :score_awarded,
                        :response_time, :scoring_source, :is_timeout, :created_at
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "match_id": room["match_id"],
                    "room_code": normalized_code,
                    "turn_number": room["turn_number"],
                    "player_id": player_id,
                    "ua_word": turn_snapshot["ua_word"],
                    "correct_answer": turn_snapshot["correct_answer"],
                    "user_answer": answer,
                    "score_awarded": scoring.score,
                    "response_time": float(turn_snapshot["response_time"]),
                    "scoring_source": scoring.source,
                    "is_timeout": False,
                    "created_at": _utc_now(),
                },
            )

            session.execute(
                text(
                    """
                    UPDATE players
                    SET total_response_time = total_response_time + :response_time,
                        total_moves = total_moves + 1
                    WHERE id = :player_id
                    """
                ),
                {"response_time": float(turn_snapshot["response_time"]), "player_id": player_id},
            )

            session.execute(
                text(
                    "SELECT ..."
                ))
            session.execute(
                text(
                    """
                    UPDATE room_players
                    SET score = score + :points
                    WHERE room_code = :room_code AND player_id = :player_id
                    """
                ),
                {"points": scoring.score, "room_code": normalized_code, "player_id": player_id},
            )

            updated_score = int(
                self._scalar(
                    session,
                    """
                    SELECT score
                    FROM room_players
                    WHERE room_code = :room_code AND player_id = :player_id
                    """,
                    {"room_code": normalized_code, "player_id": player_id},
                )
            )

            game_over = updated_score >= int(room["target_score"])
            winner_id: Optional[str] = None
            second_chance = False
            second_chance_player_id: Optional[str] = None

            if game_over:
                winner_id = player_id
                self._finish_match(session, room, winner_id)
            elif scoring.score == 0:
                # FEATURE 7: Second chance — opponent gets 10s to steal
                other_id = self._other_player_id(session, normalized_code, player_id)
                from .ai_player import is_ai_player
                if other_id and not is_ai_player(other_id):
                    second_chance = True
                    second_chance_player_id = other_id
                    # Set second_chance fields on room
                    expires_at = _utc_now() + timedelta(seconds=10)
                    session.execute(
                        text(
                            """
                            UPDATE rooms
                            SET second_chance_player = :sc_player,
                                second_chance_expires = :sc_expires
                            WHERE code = :code
                            """
                        ),
                        {
                            "sc_player": other_id,
                            "sc_expires": expires_at,
                            "code": normalized_code,
                        },
                    )
                    # Don't advance turn yet — wait for second chance
                else:
                    self._advance_turn(session, room, player_id)
            else:
                # Clear any second chance state
                session.execute(
                    text(
                        """
                        UPDATE rooms
                        SET second_chance_player = NULL,
                            second_chance_expires = NULL
                        WHERE code = :code
                        """
                    ),
                    {"code": normalized_code},
                )
                self._advance_turn(session, room, player_id)

            result = {
                "room_code": normalized_code,
                "turn_number": int(room["turn_number"]),
                "points": scoring.score,
                "scoring_source": scoring.source,
                "feedback": "exact" if scoring.score >= 2 else "correct" if scoring.score >= 1 else "wrong",
                "correct_answer": turn_snapshot["correct_answer"],
                "game_over": game_over,
                "winner_id": winner_id,
                "second_chance": second_chance,
                "second_chance_player_id": second_chance_player_id,
            }

        # After releasing the DB session, trigger AI auto-move if it's now AI's turn
        if not game_over and not second_chance:
            ai_diff = self._ai_rooms.get(normalized_code)
            if ai_diff:
                asyncio.ensure_future(self._trigger_ai_move(normalized_code, ai_diff))

        return result

    def room_state_for_player(self, room_code: str, viewer_player_id: str, ip: str) -> dict[str, Any]:
        normalized_code = room_code.upper()
        with get_db() as session:
            self._ensure_not_banned(session, viewer_player_id, ip)
            room = self._fetch_room(session, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(session, normalized_code, viewer_player_id)
            if not membership:
                raise HTTPException(status_code=403, detail="You are not in this room")

            self._apply_timeout_if_needed(session, normalized_code)
            room = self._fetch_room(session, normalized_code)
            players_rows = self._fetch_room_players(session, normalized_code)

            winner_id = None
            if room["match_id"]:
                winner_row = self._one(
                    session,
                    "SELECT winner_id FROM matches WHERE id = :match_id",
                    {"match_id": room["match_id"]},
                )
                winner_id = winner_row["winner_id"] if winner_row else None

            winner_payload = None
            if winner_id:
                winner_nick_row = self._one(
                    session,
                    "SELECT nickname FROM players WHERE id = :player_id",
                    {"player_id": winner_id},
                )
                if winner_nick_row:
                    winner_payload = {
                        "user_id": winner_id,
                        "player_id": winner_id,
                        "nickname": winner_nick_row["nickname"],
                    }

            last_feedback = None
            last_move = self._one(
                session,
                """
                SELECT m.user_answer, m.score_awarded, m.ua_word, m.correct_answer,
                       m.scoring_source, p.nickname
                FROM moves m
                JOIN players p ON p.id = m.player_id
                WHERE m.room_code = :room_code
                ORDER BY m.created_at DESC
                LIMIT 1
                """,
                {"room_code": normalized_code},
            )
            if last_move:
                last_feedback = {
                    "player_nickname": last_move["nickname"],
                    "word_ua": last_move["ua_word"],
                    "correct_en": last_move["correct_answer"],
                    "answer": last_move["user_answer"] or "(no answer)",
                    "points": last_move["score_awarded"],
                    "scoring_source": last_move["scoring_source"],
                    "status": "expired" if last_move["scoring_source"] == "timeout" else "completed",
                }

            players = [
                {
                    "user_id": row["player_id"],
                    "player_id": row["player_id"],
                    "nickname": row["nickname"],
                    "score": row["score"],
                    "elo": row["elo"],
                    "is_current_turn": bool(room["current_turn"] == row["player_id"]),
                }
                for row in players_rows
            ]

            visible_word = None
            visible_word_en = None
            if room["status"] == "playing" and room["current_turn"] == viewer_player_id:
                visible_word = room["current_word_ua"]
                visible_word_en = room["current_word_en"]

            time_remaining = None
            if room["turn_started_at"] and room["status"] == "playing":
                elapsed = self._elapsed_seconds(room)
                time_remaining = max(0, int(settings.turn_timeout_seconds - elapsed))

            current_turn = None
            if room["status"] == "playing" and room["current_turn"]:
                current_turn = {
                    "turn_id": f"{room['match_id']}:{room['turn_number']}",
                    "word_ua": visible_word,
                    "word_en": visible_word_en,
                    "time_remaining": time_remaining,
                    "current_player_id": room["current_turn"],
                }

            raw_turn_started = room["turn_started_at"]
            turn_started_str = (
                raw_turn_started.isoformat()
                if isinstance(raw_turn_started, datetime)
                else raw_turn_started
            )

            return {
                "room_code": normalized_code,
                "code": normalized_code,
                "status": room["status"],
                "mode": room["mode"],
                "target_score": room["target_score"],
                "turn_number": room["turn_number"],
                "turn_timeout_seconds": settings.turn_timeout_seconds,
                "word_level": room.get("word_level") or "B1",
                "players": players,
                "current_word_ua": visible_word,
                "current_word_en": visible_word_en,
                "current_turn_player_id": room["current_turn"],
                "turn_started_at": turn_started_str,
                "match_id": room["match_id"],
                "winner_id": winner_id,
                "current_turn": current_turn,
                "winner": winner_payload,
                "last_feedback": last_feedback,
            }

    def leaderboard(self, limit: int, period: str = "all") -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))

        # Build time filter
        time_filter = ""
        params: dict[str, Any] = {"safe_limit": safe_limit}
        if period == "today":
            time_filter = "WHERE total_games > 0 AND created_at >= :since"
            params["since"] = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            time_filter = "WHERE total_games > 0 AND created_at >= :since"
            params["since"] = _utc_now() - timedelta(days=7)

        with get_db() as session:
            rows = self._all(
                session,
                f"""
                SELECT id, nickname, elo, wins, losses, total_games, total_response_time, total_moves
                FROM players
                {time_filter}
                ORDER BY elo DESC, wins DESC, created_at ASC
                LIMIT :safe_limit
                """,
                params,
            )

        results: list[dict[str, Any]] = []
        for row in rows:
            total_games = row["total_games"]
            total_moves = row["total_moves"]
            win_rate = (row["wins"] / total_games) if total_games else 0.0
            avg_response_time = (row["total_response_time"] / total_moves) if total_moves else 0.0
            results.append(
                {
                    "player_id": row["id"],
                    "nickname": row["nickname"],
                    "elo": row["elo"],
                    "wins": row["wins"],
                    "losses": row["losses"],
                    "total_games": total_games,
                    "win_rate": round(win_rate, 4),
                    "avg_response_time": round(avg_response_time, 4),
                }
            )
        return results

    def player_stats(self, player_id: str) -> dict[str, Any]:
        with get_db() as session:
            row = self._one(
                session,
                """
                SELECT id, nickname, elo, wins, losses, total_games, total_moves,
                       total_response_time, created_at
                FROM players
                WHERE id = :player_id
                """,
                {"player_id": player_id},
            )
            if not row:
                raise HTTPException(status_code=404, detail="Player not found")

        total_games = row["total_games"]
        total_moves = row["total_moves"]
        win_rate = (row["wins"] / total_games) if total_games else 0.0
        avg_response_time = (row["total_response_time"] / total_moves) if total_moves else 0.0

        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return {
            "player_id": row["id"],
            "nickname": row["nickname"],
            "elo": row["elo"],
            "wins": row["wins"],
            "losses": row["losses"],
            "total_games": total_games,
            "total_moves": total_moves,
            "win_rate": round(win_rate, 4),
            "avg_response_time": round(avg_response_time, 4),
            "created_at": created_at,
        }

    def player_match_history(self, player_id: str, page: int = 1, per_page: int = 10) -> dict[str, Any]:
        offset = (page - 1) * per_page
        with get_db() as session:
            # Count total matches
            total = int(
                self._scalar(
                    session,
                    """
                    SELECT COUNT(*)
                    FROM matches
                    WHERE player_a = :pid OR player_b = :pid
                    """,
                    {"pid": player_id},
                )
            )

            rows = self._all(
                session,
                """
                SELECT m.id, m.room_code, m.player_a, m.player_b, m.winner_id,
                       m.started_at, m.finished_at,
                       pa.nickname AS player_a_nick, pb.nickname AS player_b_nick,
                       rpa.score AS score_a, rpb.score AS score_b
                FROM matches m
                JOIN players pa ON pa.id = m.player_a
                JOIN players pb ON pb.id = m.player_b
                LEFT JOIN room_players rpa ON rpa.room_code = m.room_code AND rpa.player_id = m.player_a
                LEFT JOIN room_players rpb ON rpb.room_code = m.room_code AND rpb.player_id = m.player_b
                WHERE m.player_a = :pid OR m.player_b = :pid
                ORDER BY m.started_at DESC
                LIMIT :per_page OFFSET :offset
                """,
                {"pid": player_id, "per_page": per_page, "offset": offset},
            )

        matches = []
        for r in rows:
            opponent_id = r["player_b"] if r["player_a"] == player_id else r["player_a"]
            opponent_nick = r["player_b_nick"] if r["player_a"] == player_id else r["player_a_nick"]
            my_score = r["score_a"] if r["player_a"] == player_id else r["score_b"]
            opp_score = r["score_b"] if r["player_a"] == player_id else r["score_a"]

            started = r["started_at"]
            if isinstance(started, datetime):
                started = started.isoformat()
            finished = r["finished_at"]
            if isinstance(finished, datetime):
                finished = finished.isoformat()

            matches.append({
                "match_id": r["id"],
                "room_code": r["room_code"],
                "opponent_id": opponent_id,
                "opponent_nickname": opponent_nick,
                "my_score": my_score or 0,
                "opponent_score": opp_score or 0,
                "won": r["winner_id"] == player_id,
                "started_at": started,
                "finished_at": finished,
            })

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "matches": matches,
        }

    def admin_batch_seed(self, actor: AuthContext, seed_words: bool, reset_stats: bool) -> dict[str, Any]:
        if not actor.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")

        seeded = 0
        if seed_words:
            seeded = seed_from_dmklinger()

        if reset_stats:
            with get_db() as session:
                session.execute(
                    text(
                        """
                        UPDATE players
                        SET elo = :default_elo, wins = 0, losses = 0, total_games = 0,
                            total_response_time = 0, total_moves = 0
                        """
                    ),
                    {"default_elo": settings.default_elo},
                )
                session.execute(text("DELETE FROM moves"))
                session.execute(text("DELETE FROM matches"))
                session.execute(text("DELETE FROM room_players"))
                session.execute(text("DELETE FROM rooms"))

        return {
            "seeded_words": seeded,
            "reset_stats": reset_stats,
        }

    def ws_message_allowed(self, room_code: str, player_id: str) -> bool:
        return self.ws_message_limiter.allow(
            f"ws:{room_code.upper()}:{player_id}",
            settings.rate_limit_ws_messages_per_min,
            60,
        )

    def leave_room(self, room_code: str, player_id: str) -> dict[str, Any]:
        """Player voluntarily leaves the room, forfeiting the match."""
        normalized_code = room_code.upper()
        with get_db() as session:
            room = self._fetch_room(session, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(session, normalized_code, player_id)
            if not membership:
                raise HTTPException(status_code=403, detail="You are not in this room")

            if room["status"] == "finished":
                return {"detail": "Match already finished"}

            # If game is playing, the other player wins by forfeit
            if room["status"] == "playing":
                winner_id = self._other_player_id(session, normalized_code, player_id)
                if winner_id:
                    self._finish_match(session, room, winner_id)
                else:
                    # Solo room — just finish it
                    session.execute(
                        text(
                            """
                            UPDATE rooms
                            SET status = 'finished',
                                current_turn = NULL,
                                turn_started_at = NULL,
                                current_word_ua = NULL,
                                current_word_en = NULL
                            WHERE code = :room_code
                            """
                        ),
                        {"room_code": normalized_code},
                    )
            elif room["status"] == "waiting":
                # Just mark room as finished
                session.execute(
                    text("UPDATE rooms SET status = 'finished' WHERE code = :room_code"),
                    {"room_code": normalized_code},
                )

            logger.info(
                "Player left room",
                extra={
                    "event": "player_left",
                    "room_code": normalized_code,
                    "player_id": player_id,
                },
            )

            return {"detail": "Left the room", "room_code": normalized_code}

    # ---------- Auth / Players ----------
    def change_nickname(self, player_id: str, new_nickname: str) -> dict[str, Any]:
        """Change player's nickname. Returns updated player info + new JWT."""
        import re
        candidate = new_nickname.strip()
        if len(candidate) < 2:
            raise HTTPException(status_code=422, detail="Nickname must be at least 2 characters")
        if len(candidate) > 20:
            raise HTTPException(status_code=422, detail="Nickname must be at most 20 characters")
        if not re.match(r'^[a-zA-Z0-9_\- \u0400-\u04FF]+$', candidate):
            raise HTTPException(
                status_code=422,
                detail="Nickname can only contain letters, digits, spaces, hyphens, and underscores",
            )

        with get_db() as session:
            player = self._one(
                session,
                "SELECT id, nickname FROM players WHERE id = :player_id",
                {"player_id": player_id},
            )
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")

            if player["nickname"] == candidate:
                is_admin = candidate.lower() in settings.admin_nicknames
                token = create_access_token(player_id=player_id, nickname=candidate, is_admin=is_admin)
                return {
                    "player_id": player_id,
                    "nickname": candidate,
                    "access_token": token,
                    "token_type": "bearer",
                }

            existing = self._one(
                session,
                "SELECT id FROM players WHERE nickname = :nickname AND id != :player_id",
                {"nickname": candidate, "player_id": player_id},
            )
            if existing:
                raise HTTPException(status_code=409, detail="Nickname already taken")

            session.execute(
                text(
                    "UPDATE players SET nickname = :nickname WHERE id = :player_id"
                ),
                {"nickname": candidate, "player_id": player_id},
            )

        is_admin = candidate.lower() in settings.admin_nicknames
        token = create_access_token(player_id=player_id, nickname=candidate, is_admin=is_admin)
        logger.info(
            "Nickname changed",
            extra={"event": "nickname_changed", "player_id": player_id, "new_nickname": candidate},
        )
        return {
            "player_id": player_id,
            "nickname": candidate,
            "access_token": token,
            "token_type": "bearer",
        }

    # ---------- Favourite words ----------
    def add_favourite(self, player_id: str, word_id: str) -> dict[str, Any]:
        with get_db() as session:
            word = self._one(
                session,
                "SELECT id, ua, en, level, definition, example FROM words WHERE id = :word_id",
                {"word_id": word_id},
            )
            if not word:
                raise HTTPException(status_code=404, detail="Word not found")

            existing = self._one(
                session,
                "SELECT id FROM favourite_words WHERE player_id = :player_id AND word_id = :word_id",
                {"player_id": player_id, "word_id": word_id},
            )
            if existing:
                raise HTTPException(status_code=409, detail="Word already in favourites")

            now = _utc_now()
            session.execute(
                text(
                    "INSERT INTO favourite_words (player_id, word_id, added_at) "
                    "VALUES (:player_id, :word_id, :added_at)"
                ),
                {"player_id": player_id, "word_id": word_id, "added_at": now},
            )

        return {
            "id": 0,  # auto-increment, not critical to return exact id
            "word_id": word["id"],
            "ua": word["ua"],
            "en": word["en"],
            "level": word["level"],
            "definition": word.get("definition") or None,
            "example": word.get("example") or None,
            "added_at": now.isoformat(),
        }

    def remove_favourite(self, player_id: str, word_id: str) -> dict[str, Any]:
        with get_db() as session:
            existing = self._one(
                session,
                "SELECT id FROM favourite_words WHERE player_id = :player_id AND word_id = :word_id",
                {"player_id": player_id, "word_id": word_id},
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Favourite not found")

            session.execute(
                text(
                    "DELETE FROM favourite_words WHERE player_id = :player_id AND word_id = :word_id"
                ),
                {"player_id": player_id, "word_id": word_id},
            )

        return {"detail": "Removed from favourites", "word_id": word_id}

    def list_favourites(self, player_id: str) -> list[dict[str, Any]]:
        with get_db() as session:
            rows = self._all(
                session,
                """
                SELECT fw.id, fw.word_id, w.ua, w.en, w.level,
                       w.definition, w.example, fw.added_at
                FROM favourite_words fw
                JOIN words w ON w.id = fw.word_id
                WHERE fw.player_id = :player_id
                ORDER BY fw.added_at DESC
                """,
                {"player_id": player_id},
            )

        results = []
        for row in rows:
            added_at = row["added_at"]
            if isinstance(added_at, datetime):
                added_at = added_at.isoformat()
            results.append({
                "id": row["id"],
                "word_id": row["word_id"],
                "ua": row["ua"],
                "en": row["en"],
                "level": row["level"],
                "definition": row.get("definition") or None,
                "example": row.get("example") or None,
                "added_at": added_at,
            })
        return results

    # ---------- AI auto-move (Feature 8) ----------
    async def _trigger_ai_move(self, room_code: str, difficulty: str) -> None:
        """Trigger instant AI move and scoring."""
        try:
            with get_db() as session:
                room = self._fetch_room(session, room_code)
                if not room or room["status"] != "playing":
                    return
                current_turn = room["current_turn"]
                if not current_turn:
                    return
                ua_word = room["current_word_ua"] or ""
                en_word = room["current_word_en"] or ""
                word_id = room.get("current_word_id") or ""
                word = {"ua": ua_word, "en": en_word, "id": word_id}
            # Use ws_manager.broadcast for broadcasting
            await ai_take_turn(
                room_code=room_code,
                current_word=word,
                difficulty=difficulty,
                broadcast_fn=ws_manager.broadcast,
                update_score_fn=self.update_player_score,
            )
        except Exception:
            logger.exception("AI instant move failed", extra={"event": "ai_move_failed", "room_code": room_code})

    # ---------- Second chance submit (Feature 7) ----------
    async def submit_second_chance(
        self,
        room_code: str,
        player_id: str,
        answer: str,
        ip: str,
    ) -> dict[str, Any]:
        """Handle a second-chance answer from the opponent."""
        normalized_code = room_code.upper()

        with get_db() as session:
            self._ensure_not_banned(session, player_id, ip)
            room = self._fetch_room(session, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")
            if room["status"] != "playing":
                raise HTTPException(status_code=400, detail="Match is not active")
            if room.get("second_chance_player") != player_id:
                raise HTTPException(status_code=403, detail="Not your second chance")

            # Check if expired
            sc_expires = _parse_dt(room.get("second_chance_expires"))
            if not sc_expires or _utc_now() > sc_expires:
                # Expired — clear second chance and advance turn
                session.execute(
                    text(
                        """
                        UPDATE rooms
                        SET second_chance_player = NULL,
                            second_chance_expires = NULL
                        WHERE code = :code
                        """
                    ),
                    {"code": normalized_code},
                )
                self._advance_turn(session, room, str(room["current_turn"]))
                raise HTTPException(status_code=409, detail="Second chance expired")

            correct_answer = room["current_word_en"] or ""
            ua_word = room["current_word_ua"] or ""

        # Score the answer
        scoring = await self.scorer.score_description(correct_answer, answer, ua_word=ua_word)

        with get_db() as session:
            room = self._fetch_room(session, normalized_code)
            if not room or room["status"] != "playing":
                raise HTTPException(status_code=400, detail="Match is not active")

            if scoring.score > 0:
                session.execute(
                    text(
                        """
                        UPDATE room_players
                        SET score = score + :points
                        WHERE room_code = :room_code AND player_id = :player_id
                        """
                    ),
                    {"points": scoring.score, "room_code": normalized_code, "player_id": player_id},
                )

            # Clear second chance and advance turn
            session.execute(
                text(
                    """
                    UPDATE rooms
                    SET second_chance_player = NULL,
                        second_chance_expires = NULL
                    WHERE code = :code
                    """
                ),
                {"code": normalized_code},
            )
            self._advance_turn(session, room, str(room["current_turn"]))

            updated_score = int(
                self._scalar(
                    session,
                    "SELECT score FROM room_players WHERE room_code = :rc AND player_id = :pid",
                    {"rc": normalized_code, "pid": player_id},
                )
            )
            game_over = updated_score >= int(room["target_score"])
            winner_id = None
            if game_over:
                winner_id = player_id
                self._finish_match(session, room, winner_id)

        return {
            "room_code": normalized_code,
            "points": scoring.score,
            "scoring_source": scoring.source,
            "feedback": "exact" if scoring.score >= 2 else "correct" if scoring.score >= 1 else "wrong",
            "correct_answer": correct_answer,
            "game_over": game_over,
            "winner_id": winner_id,
        }

    # ---------- Custom words (Feature 9) ----------
    def add_custom_word(self, player_id: str, ua_word: str, en_word: str) -> dict[str, Any]:
        import re
        ua = ua_word.strip()
        en = en_word.strip()

        # Validate single words only (allow hyphens)
        if " " in ua and not ua.startswith("не "):
            raise HTTPException(status_code=422, detail="Ukrainian word must be a single word")
        if " " in en:
            raise HTTPException(status_code=422, detail="English word must be a single word")
        if not re.match(r'^[\w\-\u0400-\u04FF]+$', ua):
            raise HTTPException(status_code=422, detail="Invalid Ukrainian word")
        if not re.match(r'^[a-zA-Z\-]+$', en):
            raise HTTPException(status_code=422, detail="Invalid English word")

        word_id = str(uuid.uuid4())
        now = _utc_now()

        with get_db() as session:
            existing = self._one(
                session,
                """
                SELECT id FROM custom_words
                WHERE player_id = :pid AND LOWER(ua_word) = :ua AND LOWER(en_word) = :en
                """,
                {"pid": player_id, "ua": ua.lower(), "en": en.lower()},
            )
            if existing:
                raise HTTPException(status_code=409, detail="Word pair already exists")

            session.execute(
                text(
                    """
                    INSERT INTO custom_words (id, player_id, ua_word, en_word, level, approved, created_at)
                    VALUES (:id, :player_id, :ua_word, :en_word, :level, :approved, :created_at)
                    """
                ),
                {
                    "id": word_id,
                    "player_id": player_id,
                    "ua_word": ua,
                    "en_word": en,
                    "level": "B1",  # Default, will be re-evaluated by AI
                    "approved": True,
                    "created_at": now,
                },
            )

        return {
            "id": word_id,
            "ua_word": ua,
            "en_word": en,
            "level": "B1",
            "approved": True,
            "created_at": now.isoformat(),
        }

    def list_custom_words(self, player_id: str) -> list[dict[str, Any]]:
        with get_db() as session:
            rows = self._all(
                session,
                """
                SELECT id, ua_word, en_word, level, approved, created_at
                FROM custom_words
                WHERE player_id = :pid
                ORDER BY created_at DESC
                """,
                {"pid": player_id},
            )
        results = []
        for row in rows:
            created_at = row["created_at"]
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            results.append({
                "id": row["id"],
                "ua_word": row["ua_word"],
                "en_word": row["en_word"],
                "level": row["level"],
                "approved": bool(row["approved"]),
                "created_at": created_at,
            })
        return results

    def delete_custom_word(self, player_id: str, word_id: str) -> dict[str, Any]:
        with get_db() as session:
            existing = self._one(
                session,
                "SELECT id FROM custom_words WHERE id = :wid AND player_id = :pid",
                {"wid": word_id, "pid": player_id},
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Custom word not found")
            session.execute(
                text("DELETE FROM custom_words WHERE id = :wid AND player_id = :pid"),
                {"wid": word_id, "pid": player_id},
            )
        return {"detail": "Deleted", "word_id": word_id}

    # ---------- Wrong words (Feature 10) ----------
    def get_wrong_words(self, player_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with get_db() as session:
            rows = self._all(
                session,
                """
                SELECT
                    m.ua_word,
                    m.correct_answer,
                    m.user_answer,
                    MAX(m.created_at) AS created_at,
                    COUNT(*) AS times_wrong
                FROM moves m
                WHERE m.player_id = :player_id
                  AND m.score_awarded = 0
                  AND m.is_timeout = 0
                GROUP BY m.ua_word, m.correct_answer
                ORDER BY times_wrong DESC, MAX(m.created_at) DESC
                LIMIT :lim
                """,
                {"player_id": player_id, "lim": limit},
            )

        results = []
        for row in rows:
            created_at = row["created_at"]
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            results.append({
                "ua_word": row["ua_word"],
                "correct_answer": row["correct_answer"],
                "user_answer": row["user_answer"],
                "times_wrong": row["times_wrong"],
                "created_at": created_at,
            })
        return results

    async def handle_answer_submission(room_code, player_id, answer, broadcast_fn):
        # Fetch current word
        with get_db() as session:
            room = session.execute(text("SELECT current_word_en, current_word_ua FROM rooms WHERE code = :code"), {"code": room_code}).mappings().first()
            current_word = {"en": room["current_word_en"], "ua": room["current_word_ua"]} if room else {"en": "", "ua": ""}
        # Run scoring AND next word fetch in parallel
        from .scoring import score_answer
        score_task = asyncio.create_task(score_answer(answer, current_word["en"], current_word["ua"]))
        next_word_task = asyncio.create_task(pick_next_word(room_code))
        score, next_word = await asyncio.gather(score_task, next_word_task)
        # Broadcast result + next word
        await broadcast_fn(room_code, {
            "type": "turn_result",
            "player_id": player_id,
            "answer": answer,
            "score": score,
            "correct_answer": current_word["en"],
            "next_word": next_word["ua"],
        })
        # Update room state
        with get_db() as session:
            session.execute(text("""
            UPDATE rooms SET current_word_en = :en, current_word_ua = :ua WHERE code = :code
        """), {"en": next_word["en"], "ua": next_word["ua"], "code": room_code})

    async def update_player_score(room_code: str, player_id: str, score: int, word: dict, answer: str) -> None:
        """Update score in rooms table and record the move."""
        if score == 0:
            return  # nothing to update
        from sqlalchemy import text
        from .db import get_db
        with get_db() as session:
            # Update room score for this player
            room = session.execute(
                text("SELECT * FROM rooms WHERE code = :code"),
                {"code": room_code}
            ).mappings().first()
            if not room:
                return
            # Find which score column to update (player1 or player2)
            if str(room["player1_id"]) == str(player_id):
                session.execute(text("""
                    UPDATE rooms 
                    SET score1 = score1 + :score 
                    WHERE code = :code
                """), {"score": score, "code": room_code})
            else:
                session.execute(text("""
                    UPDATE rooms 
                    SET score2 = score2 + :score 
                    WHERE code = :code
                """), {"score": score, "code": room_code})
            # Optionally: record the move in moves table if needed

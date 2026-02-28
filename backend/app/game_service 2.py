from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets
import sqlite3
import string
from typing import Any, Optional
import uuid

from fastapi import HTTPException

from .config import settings
from .db import get_db, seed_sample_words_if_empty
from .elo import expected_score, update_elo
from .rate_limit import SlidingWindowLimiter, ViolationTracker
from .scoring import LLMScorer
from .security import AuthContext, create_access_token

logger = logging.getLogger("duoeng.game")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def generate_room_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class GameService:
    def __init__(self, scorer: LLMScorer) -> None:
        self.scorer = scorer
        self.submit_limiter = SlidingWindowLimiter()
        self.ws_message_limiter = SlidingWindowLimiter()
        self.join_fail_tracker = ViolationTracker()
        self.violation_tracker = ViolationTracker()

    # ---------- Auth / Players ----------
    def create_guest(self, nickname: str) -> dict[str, Any]:
        candidate = nickname.strip()
        if len(candidate) < 2:
            raise HTTPException(status_code=422, detail="Nickname too short")

        player_id = str(uuid.uuid4())
        created_at = _utc_now_iso()

        with get_db() as conn:
            cursor = conn.cursor()
            final_name = candidate
            suffix_attempt = 0
            while True:
                try:
                    cursor.execute(
                        """
                        INSERT INTO players (id, nickname, elo, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (player_id, final_name, settings.default_elo, created_at),
                    )
                    break
                except sqlite3.IntegrityError:
                    suffix_attempt += 1
                    if suffix_attempt > 20:
                        raise HTTPException(status_code=409, detail="Nickname already taken")
                    final_name = f"{candidate}{secrets.randbelow(9000) + 1000}"

        is_admin = final_name.lower() in settings.admin_nicknames
        token = create_access_token(player_id=player_id, nickname=final_name, is_admin=is_admin)
        return {
            "user_id": player_id,
            "player_id": player_id,
            "nickname": final_name,
            "access_token": token,
            "token_type": "bearer",
        }

    def ensure_player_exists(self, player_id: str) -> None:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM players WHERE id = ?", (player_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Player not found")

    # ---------- Security / bans ----------
    def _is_banned(self, conn: sqlite3.Connection, entity_type: str, entity_id: str) -> bool:
        row = conn.execute(
            """
            SELECT banned_until
            FROM bans
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY banned_until DESC
            LIMIT 1
            """,
            (entity_type, entity_id),
        ).fetchone()
        if not row:
            return False
        return datetime.fromisoformat(row["banned_until"]) > _utc_now()

    def _ban_entity(
        self,
        conn: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        reason: str,
        seconds: Optional[int] = None,
    ) -> None:
        ban_seconds = seconds if seconds is not None else settings.ban_seconds
        banned_until = (_utc_now() + timedelta(seconds=ban_seconds)).isoformat()
        conn.execute(
            """
            INSERT INTO bans (entity_type, entity_id, reason, banned_until, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, reason, banned_until, _utc_now_iso()),
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

    def _ensure_not_banned(self, conn: sqlite3.Connection, player_id: str, ip: str) -> None:
        if self._is_banned(conn, "player", player_id):
            raise HTTPException(status_code=403, detail="Player is temporarily banned")
        if self._is_banned(conn, "ip", ip):
            raise HTTPException(status_code=403, detail="IP is temporarily banned")

    def _record_violation(self, conn: sqlite3.Connection, player_id: str, reason: str) -> None:
        record = self.violation_tracker.record(player_id, period_seconds=60)
        logger.warning(
            "Suspicious behavior detected",
            extra={"event": "suspicious_action", "player_id": player_id, "reason": reason},
        )
        if record.count >= settings.suspicious_attempts_per_min:
            self._ban_entity(conn, "player", player_id, f"too_many_violations:{reason}")

    # ---------- Room helpers ----------
    def _fetch_room(self, conn: sqlite3.Connection, room_code: str) -> Optional[sqlite3.Row]:
        return conn.execute("SELECT * FROM rooms WHERE code = ?", (room_code.upper(),)).fetchone()

    def _fetch_membership(
        self, conn: sqlite3.Connection, room_code: str, player_id: str
    ) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM room_players WHERE room_code = ? AND player_id = ?",
            (room_code.upper(), player_id),
        ).fetchone()

    def _fetch_room_players(self, conn: sqlite3.Connection, room_code: str) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT rp.player_id, rp.player_order, rp.score, p.nickname, p.elo
            FROM room_players rp
            JOIN players p ON p.id = rp.player_id
            WHERE rp.room_code = ?
            ORDER BY rp.player_order
            """,
            (room_code.upper(),),
        ).fetchall()

    def _pick_random_word(self, conn: sqlite3.Connection) -> sqlite3.Row:
        row = conn.execute("SELECT ua, en FROM words ORDER BY RANDOM() LIMIT 1").fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="No words available")
        return row

    def _elapsed_seconds(self, room: sqlite3.Row) -> float:
        started_at = _parse_dt(room["turn_started_at"])
        if not started_at:
            return 0.0
        return max(0.0, (_utc_now() - started_at).total_seconds())

    def _other_player_id(self, conn: sqlite3.Connection, room_code: str, player_id: str) -> Optional[str]:
        row = conn.execute(
            """
            SELECT player_id
            FROM room_players
            WHERE room_code = ? AND player_id != ?
            ORDER BY player_order
            LIMIT 1
            """,
            (room_code.upper(), player_id),
        ).fetchone()
        return row["player_id"] if row else None

    def _apply_timeout_if_needed(self, conn: sqlite3.Connection, room_code: str) -> bool:
        room = self._fetch_room(conn, room_code)
        if not room or room["status"] != "playing" or not room["current_turn"]:
            return False

        elapsed = self._elapsed_seconds(room)
        if elapsed <= settings.turn_timeout_seconds:
            return False

        match_id = room["match_id"]
        if not match_id:
            return False

        existing_move = conn.execute(
            "SELECT id FROM moves WHERE match_id = ? AND turn_number = ?",
            (match_id, room["turn_number"]),
        ).fetchone()
        if existing_move:
            return False

        conn.execute(
            """
            INSERT INTO moves (
                id, match_id, room_code, turn_number, player_id,
                ua_word, correct_answer, user_answer, score_awarded,
                response_time, scoring_source, is_timeout, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                match_id,
                room["code"],
                room["turn_number"],
                room["current_turn"],
                room["current_word_ua"] or "",
                room["current_word_en"] or "",
                "",
                0,
                float(settings.turn_timeout_seconds),
                "timeout",
                1,
                _utc_now_iso(),
            ),
        )

        conn.execute(
            """
            UPDATE players
            SET total_response_time = total_response_time + ?,
                total_moves = total_moves + 1
            WHERE id = ?
            """,
            (float(settings.turn_timeout_seconds), room["current_turn"]),
        )

        self._advance_turn(conn, room, room["current_turn"])
        logger.info(
            "Turn timeout applied",
            extra={"event": "turn_timeout", "room_code": room["code"], "player_id": room["current_turn"]},
        )
        return True

    def _advance_turn(self, conn: sqlite3.Connection, room: sqlite3.Row, last_player_id: str) -> None:
        next_player_id = self._other_player_id(conn, room["code"], last_player_id)
        if not next_player_id:
            return

        word = self._pick_random_word(conn)
        next_turn_number = int(room["turn_number"]) + 1
        conn.execute(
            """
            UPDATE rooms
            SET current_turn = ?, turn_started_at = ?, turn_number = ?,
                current_word_ua = ?, current_word_en = ?
            WHERE code = ?
            """,
            (
                next_player_id,
                _utc_now_iso(),
                next_turn_number,
                word["ua"],
                word["en"],
                room["code"],
            ),
        )

    def _finish_match(self, conn: sqlite3.Connection, room: sqlite3.Row, winner_id: str) -> None:
        loser_id = self._other_player_id(conn, room["code"], winner_id)
        if not loser_id:
            return

        winner = conn.execute("SELECT elo FROM players WHERE id = ?", (winner_id,)).fetchone()
        loser = conn.execute("SELECT elo FROM players WHERE id = ?", (loser_id,)).fetchone()
        if not winner or not loser:
            return

        expected_winner = expected_score(winner["elo"], loser["elo"])
        expected_loser = expected_score(loser["elo"], winner["elo"])

        winner_new_elo = update_elo(winner["elo"], expected_winner, 1, k=settings.k_factor)
        loser_new_elo = update_elo(loser["elo"], expected_loser, 0, k=settings.k_factor)

        conn.execute(
            """
            UPDATE players
            SET elo = ?, wins = wins + 1, total_games = total_games + 1
            WHERE id = ?
            """,
            (winner_new_elo, winner_id),
        )
        conn.execute(
            """
            UPDATE players
            SET elo = ?, losses = losses + 1, total_games = total_games + 1
            WHERE id = ?
            """,
            (loser_new_elo, loser_id),
        )

        conn.execute(
            """
            UPDATE matches
            SET winner_id = ?, finished_at = ?
            WHERE id = ?
            """,
            (winner_id, _utc_now_iso(), room["match_id"]),
        )

        conn.execute(
            """
            UPDATE rooms
            SET status = 'finished', current_turn = NULL, turn_started_at = NULL,
                current_word_ua = NULL, current_word_en = NULL
            WHERE code = ?
            """,
            (room["code"],),
        )

        # Anti-farm heuristic: too many wins over same opponent within one minute.
        recent_wins = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM matches
            WHERE winner_id = ?
              AND finished_at >= ?
              AND ((player_a = ? AND player_b = ?) OR (player_a = ? AND player_b = ?))
            """,
            (
                winner_id,
                (_utc_now() - timedelta(minutes=1)).isoformat(),
                winner_id,
                loser_id,
                loser_id,
                winner_id,
            ),
        ).fetchone()["cnt"]

        if recent_wins >= settings.farm_wins_per_min_threshold:
            self._ban_entity(
                conn,
                "player",
                winner_id,
                reason="anti_farm_triggered",
                seconds=settings.ban_seconds,
            )

    # ---------- Public game operations ----------
    def create_room(self, player_id: str, mode: str, target_score: int, ip: str) -> dict[str, Any]:
        with get_db() as conn:
            self._ensure_not_banned(conn, player_id, ip)

            player = conn.execute("SELECT id FROM players WHERE id = ?", (player_id,)).fetchone()
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")

            code = None
            for _ in range(settings.room_code_attempts):
                candidate = generate_room_code(settings.room_code_length)
                try:
                    conn.execute(
                        """
                        INSERT INTO rooms (
                            code, created_at, status, current_turn, turn_started_at,
                            mode, target_score, turn_number
                        ) VALUES (?, ?, 'waiting', NULL, NULL, ?, ?, 0)
                        """,
                        (candidate, _utc_now_iso(), mode, target_score),
                    )
                    code = candidate
                    break
                except sqlite3.IntegrityError:
                    continue

            if not code:
                raise HTTPException(status_code=503, detail="Could not allocate unique room code")

            conn.execute(
                """
                INSERT INTO room_players (room_code, player_id, player_order, score, joined_at)
                VALUES (?, ?, 1, 0, ?)
                """,
                (code, player_id, _utc_now_iso()),
            )

        return {"room_code": code, "code": code, "status": "waiting"}

    def join_room(self, room_code: str, player_id: str, ip: str) -> dict[str, Any]:
        normalized_code = room_code.upper()

        with get_db() as conn:
            self._ensure_not_banned(conn, player_id, ip)

            room = self._fetch_room(conn, normalized_code)
            if not room:
                failure = self.join_fail_tracker.record(f"{player_id}:{ip}", 60)
                if failure.count >= settings.max_join_failures_per_min:
                    self._ban_entity(conn, "player", player_id, "room_code_bruteforce")
                    self._ban_entity(conn, "ip", ip, "room_code_bruteforce")
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(conn, normalized_code, player_id)
            if membership:
                return {"room_code": normalized_code, "code": normalized_code, "status": room["status"]}

            player_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM room_players WHERE room_code = ?",
                (normalized_code,),
            ).fetchone()["cnt"]

            if player_count >= 2:
                raise HTTPException(status_code=400, detail="Room is full")

            if room["status"] == "finished":
                raise HTTPException(status_code=400, detail="Room already finished")

            conn.execute(
                """
                INSERT INTO room_players (room_code, player_id, player_order, score, joined_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (normalized_code, player_id, player_count + 1, _utc_now_iso()),
            )

            if player_count + 1 == 2 and room["status"] == "waiting":
                players = self._fetch_room_players(conn, normalized_code)
                match_id = str(uuid.uuid4())
                word = self._pick_random_word(conn)
                turn_player_id = players[0]["player_id"]

                conn.execute(
                    """
                    INSERT INTO matches (id, room_code, player_a, player_b, started_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        normalized_code,
                        players[0]["player_id"],
                        players[1]["player_id"],
                        _utc_now_iso(),
                    ),
                )

                conn.execute(
                    """
                    UPDATE rooms
                    SET status = 'playing', current_turn = ?, turn_started_at = ?,
                        turn_number = 1, current_word_ua = ?, current_word_en = ?, match_id = ?
                    WHERE code = ?
                    """,
                    (
                        turn_player_id,
                        _utc_now_iso(),
                        word["ua"],
                        word["en"],
                        match_id,
                        normalized_code,
                    ),
                )

            status = self._fetch_room(conn, normalized_code)["status"]
            return {"room_code": normalized_code, "code": normalized_code, "status": status}

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
            with get_db() as conn:
                self._ban_entity(conn, "player", player_id, "submit_rate_limit")
            raise HTTPException(status_code=429, detail="Too many submit attempts")

        # Phase 1: validate and capture scoring input.
        with get_db() as conn:
            self._ensure_not_banned(conn, player_id, ip)
            room = self._fetch_room(conn, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(conn, normalized_code, player_id)
            if not membership:
                self._record_violation(conn, player_id, "submit_without_membership")
                raise HTTPException(status_code=403, detail="You are not in this room")

            self._apply_timeout_if_needed(conn, normalized_code)
            room = self._fetch_room(conn, normalized_code)
            if room["status"] != "playing":
                raise HTTPException(status_code=400, detail="Match is not active")

            if room["current_turn"] != player_id:
                self._record_violation(conn, player_id, "submit_not_your_turn")
                raise HTTPException(status_code=403, detail="Not your turn")

            elapsed = self._elapsed_seconds(room)
            if elapsed > settings.turn_timeout_seconds:
                self._apply_timeout_if_needed(conn, normalized_code)
                raise HTTPException(status_code=409, detail="Turn expired")

            existing_move = conn.execute(
                "SELECT id FROM moves WHERE match_id = ? AND turn_number = ?",
                (room["match_id"], room["turn_number"]),
            ).fetchone()
            if existing_move:
                self._record_violation(conn, player_id, "double_submit")
                raise HTTPException(status_code=409, detail="Turn already submitted")

            turn_snapshot = {
                "match_id": room["match_id"],
                "turn_number": room["turn_number"],
                "correct_answer": room["current_word_en"] or "",
                "ua_word": room["current_word_ua"] or "",
                "response_time": elapsed,
            }

        scoring = await self.scorer.score(turn_snapshot["correct_answer"], answer)

        # Phase 2: transactional apply after scoring
        with get_db() as conn:
            self._ensure_not_banned(conn, player_id, ip)
            room = self._fetch_room(conn, normalized_code)
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

            existing_move = conn.execute(
                "SELECT id FROM moves WHERE match_id = ? AND turn_number = ?",
                (room["match_id"], room["turn_number"]),
            ).fetchone()
            if existing_move:
                raise HTTPException(status_code=409, detail="Turn already submitted")

            conn.execute(
                """
                INSERT INTO moves (
                    id, match_id, room_code, turn_number, player_id,
                    ua_word, correct_answer, user_answer, score_awarded,
                    response_time, scoring_source, is_timeout, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    str(uuid.uuid4()),
                    room["match_id"],
                    normalized_code,
                    room["turn_number"],
                    player_id,
                    turn_snapshot["ua_word"],
                    turn_snapshot["correct_answer"],
                    answer,
                    scoring.score,
                    float(turn_snapshot["response_time"]),
                    scoring.source,
                    _utc_now_iso(),
                ),
            )

            conn.execute(
                """
                UPDATE players
                SET total_response_time = total_response_time + ?,
                    total_moves = total_moves + 1
                WHERE id = ?
                """,
                (float(turn_snapshot["response_time"]), player_id),
            )

            conn.execute(
                """
                UPDATE room_players
                SET score = score + ?
                WHERE room_code = ? AND player_id = ?
                """,
                (scoring.score, normalized_code, player_id),
            )

            updated_score = conn.execute(
                """
                SELECT score
                FROM room_players
                WHERE room_code = ? AND player_id = ?
                """,
                (normalized_code, player_id),
            ).fetchone()["score"]

            game_over = updated_score >= room["target_score"]
            winner_id: Optional[str] = None

            if game_over:
                winner_id = player_id
                self._finish_match(conn, room, winner_id)
            else:
                self._advance_turn(conn, room, player_id)

            return {
                "room_code": normalized_code,
                "turn_number": int(room["turn_number"]),
                "points": scoring.score,
                "scoring_source": scoring.source,
                "feedback": "correct" if scoring.score == 2 else ("partial" if scoring.score == 1 else "wrong"),
                "correct_answer": turn_snapshot["correct_answer"],
                "game_over": game_over,
                "winner_id": winner_id,
            }

    def room_state_for_player(self, room_code: str, viewer_player_id: str, ip: str) -> dict[str, Any]:
        normalized_code = room_code.upper()
        with get_db() as conn:
            self._ensure_not_banned(conn, viewer_player_id, ip)
            room = self._fetch_room(conn, normalized_code)
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            membership = self._fetch_membership(conn, normalized_code, viewer_player_id)
            if not membership:
                raise HTTPException(status_code=403, detail="You are not in this room")

            self._apply_timeout_if_needed(conn, normalized_code)
            room = self._fetch_room(conn, normalized_code)

            players_rows = self._fetch_room_players(conn, normalized_code)

            winner_row = conn.execute(
                """
                SELECT winner_id
                FROM matches
                WHERE id = ?
                """,
                (room["match_id"],),
            ).fetchone()
            winner_id = winner_row["winner_id"] if winner_row else None

            winner_payload = None
            if winner_id:
                winner_nick_row = conn.execute(
                    "SELECT nickname FROM players WHERE id = ?",
                    (winner_id,),
                ).fetchone()
                if winner_nick_row:
                    winner_payload = {
                        "user_id": winner_id,
                        "player_id": winner_id,
                        "nickname": winner_nick_row["nickname"],
                    }

            last_feedback = None
            last_move = conn.execute(
                """
                SELECT m.user_answer, m.score_awarded, m.ua_word, m.correct_answer,
                       m.scoring_source, p.nickname
                FROM moves m
                JOIN players p ON p.id = m.player_id
                WHERE m.room_code = ?
                ORDER BY m.created_at DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            if last_move:
                last_feedback = {
                    "player_nickname": last_move["nickname"],
                    "word_ua": last_move["ua_word"],
                    "correct_en": last_move["correct_answer"],
                    "answer": last_move["user_answer"] or "(no answer)",
                    "points": last_move["score_awarded"],
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
            if room["status"] == "playing" and room["current_turn"] == viewer_player_id:
                visible_word = room["current_word_ua"]

            time_remaining = None
            if room["turn_started_at"] and room["status"] == "playing":
                elapsed = self._elapsed_seconds(room)
                time_remaining = max(0, int(settings.turn_timeout_seconds - elapsed))

            current_turn = None
            if room["status"] == "playing" and room["current_turn"]:
                current_turn = {
                    "turn_id": f"{room['match_id']}:{room['turn_number']}",
                    "word_ua": visible_word,
                    "time_remaining": time_remaining,
                    "current_player_id": room["current_turn"],
                }

            return {
                "room_code": normalized_code,
                "code": normalized_code,
                "status": room["status"],
                "mode": room["mode"],
                "target_score": room["target_score"],
                "turn_number": room["turn_number"],
                "turn_timeout_seconds": settings.turn_timeout_seconds,
                "players": players,
                "current_word_ua": visible_word,
                "current_turn_player_id": room["current_turn"],
                "turn_started_at": room["turn_started_at"],
                "match_id": room["match_id"],
                "winner_id": winner_id,
                "current_turn": current_turn,
                "winner": winner_payload,
                "last_feedback": last_feedback,
            }

    def leaderboard(self, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, nickname, elo, wins, losses, total_games, total_response_time, total_moves
                FROM players
                ORDER BY elo DESC, wins DESC, created_at ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

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
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, nickname, elo, wins, losses, total_games, total_moves,
                       total_response_time, created_at
                FROM players
                WHERE id = ?
                """,
                (player_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Player not found")

        total_games = row["total_games"]
        total_moves = row["total_moves"]
        win_rate = (row["wins"] / total_games) if total_games else 0.0
        avg_response_time = (row["total_response_time"] / total_moves) if total_moves else 0.0

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
            "created_at": row["created_at"],
        }

    def admin_batch_seed(self, actor: AuthContext, seed_words: bool, reset_stats: bool) -> dict[str, Any]:
        if not actor.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")

        seeded = 0
        if seed_words:
            seeded = seed_sample_words_if_empty()

        if reset_stats:
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE players
                    SET elo = ?, wins = 0, losses = 0, total_games = 0,
                        total_response_time = 0, total_moves = 0
                    """,
                    (settings.default_elo,),
                )
                conn.execute("DELETE FROM moves")
                conn.execute("DELETE FROM matches")
                conn.execute("DELETE FROM room_players")
                conn.execute("DELETE FROM rooms")

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

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
import logging
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from .config import settings
from .db import check_db_connection, clear_expired_llm_cache, get_db, init_db, seed_sample_words_if_empty
from .game_service import GameService
from .logging_utils import configure_logging
from .metrics import CONTENT_TYPE_LATEST, REQUESTS_TOTAL, generate_latest
from .rate_limit import SlidingWindowLimiter
from .routers.ai import router as ai_router
from .routers.oauth import router as oauth_router
from .routers.word_levels import router as word_levels_router
from .schemas import (
    AddCustomWordRequest,
    AddFavouriteRequest,
    AdminSeedRequest,
    ChangeNicknameRequest,
    ChangeNicknameResponse,
    CreateRoomRequest,
    CustomWordItem,
    DictionaryEntryItem,
    EvaluateLevelsRequest,
    FavouriteWordItem,
    GuestAuthRequest,
    GuestAuthResponse,
    JoinRoomResponse,
    LeaderboardItem,
    MoveResponse,
    PlayerStatsResponse,
    RoomStateResponse,
    SubmitAnswerRequest,
    WrongWordItem,
)
from .scoring import LLMScorer
from .security import AuthContext, auth_context_from_header, decode_token
from .ws_manager import ConnectionManager

load_dotenv()
configure_logging()
logger = logging.getLogger("duoeng.app")

# ---------------------------------------------------------------------------
# Request body size limit (bytes).  1 MB should be more than enough for
# any legitimate payload this API accepts.
# ---------------------------------------------------------------------------
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024  # 1 MB

app = FastAPI(
    title="DuoEng API",
    version="2.0.0",
    # Disable auto-generated docs in production to reduce attack surface.
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)
api_router = APIRouter(prefix="/api")

scorer = LLMScorer()
service = GameService(scorer=scorer)
ws_manager = ConnectionManager()
http_rate_limiter = SlidingWindowLimiter()


@app.on_event("startup")
async def startup_event() -> None:
    check_db_connection()
    if settings.is_sqlite:
        # Local dev fallback keeps sqlite bootstrap simple.
        init_db()

    # Create AI players on startup (Feature 8)
    try:
        from .ai_player import ensure_ai_players_exist
        ensure_ai_players_exist()
    except Exception:
        logger.warning("Could not create AI players at startup")

    # Run seeding in a background thread so the server can bind the port
    # immediately.  Render (and similar PaaS) will kill the process if no
    # open port is detected within ~5 minutes.
    def _background_seed():
        try:
            seeded = seed_sample_words_if_empty()
            logger.info(
                "Background seed complete",
                extra={"event": "seed_done", "seeded_words": seeded},
            )
        except Exception:
            logger.exception("Background seeding failed")

    seed_thread = threading.Thread(target=_background_seed, daemon=True)
    seed_thread.start()

    clear_expired_llm_cache()
    logger.info(
        "Backend startup complete — server ready (seeding continues in background)",
        extra={
            "event": "startup",
            "db_backend": "sqlite" if settings.is_sqlite else "postgres",
            "schema_bootstrap": "create_all" if settings.is_sqlite else "alembic",
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Security headers middleware – adds defence-in-depth headers to every
# HTTP response.  WebSocket upgrade responses are excluded automatically
# because Starlette/ASGI doesn't call ASGI middleware for them.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


# ---------------------------------------------------------------------------
# Global exception handler – ensures internal details never leak to clients.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    # HTTPExceptions are already handled by FastAPI; this catches unexpected errors.
    logger.error(
        "Unhandled exception",
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "reason": f"{exc.__class__.__name__}: {exc}",
        },
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def _client_ip_from_request(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _client_ip_from_ws(websocket: WebSocket) -> str:
    if websocket.client and websocket.client.host:
        return websocket.client.host
    return "unknown"


@app.middleware("http")
async def request_guard_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method
    ip = _client_ip_from_request(request)

    # ── Request body size guard ──
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})

    if not http_rate_limiter.allow(f"http:{ip}", settings.rate_limit_requests_per_min, 60):
        logger.warning(
            "HTTP rate limit exceeded",
            extra={"event": "rate_limit_hit", "ip": ip, "path": path},
        )
        response = JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        REQUESTS_TOTAL.labels(method=method, path=path, status="429").inc()
        return response

    with get_db() as conn:
        if service._is_banned(conn, "ip", ip):
            response = JSONResponse(status_code=403, content={"detail": "IP temporarily banned"})
            REQUESTS_TOTAL.labels(method=method, path=path, status="403").inc()
            return response

    response = await call_next(request)
    REQUESTS_TOTAL.labels(method=method, path=path, status=str(response.status_code)).inc()
    return response


def _auth_user_from_header(authorization: Optional[str] = Header(default=None)) -> AuthContext:
    auth = auth_context_from_header(authorization)
    service.ensure_player_exists(auth.player_id)
    return auth


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"message": "DuoEng API"}


@api_router.post("/auth/guest", response_model=GuestAuthResponse)
async def auth_guest(payload: GuestAuthRequest) -> GuestAuthResponse:
    result = service.create_guest(payload.nickname)
    return GuestAuthResponse(**result)


@api_router.post("/rooms", response_model=JoinRoomResponse)
async def create_room(
    payload: CreateRoomRequest,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> JoinRoomResponse:
    result = service.create_room(
        player_id=auth.player_id,
        mode=payload.mode,
        target_score=payload.target_score,
        ip=_client_ip_from_request(request),
        word_level=payload.word_level,
        use_favourites=payload.use_favourites,
        use_custom_words=payload.use_custom_words,
        ai_difficulty=payload.ai_difficulty,
        word_ids=payload.word_ids,
    )
    return JoinRoomResponse(**result)


@api_router.post("/rooms/{room_code}/join", response_model=JoinRoomResponse)
async def join_room(
    room_code: str,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> JoinRoomResponse:
    result = service.join_room(room_code=room_code, player_id=auth.player_id, ip=_client_ip_from_request(request))
    return JoinRoomResponse(**result)


@api_router.get("/rooms/{room_code}/state", response_model=RoomStateResponse)
async def room_state(
    room_code: str,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> RoomStateResponse:
    state = service.room_state_for_player(room_code, auth.player_id, ip=_client_ip_from_request(request))
    return RoomStateResponse(**state)


@api_router.post("/rooms/{room_code}/submit", response_model=MoveResponse)
async def submit_move(
    room_code: str,
    payload: SubmitAnswerRequest,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> MoveResponse:
    result = await service.submit_answer(
        room_code=room_code,
        player_id=auth.player_id,
        answer=payload.answer,
        ip=_client_ip_from_request(request),
        channel="http",
    )
    return MoveResponse(**result)


@api_router.post("/rooms/{room_code}/turn", response_model=MoveResponse)
async def submit_move_legacy(
    room_code: str,
    payload: SubmitAnswerRequest,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> MoveResponse:
    result = await service.submit_answer(
        room_code=room_code,
        player_id=auth.player_id,
        answer=payload.answer,
        ip=_client_ip_from_request(request),
        channel="http",
    )
    return MoveResponse(**result)


@api_router.post("/rooms/{room_code}/leave")
async def leave_room(
    room_code: str,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    result = service.leave_room(room_code=room_code, player_id=auth.player_id)

    # Notify remaining player via WebSocket
    async def _state_provider(target_room_code: str, target_player_id: str) -> dict:
        return service.room_state_for_player(target_room_code, target_player_id, ip="http")

    await ws_manager.broadcast(room_code.upper(), {
        "type": "opponent_left",
        "message": "Your opponent left. You win!",
    })
    try:
        await ws_manager.broadcast_room_state(room_code.upper(), _state_provider)
    except Exception:
        pass

    return result


@api_router.get("/leaderboard", response_model=list[LeaderboardItem])
async def leaderboard(
    limit: int = Query(default=20, ge=1, le=100),
    period: str = Query(default="all", pattern="^(today|week|all)$"),
) -> list[LeaderboardItem]:
    rows = service.leaderboard(limit, period=period)
    return [LeaderboardItem(**row) for row in rows]


@api_router.get("/players/{player_id}/stats", response_model=PlayerStatsResponse)
async def player_stats(
    player_id: str,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> PlayerStatsResponse:
    stats = service.player_stats(player_id)
    return PlayerStatsResponse(**stats)


@api_router.patch("/players/me/nickname", response_model=ChangeNicknameResponse)
async def change_nickname(
    payload: ChangeNicknameRequest,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> ChangeNicknameResponse:
    result = service.change_nickname(auth.player_id, payload.nickname)
    return ChangeNicknameResponse(**result)


# ── Favourite words ──

@api_router.get("/players/me/favourites", response_model=list[FavouriteWordItem])
async def list_favourites(
    auth: AuthContext = Depends(_auth_user_from_header),
) -> list[FavouriteWordItem]:
    rows = service.list_favourites(auth.player_id)
    return [FavouriteWordItem(**row) for row in rows]


@api_router.post("/players/me/favourites", response_model=FavouriteWordItem, status_code=201)
async def add_favourite(
    payload: AddFavouriteRequest,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> FavouriteWordItem:
    result = service.add_favourite(auth.player_id, payload.word_id)
    return FavouriteWordItem(**result)


@api_router.delete("/players/me/favourites/{word_id}")
async def remove_favourite(
    word_id: str,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    return service.remove_favourite(auth.player_id, word_id)


@api_router.get("/players/{player_id}/history")
async def player_history(
    player_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    return service.player_match_history(player_id, page=page, per_page=per_page)


@api_router.get("/dictionary/search", response_model=list[DictionaryEntryItem])
async def dictionary_search(
    q: str = Query(..., min_length=1, max_length=80),
    level: Optional[str] = Query(default=None, pattern="^(A1|A2|B1|B2|C1|C2)$"),
    auth: AuthContext = Depends(_auth_user_from_header),
) -> list[DictionaryEntryItem]:
    _ = auth
    normalized = " ".join(q.strip().lower().split())
    if not normalized:
        return []

    # Build optional level filter via LEFT JOIN to the words table.
    level_join = ""
    level_clause = ""
    level_select = ", w.level AS level"
    params: dict[str, object] = {"prefix": f"{normalized}%", "exact": normalized}

    # Always join words to get the CEFR level for each entry.
    level_join = "LEFT JOIN words w ON LOWER(d.en_word) = LOWER(w.en)"

    if level:
        level_clause = "AND w.level = :level"
        params["level"] = level.upper()

    with get_db() as session:
        rows = session.execute(
            text(
                f"""
                SELECT d.ua_word, d.en_word, d.part_of_speech, d.source {level_select}
                FROM dictionary_entries d
                {level_join}
                WHERE (d.en_word LIKE :prefix OR d.ua_word LIKE :prefix) {level_clause}
                ORDER BY
                    CASE WHEN d.en_word = :exact OR d.ua_word = :exact THEN 0 ELSE 1 END,
                    CASE WHEN d.en_word LIKE :prefix THEN 0 ELSE 1 END,
                    d.en_word ASC,
                    d.ua_word ASC
                LIMIT 20
                """
            ),
            params,
        ).mappings().all()

    return [DictionaryEntryItem(**dict(row)) for row in rows]


# ── Custom words (Feature 9) ──

@api_router.post("/players/me/words", response_model=CustomWordItem, status_code=201)
async def add_custom_word(
    payload: AddCustomWordRequest,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> CustomWordItem:
    result = service.add_custom_word(auth.player_id, payload.ua_word, payload.en_word)
    return CustomWordItem(**result)


@api_router.get("/players/me/words", response_model=list[CustomWordItem])
async def list_custom_words(
    auth: AuthContext = Depends(_auth_user_from_header),
) -> list[CustomWordItem]:
    rows = service.list_custom_words(auth.player_id)
    return [CustomWordItem(**row) for row in rows]


@api_router.delete("/players/me/words/{word_id}")
async def delete_custom_word(
    word_id: str,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    return service.delete_custom_word(auth.player_id, word_id)


# ── Wrong words (Feature 10) ──

@api_router.get("/players/me/wrong-words", response_model=list[WrongWordItem])
async def wrong_words(
    auth: AuthContext = Depends(_auth_user_from_header),
    limit: int = Query(default=50, le=100),
) -> list[WrongWordItem]:
    rows = service.get_wrong_words(auth.player_id, limit=limit)
    return [WrongWordItem(**row) for row in rows]


# ── Second chance submit (Feature 7) ──

@api_router.post("/rooms/{room_code}/second-chance")
async def submit_second_chance(
    room_code: str,
    payload: SubmitAnswerRequest,
    request: Request,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    result = await service.submit_second_chance(
        room_code=room_code,
        player_id=auth.player_id,
        answer=payload.answer,
        ip=_client_ip_from_request(request),
    )
    return result


# ── Admin: Re-evaluate CEFR levels (Feature 6) ──

@api_router.post("/admin/evaluate-levels")
async def admin_evaluate_levels(
    payload: EvaluateLevelsRequest,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict:
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from .services.admin_service import evaluate_word_levels
    result = await evaluate_word_levels(batch_size=payload.batch_size, max_words=payload.max_words)
    return result


@api_router.post("/admin/batch-seed")
async def admin_batch_seed(
    payload: AdminSeedRequest,
    auth: AuthContext = Depends(_auth_user_from_header),
) -> dict[str, object]:
    return service.admin_batch_seed(actor=auth, seed_words=payload.seed_words, reset_stats=payload.reset_stats)


@api_router.get("/health")
async def api_healthcheck() -> dict[str, str]:
    with get_db() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Public stats endpoint – no auth, cached for 60 seconds
# ---------------------------------------------------------------------------
_stats_cache: dict[str, object] = {"data": None, "expires_at": 0.0}


@api_router.get("/stats")
async def public_stats() -> dict:
    """Return aggregate platform stats. No auth required. Cached for 60s."""
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires_at"]:
        return _stats_cache["data"]

    with get_db() as session:
        total_words = session.execute(text("SELECT COUNT(*) FROM words")).scalar() or 0

        # Also check dictionary_entries if available
        try:
            total_dict_entries = session.execute(text("SELECT COUNT(*) FROM dictionary_entries")).scalar() or 0
        except Exception:
            total_dict_entries = 0

        total_players = session.execute(text("SELECT COUNT(*) FROM players")).scalar() or 0
        total_games = session.execute(text("SELECT COUNT(*) FROM matches")).scalar() or 0

        level_rows = session.execute(
            text("SELECT level, COUNT(*) as cnt FROM words GROUP BY level ORDER BY level")
        ).mappings().all()

    words_by_level = {row["level"]: row["cnt"] for row in level_rows}
    result = {
        "total_words": max(total_words, total_dict_entries),
        "total_players": total_players,
        "total_games_played": total_games,
        "words_by_level": words_by_level,
    }

    _stats_cache["data"] = result
    _stats_cache["expires_at"] = now + 60.0

    return result


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    with get_db() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics")
async def metrics(auth: AuthContext = Depends(_auth_user_from_header)) -> Response:
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    if not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


api_router.include_router(ai_router)
api_router.include_router(oauth_router)
app.include_router(word_levels_router)
app.include_router(api_router)


def _extract_ws_token(websocket: WebSocket) -> str:
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token

    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()

    subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    if subprotocols:
        items = [item.strip() for item in subprotocols.split(",") if item.strip()]
        if len(items) >= 2 and items[0].lower() == "jwt":
            return items[1]

    raise HTTPException(status_code=401, detail="WebSocket token is missing")


@app.websocket("/ws/rooms/{room_code}")
async def websocket_room(websocket: WebSocket, room_code: str) -> None:
    ip = _client_ip_from_ws(websocket)

    try:
        token = _extract_ws_token(websocket)
        auth = decode_token(token)
        service.ensure_player_exists(auth.player_id)
        # Validate membership before accepting active stream.
        initial_state = service.room_state_for_player(room_code, auth.player_id, ip=ip)
    except HTTPException:
        logger.warning(
            "WS auth rejected",
            extra={"event": "ws_auth_rejected", "ip": ip, "room_code": room_code},
        )
        await websocket.close(code=4401)
        return

    requested_subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    accepted_subprotocol = None
    if requested_subprotocols:
        items = [item.strip().lower() for item in requested_subprotocols.split(",") if item.strip()]
        if "jwt" in items:
            accepted_subprotocol = "jwt"

    await ws_manager.connect(room_code.upper(), auth.player_id, websocket, subprotocol=accepted_subprotocol)

    # Per-connection burst rate limiter (10 messages / second sliding window).
    _ws_burst_limiter = SlidingWindowLimiter()
    _ws_burst_key = f"ws_burst:{room_code.upper()}:{auth.player_id}"

    try:
        await websocket.send_json({"type": "connected", "room_code": room_code.upper()})
        await websocket.send_json({"type": "game_state", "data": initial_state})

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=45)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
                continue

            # ── Re-validate JWT on every incoming message ──
            try:
                auth = decode_token(token)
            except HTTPException:
                logger.warning(
                    "WS token invalid mid-session",
                    extra={"event": "ws_token_expired", "ip": ip, "player_id": auth.player_id},
                )
                await websocket.send_json({"type": "error", "detail": "Token expired"})
                await websocket.close(code=4401)
                return

            # ── Per-connection burst guard (10 msg/sec) ──
            if not _ws_burst_limiter.allow(_ws_burst_key, max_events=10, period_seconds=1):
                logger.warning(
                    "WS burst rate limit triggered",
                    extra={"event": "ws_burst_limit", "ip": ip, "player_id": auth.player_id},
                )
                await websocket.send_json({"type": "error", "detail": "Message rate limit exceeded"})
                await websocket.close(code=4429)
                return

            msg_type = (message.get("type") or "").lower()
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
                continue

            if msg_type == "pause":
                room_code_upper = room_code.upper()
                if ws_manager.is_paused(room_code_upper):
                    await websocket.send_json({"type": "error", "detail": "Game is already paused"})
                else:
                    ws_manager.pause_room(room_code_upper, auth.nickname)
                    await ws_manager.broadcast(room_code_upper, {
                        "type": "game_paused",
                        "paused_by": auth.nickname,
                    })
                continue

            if msg_type == "resume":
                room_code_upper = room_code.upper()
                if not ws_manager.is_paused(room_code_upper):
                    await websocket.send_json({"type": "error", "detail": "Game is not paused"})
                else:
                    ws_manager.resume_room(room_code_upper)
                    await ws_manager.broadcast(room_code_upper, {
                        "type": "game_resumed",
                    })
                continue

            if msg_type == "leave":
                room_code_upper = room_code.upper()
                try:
                    service.leave_room(room_code=room_code, player_id=auth.player_id)
                except HTTPException:
                    pass
                await ws_manager.broadcast(room_code_upper, {
                    "type": "opponent_left",
                    "message": f"{auth.nickname} left the game. You win!",
                })
                await websocket.send_json({"type": "left", "detail": "You left the room"})
                return

            if msg_type not in {"submit", "move", "second_chance"}:
                await websocket.send_json({"type": "error", "detail": "Unsupported message type"})
                continue

            # Block submissions while paused
            if ws_manager.is_paused(room_code.upper()):
                await websocket.send_json({"type": "error", "detail": "Game is paused"})
                continue

            if not service.ws_message_allowed(room_code, auth.player_id):
                logger.warning(
                    "WS rate limit hit",
                    extra={"event": "ws_rate_limit", "ip": ip, "player_id": auth.player_id},
                )
                await websocket.send_json({"type": "error", "detail": "WebSocket rate limit exceeded"})
                continue

            answer = str(message.get("answer", "")).strip()[:256]
            if not answer:
                await websocket.send_json({"type": "error", "detail": "Answer is required"})
                continue

            try:
                if msg_type == "second_chance":
                    result = await service.submit_second_chance(
                        room_code=room_code,
                        player_id=auth.player_id,
                        answer=answer,
                        ip=ip,
                    )
                else:
                    result = await service.submit_answer(
                        room_code=room_code,
                        player_id=auth.player_id,
                        answer=answer,
                        ip=ip,
                        channel="ws",
                    )
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "detail": exc.detail, "status": exc.status_code})
                continue

            async def _state_provider(target_room_code: str, target_player_id: str) -> dict:
                return service.room_state_for_player(target_room_code, target_player_id, ip="ws")

            await ws_manager.broadcast_room_state(room_code.upper(), _state_provider)
            await ws_manager.broadcast(
                room_code.upper(),
                {"type": "leaderboard", "data": service.leaderboard(10, period="all")},
            )
            await ws_manager.send_to_player(room_code.upper(), auth.player_id, {"type": "submit_ack", "data": result})

            # Broadcast second_chance info if applicable
            if result.get("second_chance") and result.get("second_chance_player_id"):
                await ws_manager.broadcast(room_code.upper(), {
                    "type": "second_chance",
                    "player_id": result["second_chance_player_id"],
                    "word": result.get("correct_answer", ""),
                    "time_limit": 10,
                })

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(room_code.upper(), auth.player_id, websocket)

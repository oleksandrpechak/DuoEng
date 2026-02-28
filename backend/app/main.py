from __future__ import annotations

import asyncio
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
from .routers.word_levels import router as word_levels_router
from .schemas import (
    AdminSeedRequest,
    CreateRoomRequest,
    DictionaryEntryItem,
    GuestAuthRequest,
    GuestAuthResponse,
    JoinRoomResponse,
    LeaderboardItem,
    MoveResponse,
    PlayerStatsResponse,
    RoomStateResponse,
    SubmitAnswerRequest,
)
from .scoring import LLMScorer
from .security import AuthContext, auth_context_from_header, decode_token
from .ws_manager import ConnectionManager

load_dotenv()
configure_logging()
logger = logging.getLogger("duoeng.app")

app = FastAPI(title="DuoEng API", version="2.0.0")
api_router = APIRouter(prefix="/api")

scorer = LLMScorer()
service = GameService(scorer=scorer)
ws_manager = ConnectionManager()
http_rate_limiter = SlidingWindowLimiter()


@app.on_event("startup")
async def startup_event() -> None:
    check_db_connection()
    init_db()
    seeded = seed_sample_words_if_empty()
    clear_expired_llm_cache()
    logger.info(
        "Backend startup complete",
        extra={
            "event": "startup",
            "seeded_words": seeded,
            "db_backend": "sqlite" if settings.is_sqlite else "postgres",
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    if not http_rate_limiter.allow(f"http:{ip}", settings.rate_limit_requests_per_min, 60):
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


@api_router.get("/leaderboard", response_model=list[LeaderboardItem])
async def leaderboard(limit: int = Query(default=20, ge=1, le=100)) -> list[LeaderboardItem]:
    rows = service.leaderboard(limit)
    return [LeaderboardItem(**row) for row in rows]


@api_router.get("/players/{player_id}/stats", response_model=PlayerStatsResponse)
async def player_stats(player_id: str) -> PlayerStatsResponse:
    stats = service.player_stats(player_id)
    return PlayerStatsResponse(**stats)


@app.get("/dictionary/search", response_model=list[DictionaryEntryItem])
@api_router.get("/dictionary/search", response_model=list[DictionaryEntryItem])
async def dictionary_search(
    q: str = Query(..., min_length=1, max_length=80),
    auth: AuthContext = Depends(_auth_user_from_header),
) -> list[DictionaryEntryItem]:
    _ = auth
    normalized = " ".join(q.strip().lower().split())
    if not normalized:
        return []

    with get_db() as session:
        rows = session.execute(
            text(
                """
                SELECT ua_word, en_word, part_of_speech, source
                FROM dictionary_entries
                WHERE en_word LIKE :prefix OR ua_word LIKE :prefix
                ORDER BY
                    CASE WHEN en_word = :exact OR ua_word = :exact THEN 0 ELSE 1 END,
                    CASE WHEN en_word LIKE :prefix THEN 0 ELSE 1 END,
                    en_word ASC,
                    ua_word ASC
                LIMIT 20
                """
            ),
            {"prefix": f"{normalized}%", "exact": normalized},
        ).mappings().all()

    return [DictionaryEntryItem(**row) for row in rows]


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


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    with get_db() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics")
async def metrics() -> Response:
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


api_router.include_router(ai_router)
app.include_router(ai_router)
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
        await websocket.close(code=4401)
        return

    requested_subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    accepted_subprotocol = None
    if requested_subprotocols:
        items = [item.strip().lower() for item in requested_subprotocols.split(",") if item.strip()]
        if "jwt" in items:
            accepted_subprotocol = "jwt"

    await ws_manager.connect(room_code.upper(), auth.player_id, websocket, subprotocol=accepted_subprotocol)

    try:
        await websocket.send_json({"type": "connected", "room_code": room_code.upper()})
        await websocket.send_json({"type": "game_state", "data": initial_state})

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=45)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
                continue

            msg_type = (message.get("type") or "").lower()
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
                continue

            if msg_type not in {"submit", "move"}:
                await websocket.send_json({"type": "error", "detail": "Unsupported message type"})
                continue

            if not service.ws_message_allowed(room_code, auth.player_id):
                await websocket.send_json({"type": "error", "detail": "WebSocket rate limit exceeded"})
                continue

            answer = str(message.get("answer", "")).strip()
            if not answer:
                await websocket.send_json({"type": "error", "detail": "Answer is required"})
                continue

            try:
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
                {"type": "leaderboard", "data": service.leaderboard(10)},
            )
            await ws_manager.send_to_player(room_code.upper(), auth.player_id, {"type": "submit_ack", "data": result})

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(room_code.upper(), auth.player_id, websocket)

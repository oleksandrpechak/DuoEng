from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from fastapi import WebSocket

from .metrics import ACTIVE_ROOMS

logger = logging.getLogger("duoeng.ws")


StateProvider = Callable[[str, str], Awaitable[dict]]


class ConnectionManager:
    def __init__(self) -> None:
        self._active_rooms: dict[str, dict[str, set[WebSocket]]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        room_code: str,
        player_id: str,
        websocket: WebSocket,
        subprotocol: str | None = None,
    ) -> None:
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            room = self._active_rooms.setdefault(room_code, {})
            room.setdefault(player_id, set()).add(websocket)
            ACTIVE_ROOMS.set(len(self._active_rooms))

    async def disconnect(self, room_code: str, player_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._active_rooms.get(room_code)
            if not room:
                return

            sockets = room.get(player_id)
            if sockets and websocket in sockets:
                sockets.remove(websocket)
            if not sockets:
                room.pop(player_id, None)
            if not room:
                self._active_rooms.pop(room_code, None)
            ACTIVE_ROOMS.set(len(self._active_rooms))

    async def send_to_player(self, room_code: str, player_id: str, payload: dict) -> None:
        room = self._active_rooms.get(room_code, {})
        sockets = list(room.get(player_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                logger.exception("WebSocket send failure", extra={"event": "ws_send_failed"})

    async def broadcast(self, room_code: str, payload: dict) -> None:
        room = self._active_rooms.get(room_code, {})
        for sockets in list(room.values()):
            for ws in list(sockets):
                try:
                    await ws.send_json(payload)
                except Exception:
                    logger.exception("WebSocket broadcast failure", extra={"event": "ws_broadcast_failed"})

    async def broadcast_room_state(self, room_code: str, state_provider: StateProvider) -> None:
        room = self._active_rooms.get(room_code, {})
        for player_id, sockets in list(room.items()):
            try:
                state = await state_provider(room_code, player_id)
            except Exception:
                logger.exception(
                    "Failed to build room state for websocket player",
                    extra={"event": "ws_state_build_failed", "room_code": room_code, "player_id": player_id},
                )
                continue

            payload = {"type": "game_state", "data": state}
            for ws in list(sockets):
                try:
                    await ws.send_json(payload)
                except Exception:
                    logger.exception("WebSocket state push failure", extra={"event": "ws_state_push_failed"})

    def room_connection_count(self, room_code: str) -> int:
        room = self._active_rooms.get(room_code, {})
        return sum(len(sockets) for sockets in room.values())

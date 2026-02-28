from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Header, HTTPException
import jwt

from .config import settings


@dataclass(frozen=True)
class AuthContext:
    player_id: str
    nickname: str
    is_admin: bool


def create_access_token(player_id: str, nickname: str, is_admin: bool = False) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": player_id,
        "nickname": nickname,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_exp_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> AuthContext:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    player_id = payload.get("sub")
    nickname = payload.get("nickname")
    is_admin = bool(payload.get("is_admin", False))
    if not player_id or not nickname:
        raise HTTPException(status_code=401, detail="Malformed token payload")

    return AuthContext(player_id=player_id, nickname=nickname, is_admin=is_admin)


def get_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    return parts[1].strip()


def auth_context_from_header(authorization: Optional[str] = Header(default=None)) -> AuthContext:
    token = get_bearer_token(authorization)
    return decode_token(token)

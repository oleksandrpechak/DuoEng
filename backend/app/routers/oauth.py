from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import httpx
from sqlalchemy import text

from ..config import settings
from ..db import get_db
from ..security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("duoeng.oauth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _get_google_client_id() -> str:
    val = settings.google_client_id
    if not val:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    return val


def _get_google_client_secret() -> str:
    val = settings.google_client_secret
    if not val:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    return val


def _get_redirect_uri() -> str:
    val = settings.google_redirect_uri
    if not val:
        # Auto-derive from frontend URL
        backend_url = settings.frontend_url.replace("-frontend", "-backend")
        return f"{backend_url}/api/auth/google/callback"
    return val


@router.get("/google")
async def google_login(request: Request):
    """Redirect user to Google OAuth consent screen."""
    client_id = _get_google_client_id()
    redirect_uri = _get_redirect_uri()
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    }
    url = f"{GOOGLE_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=url)


@router.get("/google/callback")
async def google_callback(code: str = None, error: str = None):
    """Handle Google OAuth callback."""
    if error:
        logger.warning("Google OAuth denied", extra={"event": "google_oauth_denied", "error": error})
        return RedirectResponse(url=f"{settings.frontend_url}?auth_error=denied")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()
    redirect_uri = _get_redirect_uri()

    # Exchange code for token
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        logger.error(
            "Google token exchange failed",
            extra={"event": "google_token_error", "status": token_resp.status_code},
        )
        return RedirectResponse(url=f"{settings.frontend_url}?auth_error=token_exchange_failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(url=f"{settings.frontend_url}?auth_error=no_access_token")

    # Fetch user info
    async with httpx.AsyncClient(timeout=10.0) as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_resp.status_code != 200:
        return RedirectResponse(url=f"{settings.frontend_url}?auth_error=userinfo_failed")

    userinfo = userinfo_resp.json()
    google_id = userinfo.get("id")
    email = userinfo.get("email")
    name = userinfo.get("name") or email.split("@")[0] if email else "User"

    if not google_id:
        return RedirectResponse(url=f"{settings.frontend_url}?auth_error=no_google_id")

    # Find or create player
    with get_db() as session:
        # Check by google_id first
        row = session.execute(
            text("SELECT id, nickname FROM players WHERE google_id = :google_id"),
            {"google_id": google_id},
        ).mappings().first()

        if row:
            player_id = row["id"]
            nickname = row["nickname"]
        else:
            # Check by email
            if email:
                row = session.execute(
                    text("SELECT id, nickname FROM players WHERE email = :email"),
                    {"email": email},
                ).mappings().first()

            if row:
                player_id = row["id"]
                nickname = row["nickname"]
                # Update google_id
                session.execute(
                    text("UPDATE players SET google_id = :google_id WHERE id = :id"),
                    {"google_id": google_id, "id": player_id},
                )
            else:
                # Create new player
                player_id = str(uuid.uuid4())
                # Make nickname unique and short (max 19 chars)
                base_name = (name[:16].strip() or "Player")[:16]
                nickname = base_name
                attempt = 0
                while True:
                    existing = session.execute(
                        text("SELECT id FROM players WHERE nickname = :nickname"),
                        {"nickname": nickname},
                    ).mappings().first()
                    if not existing:
                        break
                    attempt += 1
                    nickname = f"{base_name}{secrets.randbelow(9000) + 1000}"[:19]
                    if attempt > 20:
                        nickname = f"User{secrets.randbelow(90000) + 10000}"[:19]
                        break

                from datetime import datetime, timezone

                session.execute(
                    text(
                        """
                        INSERT INTO players (
                            id, nickname, elo, wins, losses,
                            total_games, total_response_time, total_moves,
                            created_at, google_id, email
                        ) VALUES (
                            :id, :nickname, :elo, 0, 0, 0, 0.0, 0,
                            :created_at, :google_id, :email
                        )
                        """
                    ),
                    {
                        "id": player_id,
                        "nickname": nickname,
                        "elo": settings.default_elo,
                        "created_at": datetime.now(timezone.utc),
                        "google_id": google_id,
                        "email": email,
                    },
                )

    is_admin = nickname.lower() in settings.admin_nicknames
    jwt_token = create_access_token(player_id=player_id, nickname=nickname, is_admin=is_admin)

    # Redirect to frontend with token in URL fragment
    redirect_url = (
        f"{settings.frontend_url}"
        f"?access_token={jwt_token}"
        f"&user_id={player_id}"
        f"&nickname={nickname}"
    )

    logger.info(
        "Google OAuth success",
        extra={"event": "google_auth_success", "player_id": player_id, "nickname": nickname},
    )
    return RedirectResponse(url=redirect_url)

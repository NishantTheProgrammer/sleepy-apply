from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response, status
import httpx
from app.core.config import get_settings
from app.db.client import get_db
from app.models.user import User
from app.security.jwt import create_access_token, create_refresh_token, decode_token
import structlog

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()

DISCORD_API = "https://discord.com/api/v10"


@router.get("/discord/login")
async def discord_login():
    """Redirect URL for Discord OAuth — return the authorization URL."""
    settings = get_settings()
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify email",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": f"https://discord.com/api/oauth2/authorize?{query}"}


@router.post("/discord/callback")
async def discord_callback(request: Request, response: Response):
    """Exchange Discord OAuth code for JWT tokens."""
    settings = get_settings()
    body = await request.json()
    code = body.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    # Exchange code for Discord access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Discord token exchange failed")

        discord_token = token_resp.json()["access_token"]

        # Fetch Discord user info
        user_resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {discord_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Discord user")

        discord_user = user_resp.json()

    db = get_db()
    now = datetime.now(timezone.utc)

    # Upsert user
    await db.users.update_one(
        {"discord_id": discord_user["id"]},
        {
            "$set": {
                "discord_username": discord_user.get("username", ""),
                "discord_avatar": discord_user.get("avatar"),
                "email": discord_user.get("email"),
                "last_login": now,
                "updated_at": now,
                "is_active": True,
            },
            "$setOnInsert": {
                "discord_id": discord_user["id"],
                "role": "user",
                "created_at": now,
            },
        },
        upsert=True,
    )

    user_doc = await db.users.find_one({"discord_id": discord_user["id"]})
    user_id = str(user_doc["_id"])

    # Issue JWT tokens
    token_data = {"sub": user_id, "discord_id": discord_user["id"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Set httpOnly cookies
    is_prod = settings.is_production
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=is_prod, samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        httponly=True, secure=is_prod, samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )

    return {
        "user": {
            "id": user_id,
            "discord_id": discord_user["id"],
            "discord_username": discord_user.get("username"),
            "discord_avatar": discord_user.get("avatar"),
            "role": user_doc.get("role", "user"),
        }
    }


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Issue a new access token from a valid refresh token."""
    settings = get_settings()
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    new_access = create_access_token({"sub": payload["sub"], "discord_id": payload.get("discord_id")})
    response.set_cookie(
        "access_token", new_access,
        httponly=True, secure=settings.is_production, samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"ok": True}


@router.get("/me")
async def get_me(request: Request):
    """Return the current authenticated user."""
    from app.security.jwt import get_current_user_id
    user_id = get_current_user_id(request)
    db = get_db()
    from bson import ObjectId
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["_id"] = str(user["_id"])
    # Never expose sensitive fields
    user.pop("__v", None)
    return user

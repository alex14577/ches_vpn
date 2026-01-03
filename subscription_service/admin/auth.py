import hmac
import os
from fastapi import Request, Response, HTTPException

COOKIE_NAME = "admin_session"

def _env(name: str) -> str:
    return os.getenv(name, "")

def verify_password(username: str, password: str) -> bool:
    # constant-time compare
    return hmac.compare_digest(username, _env("ADMIN_USERNAME")) and hmac.compare_digest(password, _env("ADMIN_PASSWORD"))

def set_session_cookie(resp: Response) -> None:
    resp.set_cookie(
        key=COOKIE_NAME,
        value="ok",  # minimal: presence = authenticated
        httponly=True,
        secure=(_env("ADMIN_COOKIE_SECURE").lower() in ("1", "true", "yes")),
        samesite="lax",
        path="/admin",
        max_age=7 * 24 * 3600,
    )

def clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME, path="/admin")

def require_admin(request: Request) -> None:
    if not request.cookies.get(COOKIE_NAME):
        raise HTTPException(status_code=401, detail="Not authenticated")
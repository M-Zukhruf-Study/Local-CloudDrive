"""
Single-admin authentication. There is no signup and no user table —
the one valid identity is whatever ADMIN_USERNAME/ADMIN_PASSWORD are set to
in the environment. A successful login just hands back a JWT, which the
frontend stores and sends back as a Bearer token (and we also accept it
as a query param for plain <a href> downloads / <img> style GET requests
where you can't attach a header).
"""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def verify_credentials(username: str, password: str) -> bool:
    return username == settings.admin_username and password == settings.admin_password


def create_access_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": settings.admin_username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    token_qs: str | None = Query(default=None, alias="token"),
):
    """
    Accepts the JWT either as a normal Authorization: Bearer header (used by
    the JS app for all fetch() calls) or as a ?token= query string (used for
    direct download links where the browser navigates the tab itself).
    """
    raw = token or token_qs
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(raw)

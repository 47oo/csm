"""Authentication endpoints (Contract §4).

Routes stay thin: validation via schemas, business rules via
``app.services.auth``, identity via ``get_current_operator``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.auth import Operator, get_current_operator
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import SESSION_COOKIE_NAME
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, build_user_out
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_options(settings: Settings) -> dict:
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
        "secure": settings.is_production,
    }


def _set_session_cookie(
    response: Response, token: str, expires_at: datetime, settings: Settings
) -> None:
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    response.set_cookie(
        value=token,
        expires=expires_at,
        max_age=max(0, max_age),
        **_cookie_options(settings),
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.set_cookie(value="", max_age=0, **_cookie_options(settings))


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Authenticate, create a session and set the session cookie."""
    user, token, expires_at = auth_service.login(db, payload.username, payload.password)
    _set_session_cookie(response, token, expires_at, get_settings())
    return LoginResponse(user=build_user_out(user), expires_at=expires_at)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    operator: Operator = Depends(get_current_operator),
    db: Session = Depends(get_db),
) -> Response:
    """Delete the current session and clear the cookie. Requires a session."""
    del operator  # authentication is the only use here
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        auth_service.logout(db, token)
    response = Response(status_code=204)
    _clear_session_cookie(response, get_settings())
    return response


@router.get("/me", response_model=MeResponse)
def me(
    operator: Operator = Depends(get_current_operator),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Return the current operator and its permission set."""
    user = db.get(User, operator.user_id)
    assert user is not None  # guaranteed by get_current_operator
    return MeResponse(user=build_user_out(user))
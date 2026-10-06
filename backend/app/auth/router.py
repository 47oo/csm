"""认证与会话路由：POST /auth/login、/auth/logout、GET /auth/me、POST /auth/change-password。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..db import get_db
from ..errors import problem
from ..models import User, UserCredential, UserSession
from ..schemas import ChangePasswordRequest, CurrentUserOut, LoginRequest
from ..security.password import (
    PASSWORD_POLICY_MESSAGE,
    hash_password,
    password_policy_ok,
    verify_password,
)
from ..security.principal import Principal, get_current_user
from ..security.tokens import generate_token, sha256_hex

router = APIRouter(prefix="/auth", tags=["auth"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
    )


@router.post("/login", response_model=CurrentUserOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.username_key == payload.username))
    if user is None:
        raise problem(401, "INVALID_CREDENTIALS", "用户名或口令错误")

    credential = db.get(UserCredential, user.id)
    if credential is None or not verify_password(credential.password_hash, payload.password):
        raise problem(401, "INVALID_CREDENTIALS", "用户名或口令错误")

    if user.status != "enabled":
        raise problem(403, "ACCOUNT_DISABLED", "账号已禁用")

    now = _utcnow()
    token = generate_token()
    db.add(
        UserSession(
            token_hash=sha256_hex(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    db.commit()

    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    token = request.cookies.get(settings.cookie_name)
    if token:
        session = db.scalar(
            select(UserSession).where(UserSession.token_hash == sha256_hex(token))
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = _utcnow()
            db.commit()

    response = Response(status_code=204)
    response.delete_cookie(settings.cookie_name, path="/")
    return response


@router.get("/me", response_model=CurrentUserOut)
def me(user: Principal = Depends(get_current_user)) -> CurrentUserOut:
    return CurrentUserOut(
        id=user.user_id,
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
        status=user.status,  # type: ignore[arg-type]
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(get_current_user),
) -> Response:
    credential = db.get(UserCredential, user.user_id)
    if credential is None or not verify_password(
        credential.password_hash, payload.current_password
    ):
        raise problem(400, "INVALID_CURRENT_PASSWORD", "当前口令错误")

    if not password_policy_ok(payload.new_password):
        raise problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[
                {
                    "field": "new_password",
                    "code": "PASSWORD_POLICY",
                    "message": PASSWORD_POLICY_MESSAGE,
                }
            ],
        )

    now = _utcnow()
    credential.password_hash = hash_password(payload.new_password)
    credential.password_updated_at = now

    current_token = request.cookies.get(settings.cookie_name)
    current_hash = sha256_hex(current_token) if current_token else None
    revoked = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.user_id,
            UserSession.revoked_at.is_(None),
            UserSession.token_hash != current_hash,
        )
        .values(revoked_at=now)
    ).rowcount

    db_user = db.get(User, user.user_id)
    assert db_user is not None
    db_user.must_change_password = False
    db_user.version = db_user.version + 1
    db_user.updated_at = now

    audit.write(
        db,
        user,
        "user.change_password",
        "user",
        str(user.user_id),
        db_user.username,
        {"must_change_password": False, "others_sessions_revoked": revoked},
    )
    db.commit()

    response = Response(status_code=204)
    return response
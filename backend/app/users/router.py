"""用户与角色管理路由（仅 admin；Contract §3）。"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..errors import problem
from ..models import ReservedUsername, User, UserCredential, UserSession
from ..schemas import (
    PagedUsers,
    ResetPasswordRequest,
    UserCreateRequest,
    UserDetailOut,
    UserListItemOut,
    UserUpdateRequest,
)
from ..security.password import (
    PASSWORD_POLICY_MESSAGE,
    hash_password,
    password_policy_ok,
)
from ..security.principal import Principal, require_roles

router = APIRouter(prefix="/users", tags=["users"])

_USERNAME_RE = re.compile(r"^[A-Za-z0-9]{1,128}$")
_USERNAME_MESSAGE = "用户名仅允许字母与数字，长度 1–128"

admin_required = require_roles("admin")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_username(username: str) -> None:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[
                {
                    "field": "username",
                    "code": "USERNAME_INVALID",
                    "message": _USERNAME_MESSAGE,
                }
            ],
        )


def _validate_password(password: str, field: str = "password") -> None:
    if not password_policy_ok(password):
        raise problem(
            422,
            "VALIDATION_ERROR",
            "字段校验失败",
            errors=[
                {
                    "field": field,
                    "code": "PASSWORD_POLICY",
                    "message": PASSWORD_POLICY_MESSAGE,
                }
            ],
        )


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise problem(404, "USER_NOT_FOUND", "用户不存在")
    return user


def _enabled_admin_count(db: Session, *, excluding_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role == "admin",
            User.status == "enabled",
            User.id != excluding_id,
        )
    )


def _is_last_enabled_admin(db: Session, user: User) -> bool:
    if user.role != "admin" or user.status != "enabled":
        return False
    return _enabled_admin_count(db, excluding_id=user.id) == 0


@router.get("", response_model=PagedUsers)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    role: str | None = Query(None),
    status: str | None = Query(None),
    sort: str = Query("username"),
    db: Session = Depends(get_db),
    _admin: Principal = Depends(admin_required),
) -> PagedUsers:
    sort_map = {
        "username": User.username_key.asc(),
        "-username": User.username_key.desc(),
        "created_at": User.created_at.asc(),
        "-created_at": User.created_at.desc(),
    }
    if sort not in sort_map:
        raise problem(400, "INVALID_REQUEST", "非法的排序参数")
    if role is not None and role not in {"viewer", "maintainer", "admin"}:
        raise problem(400, "INVALID_REQUEST", "非法的角色过滤值")
    if status is not None and status not in {"enabled", "disabled"}:
        raise problem(400, "INVALID_REQUEST", "非法的状态过滤值")

    conditions = []
    if q is not None and q.strip() != "":
        escaped = (
            q.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        conditions.append(User.username.ilike(f"%{escaped}%", escape="\\"))
    if role is not None:
        conditions.append(User.role == role)
    if status is not None:
        conditions.append(User.status == status)

    total = db.scalar(
        select(func.count()).select_from(User).where(*conditions)
    )
    items = (
        db.scalars(
            select(User)
            .where(*conditions)
            .order_by(sort_map[sort])
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    return PagedUsers(
        items=[UserListItemOut.model_validate(u) for u in items],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserDetailOut, status_code=201)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> User:
    _validate_username(payload.username)
    _validate_password(payload.password)

    now = _utcnow()
    try:
        db.add(ReservedUsername(username_key=payload.username))
        db.flush()
    except IntegrityError:
        db.rollback()
        raise problem(409, "USERNAME_TAKEN", "用户名已被占用")

    user = User(
        username=payload.username,
        role=payload.role,
        status="enabled",
        must_change_password=True,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise problem(409, "USERNAME_TAKEN", "用户名已被占用")

    db.add(
        UserCredential(
            user_id=user.id,
            password_hash=hash_password(payload.password),
            password_updated_at=now,
        )
    )
    audit.write(
        db,
        admin,
        "user.create",
        "user",
        str(user.id),
        user.username,
        {"role": user.role, "status": user.status, "must_change_password": True},
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserDetailOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: Principal = Depends(admin_required),
) -> User:
    return _get_user_or_404(db, user_id)


@router.patch("/{user_id}", response_model=UserDetailOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> User:
    extra_fields = set((payload.model_extra or {}).keys())
    if extra_fields or payload.role is None:
        raise problem(400, "INVALID_REQUEST", "仅允许修改角色字段")

    user = _get_user_or_404(db, user_id)
    old_role = user.role
    now = _utcnow()

    result = db.execute(
        update(User)
        .where(User.id == user_id, User.version == payload.version)
        .values(role=payload.role, version=User.version + 1, updated_at=now)
    )
    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "用户已被其他人修改，请刷新后重试")

    audit.write(
        db,
        admin,
        "user.update_role",
        "user",
        str(user_id),
        user.username,
        {"role": {"from": old_role, "to": payload.role}},
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    version: int = Query(..., description="乐观锁版本"),
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> None:
    user = _get_user_or_404(db, user_id)
    if _is_last_enabled_admin(db, user):
        raise problem(
            409, "LAST_ADMIN", "禁止删除最后一个启用中的平台管理员"
        )

    username = user.username
    audit.write(
        db,
        admin,
        "user.delete",
        "user",
        str(user_id),
        username,
        {"role": user.role, "status": user.status},
    )
    result = db.execute(
        delete(User).where(User.id == user_id, User.version == version)
    )
    if result.rowcount == 0:
        db.rollback()
        raise problem(409, "VERSION_CONFLICT", "用户已被其他人修改，请刷新后重试")
    db.commit()


@router.post("/{user_id}/disable", status_code=204)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> None:
    user = _get_user_or_404(db, user_id)
    if user.status == "disabled":
        return
    if _is_last_enabled_admin(db, user):
        raise problem(
            409, "LAST_ADMIN", "禁止禁用最后一个启用中的平台管理员"
        )

    now = _utcnow()
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(status="disabled", version=User.version + 1, updated_at=now)
    )
    # PROPOSED：禁用后撤销该用户现有会话。
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    audit.write(
        db,
        admin,
        "user.disable",
        "user",
        str(user_id),
        user.username,
        {"status": {"from": "enabled", "to": "disabled"}},
    )
    db.commit()


@router.post("/{user_id}/enable", status_code=204)
def enable_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> None:
    user = _get_user_or_404(db, user_id)
    if user.status == "enabled":
        return

    now = _utcnow()
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(status="enabled", version=User.version + 1, updated_at=now)
    )
    audit.write(
        db,
        admin,
        "user.enable",
        "user",
        str(user_id),
        user.username,
        {"status": {"from": "disabled", "to": "enabled"}},
    )
    db.commit()


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(admin_required),
) -> None:
    user = _get_user_or_404(db, user_id)
    _validate_password(payload.new_password, field="new_password")

    now = _utcnow()
    credential = db.get(UserCredential, user_id)
    if credential is None:
        credential = UserCredential(user_id=user_id)
        db.add(credential)
    credential.password_hash = hash_password(payload.new_password)
    credential.password_updated_at = now

    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(must_change_password=True, version=User.version + 1, updated_at=now)
    )
    revoked = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
    audit.write(
        db,
        admin,
        "user.reset_password",
        "user",
        str(user_id),
        user.username,
        {"must_change_password": True, "sessions_revoked": revoked},
    )
    db.commit()
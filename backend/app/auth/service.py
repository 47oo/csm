"""认证业务行为（F013）。

- ``authenticate``：统一失败语义（R-AUTH-006）——用户名不存在 / 口令错误 /
  账号停用一律抛**同一个** ``UnauthenticatedError``，且不建立会话。
- ``establish_session``：惰性清理过期会话 → 生成令牌 → 写入会话行（8 小时绝对
  有效期，不滑动续期）。
- ``logout``：物理删除当前会话行。
- ``create_initial_admin``：初始管理员（幂等），口令经 ``policy.validate_password``
  校验（R-AUTH-004 的单一实现）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import passwords, policy, tokens
from app.auth.repository import AuthRepository
from app.common.errors import UnauthenticatedError
from app.models.user import User

#: 会话绝对有效期（契约 §7 记录的实现决策）：8 小时；不滑动续期。
SESSION_TTL = timedelta(hours=8)


class InitialAdminResult:
    """``create_initial_admin`` 的结果：账号 id + 本次是否新建。"""

    def __init__(self, user_id: int, username: str, created: bool) -> None:
        self.user_id = user_id
        self.username = username
        self.created = created


def authenticate(session: Session, username: str, password: str) -> User:
    """校验凭据并返回账号；失败抛统一的 ``UnauthenticatedError``。"""
    repository = AuthRepository(session)
    user = repository.get_user_by_username(username)
    if user is None:
        # 用户不存在时仍执行一次等价耗时的 Argon2 校验（防计时侧信道）。
        passwords.verify_dummy(password)
        raise UnauthenticatedError()
    if not passwords.verify_password(user.password_hash, password):
        raise UnauthenticatedError()
    if not user.active:
        # 账号停用与凭据错误返回完全相同的响应（R-AUTH-006 / AC-07）。
        raise UnauthenticatedError()
    return user


def establish_session(session: Session, user: User) -> str:
    """建立服务端会话，返回**原始**令牌（只在此处出现，永不落库 / 落日志）。"""
    repository = AuthRepository(session)
    repository.delete_expired_sessions()
    token = tokens.generate_session_token()
    repository.create_session(
        user_id=user.id,
        token_hash=tokens.hash_session_token(token),
        expires_at=datetime.now(UTC) + SESSION_TTL,
    )
    return token


def logout(session: Session, raw_token: str | None) -> None:
    """物理删除该令牌对应的会话行；令牌缺失时为 no-op。"""
    if not raw_token:
        return
    AuthRepository(session).delete_session_by_token_hash(tokens.hash_session_token(raw_token))


def create_initial_admin(session: Session, username: str, password: str) -> InitialAdminResult:
    """建立初始管理员账号（幂等）。

    - 先校验口令（R-AUTH-004）：不足 8 位直接抛 ``ValidationError``，不产生账号。
    - 用户名已存在 → 不修改任何内容，返回 ``created=False``。
    """
    policy.validate_password(password)
    repository = AuthRepository(session)
    existing = repository.get_user_by_username(username)
    if existing is not None:
        return InitialAdminResult(existing.id, existing.username, created=False)
    user = User(
        username=username,
        password_hash=passwords.hash_password(password),
        active=True,
    )
    session.add(user)
    session.flush()
    session.refresh(user)
    return InitialAdminResult(user.id, user.username, created=True)

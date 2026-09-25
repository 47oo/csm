"""pytest 共享夹具：真实 PostgreSQL、Schema 初始化、测试隔离与客户端。"""

from __future__ import annotations

import os

# 必须在导入应用模块前设置，保证引擎连接到测试库。
os.environ.setdefault(
    "CSM_DATABASE_URL",
    "postgresql+psycopg://csm:csm@db:5432/csm_test",
)
os.environ.setdefault("CSM_SESSION_TTL_SECONDS", "43200")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.bootstrap import create_schema  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ReservedUsername, User, UserCredential  # noqa: E402
from app.security.password import hash_password  # noqa: E402

_ALL_TABLES = "users, user_credentials, sessions, reserved_usernames, audit_log"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    create_schema(engine)
    # 幂等：重复调用不报错。
    create_schema(engine)
    yield


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def add_user():
    def _add(
        username: str,
        password: str,
        role: str,
        *,
        status: str = "enabled",
        must_change: bool = False,
    ) -> int:
        with SessionLocal() as db:
            db.add(ReservedUsername(username_key=username))
            user = User(
                username=username,
                role=role,
                status=status,
                must_change_password=must_change,
            )
            db.add(user)
            db.flush()
            db.add(
                UserCredential(
                    user_id=user.id,
                    password_hash=hash_password(password),
                )
            )
            db.commit()
            return user.id

    return _add


@pytest.fixture
def login_as():
    def _login(client: TestClient, username: str, password: str):
        return client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

    return _login
"""F013 初始管理员 CLI 测试（T-11、T-13，AC-11 / AC-14）。

CLI 是唯一的账号建立路径；口令从 stdin 读取，经 ``app.auth.policy`` 校验。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _client, login
from tests.database.helpers import REPO_ROOT, upgrade_to_head


def _run_cli(dsn: str, username: str, password_line: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CSM_DATABASE_URL"] = dsn
    env["CSM_ENVIRONMENT"] = "test"
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")
    return subprocess.run(
        [sys.executable, "-m", "app.auth.cli", "create-initial-admin", "--username", username],
        cwd=REPO_ROOT,
        env=env,
        input=password_line + "\n",
        capture_output=True,
        text=True,
    )


def _user_count(dsn: str, username: str) -> int:
    engine = create_engine(dsn)
    try:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT count(*) FROM users WHERE username = :u"), {"u": username}
            ).scalar()
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- #
# T-11 / AC-11：按文档化步骤建立初始账号 → 可登录；重复执行幂等
# --------------------------------------------------------------------------- #
def test_t11_cli_creates_loginable_admin_and_is_idempotent(database_url):
    engine = upgrade_to_head(database_url)
    engine.dispose()

    first = _run_cli(database_url, "ops-admin", "ops-admin-password")
    assert first.returncode == 0, first.stderr
    assert _user_count(database_url, "ops-admin") == 1

    with _client("dev", database_url) as client:
        response = login(client, "ops-admin", "ops-admin-password")
        assert response.json()["username"] == "ops-admin"
        assert client.get("/api/clusters").status_code == 200

    second = _run_cli(database_url, "ops-admin", "ops-admin-password")
    assert second.returncode == 0, second.stderr
    assert "已存在" in second.stdout
    assert _user_count(database_url, "ops-admin") == 1


# --------------------------------------------------------------------------- #
# T-13 / AC-14 / R-AUTH-004：7 位拒绝、8 位接受
# --------------------------------------------------------------------------- #
def test_t13_seven_char_password_rejected(database_url):
    engine = upgrade_to_head(database_url)
    engine.dispose()

    result = _run_cli(database_url, "short-pw-user", "abcdefg")  # 7 位
    assert result.returncode != 0
    assert _user_count(database_url, "short-pw-user") == 0
    assert "abcdefg" not in result.stdout
    assert "abcdefg" not in result.stderr


def test_t13_eight_lowercase_char_password_accepted(database_url):
    engine = upgrade_to_head(database_url)
    engine.dispose()

    result = _run_cli(database_url, "lower-pw-user", "abcdefgh")  # 8 位纯小写
    assert result.returncode == 0, result.stderr
    assert _user_count(database_url, "lower-pw-user") == 1

    with _client("dev", database_url) as client:
        response = login(client, "lower-pw-user", "abcdefgh")
        assert response.status_code == 200
        assert client.get("/api/clusters").status_code == 200


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_t13_sub_eight_passwords_never_create_account(database_url, password):
    engine = upgrade_to_head(database_url)
    engine.dispose()

    result = _run_cli(database_url, "pw-user", password)
    assert result.returncode != 0
    assert _user_count(database_url, "pw-user") == 0

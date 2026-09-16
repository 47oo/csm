"""F013 结构 / 静态 guard（G-D、G-E、G-F、T-08 静态部分、T-09）。

把「单一口令策略实现」「无明文进入日志」「无状态改变型 GET」「无注册入口」
「无 RBAC」变成会失败的测试，而非口头约定。
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.main import create_app
from tests.conftest import OFFLINE_DSN
from tests.deletion_guard_helpers import scan_deleted_at_writes

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "backend" / "app"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def _python_sources() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


# --------------------------------------------------------------------------- #
# G-D：口令策略单一实现 + Argon2 单一导入点
# --------------------------------------------------------------------------- #
def test_g_d_password_length_check_lives_only_in_policy():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if "len(password" in path.read_text(encoding="utf-8") and path.name != "policy.py"
    ]
    assert offenders == [], f"R-AUTH-004 长度校验只允许在 policy.py：{offenders}"


def test_g_d_policy_min_length_is_eight():
    from app.auth import policy

    assert policy.MIN_PASSWORD_LENGTH == 8


def test_g_d_argon2_imported_only_in_passwords_module():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if "argon2" in path.read_text(encoding="utf-8") and path.name != "passwords.py"
    ]
    assert offenders == [], f"Argon2 只允许在 auth/passwords.py 使用：{offenders}"


def test_g_d_login_schema_has_no_length_constraint():
    from app.auth.schemas import LoginRequest

    for model in (LoginRequest,):
        field = model.model_fields["password"]
        for meta in field.metadata:
            assert getattr(meta, "min_length", None) in (None, False)
            assert getattr(meta, "max_length", None) in (None, False)


# --------------------------------------------------------------------------- #
# G-E：认证代码不写 deleted_at、不把 password 传给日志
#
# F014 演进：原断言扫描**全部** ``app/**``（写入数 = 0）已由 G-3 的 allow-list
# 取代（``tests/test_deletion_guards.py``）。此处收窄回本意——认证代码自身
# 不得引入软删语义（AC-13）。
# --------------------------------------------------------------------------- #
def test_g_e_no_deleted_at_assignment_in_auth_sources():
    assert scan_deleted_at_writes(APP_DIR / "auth") == {}, "认证代码不得写入 deleted_at"


def test_g_e_no_password_in_logging_calls():
    log_markers = ("logger.", "logging.", "log.")
    offenders = []
    for path in _python_sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(marker in line for marker in log_markers) and "password" in line.lower():
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert offenders == [], f"日志调用中不得出现 password：{offenders}"


def test_g_e_auth_module_declares_no_deleted_at():
    for path in sorted((APP_DIR / "auth").rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        # 允许注释 / docstring 提及；禁止列定义与赋值路径。
        assert ".deleted_at" not in content, f"{path.name} 不得写入 deleted_at"
        assert "deleted_at:" not in content, f"{path.name} 不得定义 deleted_at 列"


def test_g_e_no_foundation_face():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if "_foundation" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --------------------------------------------------------------------------- #
# G-F：无状态改变型 GET（路由表中 GET 集合恰为只读端点）
# --------------------------------------------------------------------------- #
EXPECTED_GET_ROUTES = {
    "/api/health",
    "/api/clusters",
    "/api/clusters/by-name/{cluster_name}",
    "/api/clusters/{cluster_id}",
    # F009：Cluster 视角只读名称别名（仅新增，不得删除既有成员）。
    "/api/clusters/by-name/{cluster_name}/bare-metals",
    "/api/bare-metals",
    "/api/bare-metals/{bare_metal_id}",
    # F006：VirtualMachine 只读 GET 路由（仅新增，不得删除既有成员）。
    "/api/virtual-machines",
    "/api/virtual-machines/{virtual_machine_id}",
    # F004：NetworkInterface 只读 GET 路由（仅新增，不得删除既有成员）。
    "/api/network-interfaces",
    "/api/network-interfaces/{network_interface_id}",
    "/api/auth/session",
}


def test_g_f_only_read_only_get_routes():
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    spec = app.openapi()

    get_routes = {path for path, operations in spec["paths"].items() if "get" in operations}
    assert get_routes == EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# T-08 静态部分：无注册路由 / 注册页面
# --------------------------------------------------------------------------- #
def test_t08_no_registration_route_in_backend():
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    spec = app.openapi()
    offenders = [
        path
        for path in spec["paths"]
        if any(token in path.lower() for token in ("register", "signup", "sign-up", "/users"))
    ]
    assert offenders == [], f"不存在注册端点：{offenders}"


def test_t08_no_registration_page_in_frontend():
    if not FRONTEND_SRC.exists():
        return
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in FRONTEND_SRC.rglob("*")
        if path.is_file() and ("register" in path.name.lower() or "signup" in path.name.lower())
    ]
    assert offenders == [], f"不存在注册页面：{offenders}"


# --------------------------------------------------------------------------- #
# T-09：无 RBAC 表 / 列 / 端点
# --------------------------------------------------------------------------- #
def test_t09_no_rbac_tables_or_columns():
    import app.models  # noqa: F401
    from app.db.base import Base

    forbidden = ("role", "permission", "rbac", "grant", "acl")
    for table in Base.metadata.tables.values():
        assert not any(token in table.name.lower() for token in forbidden), table.name
        for column in table.columns:
            assert not any(token in column.name.lower() for token in forbidden), (
                f"{table.name}.{column.name}"
            )


def test_t09_no_rbac_routes():
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    spec = app.openapi()
    offenders = [
        path
        for path in spec["paths"]
        if any(token in path.lower() for token in ("role", "permission", "rbac"))
    ]
    assert offenders == []


def test_t09_no_forbidden_error_class_or_403_raise_path():
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        if "ForbiddenError" in text or "FORBIDDEN" in text:
            if path.name != "error_handlers.py":
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"V1 无 403 触发路径：{offenders}"

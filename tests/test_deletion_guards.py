"""F014 静态 guard（G-3 / T-11 静态部分 / T-12）与 A15 / G-E 的演进。

把「唯一软删写入路径」「无恢复路径」「无越界能力」「认证表无软删」变成会失败的
测试，而非口头约定（AC-03 / AC-08 / AC-11 / AC-13）。
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.main import create_app
from tests.conftest import OFFLINE_DSN
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
    scan_undelete_writes,
)


def _openapi_paths() -> dict:
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()["paths"]


# --------------------------------------------------------------------------- #
# G-3 / AC-08：写入 deleted_at 的文件集合恰好为 {app/deletion/service.py}
# --------------------------------------------------------------------------- #
def test_g3_deleted_at_writers_are_allowlisted():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, (
        f"写入 deleted_at 的文件必须恰好为 {ALLOWED_DELETED_AT_WRITER}，实际：{writers}"
    )


# --------------------------------------------------------------------------- #
# G-3 / AC-03 / R-DELETE-003：不存在任何 undelete（deleted_at = None）路径
# --------------------------------------------------------------------------- #
def test_g3_no_undelete_path():
    assert scan_undelete_writes() == []


def test_g3_deletion_service_exists_and_is_used_by_cluster_delete():
    """正向断言：唯一写入路径存在，且资源删除委托它，避免「空 allow-list」退化。"""
    from app.deletion import soft_delete as exported_soft_delete
    from app.deletion.service import soft_delete as service_soft_delete

    assert exported_soft_delete is service_soft_delete

    import app.clusters.service as cluster_service

    source = Path(cluster_service.__file__).read_text(encoding="utf-8")
    assert "soft_delete(" in source, "Cluster 删除必须委托统一软删服务"


# --------------------------------------------------------------------------- #
# T-11 静态部分 / AC-13：认证代码不引入软删语义
# --------------------------------------------------------------------------- #
def test_t11_auth_module_writes_no_deleted_at():
    from app.models.session import Session as SessionModel
    from app.models.user import User

    assert scan_deleted_at_writes(APP_DIR / "auth") == {}
    assert not hasattr(User, "deleted_at")
    assert not hasattr(SessionModel, "deleted_at")


# --------------------------------------------------------------------------- #
# T-12 / AC-11：无越界能力（恢复 / 回收站 / 批量删除 / 查看已删）
# --------------------------------------------------------------------------- #
def test_t12_no_out_of_scope_routes():
    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "deleted")
    offenders = [
        path
        for path in _openapi_paths()
        if any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 回收站 / 批量删除端点：{offenders}"


def test_t12_list_endpoint_has_no_deleted_query_param():
    list_op = _openapi_paths()["/api/clusters"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)

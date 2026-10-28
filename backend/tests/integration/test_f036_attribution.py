"""F036 DR-F036-01 —— `RowError.field` 归因修正（真实 PostgreSQL 强制争用）。

对应 `docs/features/F036/architecture.md` §3 DR-F036-01 与 §12 定稿裁定
（TD-I-3 / TD-I-4 / TD-I-8），以及 `docs/api/F023.md` §11「归因澄清」bullet：

* 宿主在**写入阶段**因并发软删 / 不再可选导致资源侧锁定失败
  （`interface.prepare_interface` → `_lock_resource`）→ `field="hostname"`，
  `reason` 为服务层**自由文本**（TD-I-3：只断言子串，不逐字符固定），
  `related_row=null`；整批 422 `IMPORT_VALIDATION_FAILED` 且零写入残留。
* 软删发生在写入的预校验之前 ⇒ 按 §8.1「不存在」新建（对照用例）。
* 多行组场景行号只断言 `row ∈ 组物理行号集合`（TD-I-4）。

V2 的强制性交错由 `pg_blocking_pids` 轮询证实（不靠固定 sleep 假定顺序）：
会话 B 先 `BEGIN` + `SELECT … FOR UPDATE` 持 `resources` 行锁，线程 A 的
`write_import` 在 `_acquire_locks` 阻塞 → B 在同一事务内经服务层软删并提交 →
A 解阻塞后在 `_lock_resource` 观察到 `deleted_at` 并失败。

Database 环境前提（§12 / `implementation.md` §3）：两个会话都显式
`SET TRANSACTION ISOLATION LEVEL READ COMMITTED`，并在断言与失败信息里记录
实测隔离级别；REPEATABLE READ 下同一竞争返回 40001 → 500，判 BLOCKED。
"""

from __future__ import annotations

import ast
import csv
import io
import threading
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import ImportValidationFailed, ValidationError
from app.services import resource as resource_service
from app.services import resource_interface_ip_import as unified
from integration.test_ip_addresses import (  # noqa: F401  (reused fixtures/helpers)
    _cluster,
    _network,
    _operator,
    role_client_factory,
)

VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
WRITE = "/api/v1/imports/resource-interfaces-ips"

BM = "BARE_METAL"
VM = "VIRTUAL_MACHINE"

# Frozen 26-column order (Contract §6 / D03).
HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "host",
    "vcpu",
    "memory_mb",
    "disk_gb",
    "hypervisor",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "gpu_model",
    "gpu_count",
    "name",
    "interface_type",
    "mac_address",
    "speed_mbps",
    "mtu",
    "enabled",
    "network",
    "ip",
]

# TD-I-3：服务层自由文本，只断言该子串。
LOCK_REASON_SUBSTRING = "does not exist or is not selectable"

POLL_DEADLINE_SECONDS = 20.0
POLL_INTERVAL_SECONDS = 0.01
READ_COMMITTED = "read committed"


# --- helpers ----------------------------------------------------------------


def _row(**values) -> list[str]:
    return ["" if values.get(h) is None else str(values.get(h)) for h in HEADERS]


def _csv_bytes(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _post(client, path, rows):
    return client.post(
        path,
        files={"file": ("import.csv", _csv_bytes(rows), "application/octet-stream")},
        data={"format": "csv"},
    )


def _validate(client, rows):
    return _post(client, VALIDATE, rows)


def _api_resource(client, cluster_code, hostname, resource_type=BM, **overrides):
    body = {"cluster": cluster_code, "hostname": hostname, "resource_type": resource_type}
    body.update(overrides)
    resp = client.post("/api/v1/resources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["resource"]


def _find_error(details: dict, field: str, row: int | None = None) -> dict | None:
    for error in details["errors"]:
        if error["field"] == field and (row is None or error["row"] == row):
            return error
    return None


def _counts(session) -> dict[str, int]:
    """写入窗口前后必须不变的计数（零写入守卫）。"""
    return {
        "resources": int(
            session.execute(text("SELECT count(*) FROM resources")).scalar_one()
        ),
        "interfaces": int(
            session.execute(text("SELECT count(*) FROM interfaces")).scalar_one()
        ),
        "ip_addresses": int(
            session.execute(text("SELECT count(*) FROM ip_addresses")).scalar_one()
        ),
        "audit_create": int(
            session.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'CREATE'")
            ).scalar_one()
        ),
    }


def _write_service(session, operator, rows) -> tuple[int, int, int, int]:
    return unified.write_import(
        session, operator, _csv_bytes(rows), "csv", Settings(_env_file=None)
    )


class _Writer(threading.Thread):
    """线程 A：独立会话（READ COMMITTED）执行 ``write_import``。

    先声明 backend pid 再进入 ``write_import``，使主线程可用
    ``pg_blocking_pids`` 证实锁等待交错；结果（返回值或异常）存在 ``outcome``。
    """

    def __init__(self, session_factory, operator, rows) -> None:
        super().__init__(daemon=True)
        self._factory = session_factory
        self._operator = operator
        self._rows = rows
        self.pid: int | None = None
        self.pid_ready = threading.Event()
        self.isolation: str | None = None
        self.outcome: object = None

    def run(self) -> None:
        session = self._factory()
        try:
            session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            self.isolation = session.execute(
                text("SHOW transaction_isolation")
            ).scalar_one()
            self.pid = int(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            self.pid_ready.set()
            self.outcome = _write_service(session, self._operator, self._rows)
        except BaseException as exc:  # noqa: BLE001 - 作为结果收集
            self.outcome = exc
        finally:
            session.close()


def _wait_until_blocked(engine, blocked_pid: int, blocking_pid: int) -> bool:
    """轮询 ``pg_blocking_pids`` 直至 ``blocked_pid`` 被 ``blocking_pid`` 阻塞。

    返回 ``False`` 表示在期限内未观察到争用 —— 调用方按 **BLOCKED** 处理
    （不靠固定 ``sleep`` 假定交错已经发生）。
    """
    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    with engine.connect() as conn:
        while time.monotonic() < deadline:
            pids = conn.execute(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": blocked_pid}
            ).scalar_one()
            if blocking_pid in {int(pid) for pid in pids}:
                return True
            time.sleep(POLL_INTERVAL_SECONDS)
    return False


# =============================================================================
# V2.5 (TD-I-8) — `_app_error_field` 词表：四项映射且无新增键
# =============================================================================


def _mapped_literal() -> dict[str, str]:
    """从源码读回 `_app_error_field` 内的 `mapped` 字典字面量（守卫新增键）。"""
    source = Path(unified.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_app_error_field":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    return {
                        ast.literal_eval(key): ast.literal_eval(value)
                        for key, value in zip(sub.keys, sub.values)
                    }
    raise AssertionError("_app_error_field: no `mapped` dict literal found")


def test_v2_5_app_error_field_vocabulary_is_exactly_four_entries():
    """V2.5 (TD-I-8): 词表恰为四项，`resource → hostname` 已登记且无新增键。"""
    assert _mapped_literal() == {
        "address": "ip",
        "virtual_machine.host_resource_id": "host",
        "interface": "name",
        "resource": "hostname",
    }

    def _field(field: str) -> str:
        return unified._app_error_field(
            ValidationError(details={"fields": [{"field": field, "message": "m"}]})
        )

    # 归因修正点：`interface._lock_resource` 的 `_field_error("resource", …)`
    assert _field("resource") == "hostname"
    # 既有三项映射不受影响（防回归）
    assert _field("address") == "ip"
    assert _field("virtual_machine.host_resource_id") == "host"
    assert _field("interface") == "name"
    # 未命中词表仍走模板列名，未知点路径的兜底口径不变
    assert _field("hardware.model") == "model"
    assert _field("") == "resource_type"


def _resource_field_error_producers() -> list[tuple[str, int]]:
    """用 AST 枚举 `_field_error("resource", …)` 的**代码**产生点（排除注释/文档串）。"""
    backend_dir = Path(unified.__file__).resolve().parents[2]
    producers: list[tuple[str, int]] = []
    for path in sorted((backend_dir / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_field_error"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "resource"
            ):
                producers.append((path.relative_to(backend_dir).as_posix(), node.lineno))
    return sorted(producers)


def test_v2_5_resource_field_error_producers_are_registered():
    """TD-I-8 守卫：`_field_error("resource", …)` 产生点仅既定 4 处。

    `interface.py::_lock_resource` 是本导入路径上唯一可达的产生点（驱动
    `field="hostname"`）；`service.py::resolve_resource` 的三处服务于 POST
    body 解析，导入路径不经过。若新增产生点必须同时复核映射语义。
    """
    assert _resource_field_error_producers() == [
        ("app/services/interface.py", 156),
        ("app/services/service.py", 111),
        ("app/services/service.py", 116),
        ("app/services/service.py", 124),
    ], producers


# =============================================================================
# V2 (TD-I-3 / TD-I-4) — 真实 PG：写入阶段宿主被并发软删 ⇒ field="hostname"
# =============================================================================


def _race_soft_delete_during_write(
    *,
    auth_session_factory,
    committed_engine,
    operator,
    client,
    cluster_code: str,
    hostname: str,
    net_name: str,
    cidr: str,
    rows_builder,
):
    """执行「B 持行锁 → A 阻塞 → B 软删提交 → A 失败」并返回观测结果。"""
    cluster = _cluster(client, code=cluster_code)
    _network(client, cluster["id"], name=net_name, cidr=cidr)
    host = _api_resource(client, cluster["code"], hostname)
    rows = rows_builder(cluster["code"], hostname, net_name)
    assert _validate(client, rows).json()["error_count"] == 0

    with auth_session_factory() as session:
        before = _counts(session)

    session_b = auth_session_factory()
    writer = None
    try:
        session_b.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        isolation_b = session_b.execute(text("SHOW transaction_isolation")).scalar_one()
        assert isolation_b == READ_COMMITTED, (
            f"BLOCKED: session B isolation {isolation_b!r} != {READ_COMMITTED!r}"
        )
        session_b.execute(
            text("SELECT id FROM resources WHERE id = :id FOR UPDATE"),
            {"id": host["id"]},
        ).first()
        pid_b = int(session_b.execute(text("SELECT pg_backend_pid()")).scalar_one())

        writer = _Writer(auth_session_factory, operator, rows)
        writer.start()
        assert writer.pid_ready.wait(timeout=POLL_DEADLINE_SECONDS), "writer never started"
        assert writer.isolation == READ_COMMITTED, (
            f"BLOCKED: writer isolation {writer.isolation!r} != {READ_COMMITTED!r}"
        )
        interleaved = _wait_until_blocked(committed_engine, writer.pid, pid_b)
        assert interleaved, (
            f"BLOCKED: writer pid {writer.pid} was never blocked by pid {pid_b} within "
            f"{POLL_DEADLINE_SECONDS}s (isolation B/A = {isolation_b}/{writer.isolation}); "
            "the concurrent-soft-delete interleaving was not reached"
        )
        # B：同一事务内经服务层软删；`delete_resource` 内部 commit ⇒ 行锁随提交释放
        resource_service.delete_resource(
            session_b,
            operator,
            uuid.UUID(host["id"]),
            expected_version=host["version"],
        )
        writer.join(timeout=60)
    finally:
        session_b.close()

    assert writer is not None and not writer.is_alive(), "writer session hung"
    with auth_session_factory() as session:
        after = _counts(session)
        deleted_at = session.execute(
            text("SELECT deleted_at FROM resources WHERE id = :id"), {"id": host["id"]}
        ).scalar_one()
        child_interfaces = int(
            session.execute(
                text("SELECT count(*) FROM interfaces WHERE resource_id = :id"),
                {"id": host["id"]},
            ).scalar_one()
        )
    # 竞争前提成立：宿主确实在 B 侧被软删
    assert deleted_at is not None, "host was not soft-deleted by session B"
    # 零写入残留（interfaces / ip_addresses / resources 计数不变、窗口内无 CREATE Audit）
    assert after == before, f"batch left residue: {before} -> {after}"
    assert child_interfaces == 0, "interfaces were written against a deleted host"
    return writer, before, after, isolation_b


def test_dr_f036_01_concurrent_soft_delete_attributed_to_hostname(
    role_client_factory, auth_session_factory, committed_engine
):
    """V2 / DR-F036-01: 写入阶段宿主被并发软删 ⇒ 422 `field="hostname"`、零写入。"""
    editor, user, _ = role_client_factory("EDITOR")

    def _rows(cluster_code, hostname, net_name):
        return [
            _row(
                cluster=cluster_code,
                hostname=hostname,
                resource_type=BM,
                name="eth0",
                network=net_name,
                ip="10.36.0.11",
            )
        ]

    writer, before, after, isolation = _race_soft_delete_during_write(
        auth_session_factory=auth_session_factory,
        committed_engine=committed_engine,
        operator=_operator(user),
        client=editor,
        cluster_code="F036A",
        hostname="f036-h1",
        net_name="f036-net",
        cidr="10.36.0.0/24",
        rows_builder=_rows,
    )

    failed = writer.outcome
    assert isinstance(failed, ImportValidationFailed), (isolation, failed)
    # 422 `IMPORT_VALIDATION_FAILED`（未新增错误码，§12 定稿）
    assert ImportValidationFailed.status_code == 422
    assert failed.status_code == 422
    assert failed.code == "IMPORT_VALIDATION_FAILED"
    details = failed.details
    assert details["error_count"] >= 1, details
    error = _find_error(details, "hostname", 2)
    assert error is not None, details["errors"]
    # TD-I-3：`reason` 为自由文本，只断子串
    assert LOCK_REASON_SUBSTRING in error["reason"], error
    assert error["related_row"] is None, error
    # 整批失败：无任何新对象写入
    assert after["interfaces"] == before["interfaces"]
    assert after["ip_addresses"] == before["ip_addresses"]
    assert after["resources"] == before["resources"]


def test_dr_f036_01_multi_row_group_row_within_group_rows(
    role_client_factory, auth_session_factory, committed_engine
):
    """TD-I-4: 多行组场景行号只断言属于该组物理行号集合（2、3）。"""
    editor, user, _ = role_client_factory("EDITOR")

    def _rows(cluster_code, hostname, net_name):
        return [
            _row(
                cluster=cluster_code,
                hostname=hostname,
                resource_type=BM,
                name="eth0",
                network=net_name,
                ip="10.37.0.11",
            ),
            _row(
                cluster=cluster_code,
                hostname=hostname,
                resource_type=BM,
                name="eth1",
                network=net_name,
                ip="10.37.0.12",
            ),
        ]

    writer, before, after, isolation = _race_soft_delete_during_write(
        auth_session_factory=auth_session_factory,
        committed_engine=committed_engine,
        operator=_operator(user),
        client=editor,
        cluster_code="F036B",
        hostname="f036-h2",
        net_name="f036-net2",
        cidr="10.37.0.0/24",
        rows_builder=_rows,
    )

    failed = writer.outcome
    assert isinstance(failed, ImportValidationFailed), (isolation, failed)
    details = failed.details
    assert details["error_count"] >= 1, details
    errors = _find_error(details, "hostname")
    assert errors is not None, details["errors"]
    # TD-I-4：组物理行号为 {2, 3}，不断言具体某一行
    assert errors["row"] in {2, 3}, errors
    assert LOCK_REASON_SUBSTRING in errors["reason"], errors
    assert after == before, f"batch left residue: {before} -> {after}"


def test_dr_f036_01_soft_delete_before_write_is_treated_as_new(
    role_client_factory, auth_session_factory
):
    """对照：软删发生在写入的预校验之前 ⇒ 按 §8.1「不存在」新建（`created==1`）。"""
    editor, user, _ = role_client_factory("EDITOR")
    admin, _, _ = role_client_factory("ADMIN")
    c = _cluster(editor, code="F036C")
    _network(editor, c["id"], name="f036-net3", cidr="10.38.0.0/24")
    host = _api_resource(editor, c["code"], "f036-h3")
    rows = [
        _row(
            cluster=c["code"],
            hostname="f036-h3",
            resource_type=BM,
            name="eth0",
            network="f036-net3",
            ip="10.38.0.11",
        )
    ]
    assert _validate(editor, rows).json()["error_count"] == 0
    deleted = admin.delete(
        f"/api/v1/resources/{host['id']}", params={"version": host["version"]}
    )
    assert deleted.status_code == 204, deleted.text

    session = auth_session_factory()
    try:
        created, interfaces_created, ips_created, total_rows = _write_service(
            session, _operator(user), rows
        )
    finally:
        session.close()
    assert (created, interfaces_created, ips_created, total_rows) == (1, 1, 1, 1)

    with auth_session_factory() as verify:
        new_row = verify.execute(
            text(
                "SELECT id FROM resources WHERE hostname = 'f036-h3' "
                "AND deleted_at IS NULL"
            )
        ).scalar_one()
        old_deleted = verify.execute(
            text("SELECT deleted_at FROM resources WHERE id = :id"), {"id": host["id"]}
        ).scalar_one()
    assert str(new_row) != host["id"]
    assert old_deleted is not None

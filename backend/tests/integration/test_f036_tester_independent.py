"""F036 Tester 独立验证用例（TEST 阶段，非 Backend 用例的复制）。

覆盖 V2 / V2.2 / V2.3 / V2.5（真实 PostgreSQL 双会话强制争用），构造与断言
由 Tester 独立编写：

* 会话 B（软删方）用**裸 SQL** 在同一事务内先 ``SELECT … FOR UPDATE`` 持
  ``resources`` 行锁，再 ``UPDATE … SET deleted_at = now(), version = version + 1``
  并提交 —— 不依赖 ``resource_service.delete_resource`` 的内部 commit 语义，
  从而证明产品行为（并发软删已提交）与 Backend 实现细节解耦；
* 写入方（线程 A）独立会话调 ``unified.write_import``，以
  ``pg_blocking_pids`` 轮询证实阻塞（不靠固定 sleep）；
* 断言 ``422 / IMPORT_VALIDATION_FAILED``、``field == "hostname"``、
  ``row == 2``、``reason`` 含子串（TD-I-3）、``related_row is None``、零写入
  （三表计数 + 窗口内 ``action='CREATE'`` Audit 不变）；
* 对照组（V2.3）：软删发生在写入预校验之前 ⇒ 按 §8.1「不存在」新建 ``created==1``。

环境：``TEST_DATABASE_URL`` 指向真实 PostgreSQL 16；两会话显式
``SET TRANSACTION ISOLATION LEVEL READ COMMITTED`` 并断言实测隔离级别。
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
from app.services import resource_interface_ip_import as unified
from integration.test_ip_addresses import (  # noqa: F401  (升值复用既有 fixture)
    _cluster,
    _network,
    _operator,
    role_client_factory,
)

VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
WRITE = "/api/v1/imports/resource-interfaces-ips"
LOCK_REASON_SUBSTRING = "does not exist or is not selectable"

HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
    "memory_mb", "disk_gb", "hypervisor", "manufacturer", "model",
    "serial_number", "cpu_model", "cpu_sockets", "cpu_cores", "gpu_model",
    "gpu_count", "name", "interface_type", "mac_address", "speed_mbps", "mtu",
    "enabled", "network", "ip",
]


def _row(**values) -> list[str]:
    return [str(values.get(header, "")) for header in HEADERS]


def _csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _http_write(client, rows):
    return client.post(
        WRITE,
        files={"file": ("i.csv", _csv(rows), "application/octet-stream")},
        data={"format": "csv"},
    )


def _http_validate(client, rows):
    return client.post(
        VALIDATE,
        files={"file": ("i.csv", _csv(rows), "application/octet-stream")},
        data={"format": "csv"},
    )


def _snapshot(session) -> dict[str, int]:
    return {
        "resources": int(session.execute(text("SELECT count(*) FROM resources")).scalar_one()),
        "interfaces": int(session.execute(text("SELECT count(*) FROM interfaces")).scalar_one()),
        "ip_addresses": int(session.execute(text("SELECT count(*) FROM ip_addresses")).scalar_one()),
        "audit_create": int(
            session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'CREATE'")).scalar_one()
        ),
        "audit_total": int(session.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()),
    }


def _wait_blocked_by(engine, blocked_pid: int, blocking_pid: int, deadline: float = 20.0) -> bool:
    end = time.monotonic() + deadline
    with engine.connect() as conn:
        while time.monotonic() < end:
            pids = conn.execute(text("SELECT pg_blocking_pids(:p)"), {"p": blocked_pid}).scalar_one()
            if int(blocking_pid) in {int(p) for p in pids}:
                return True
            time.sleep(0.01)
    return False


class _Writer(threading.Thread):
    """写入方线程：独立会话 + 显式 READ COMMITTED，先公布 backend pid。"""

    def __init__(self, factory, operator, rows) -> None:
        super().__init__(daemon=True)
        self.factory = factory
        self.operator = operator
        self.rows = rows
        self.pid: int | None = None
        self.isolation: str | None = None
        self.ready = threading.Event()
        self.outcome: object = None

    def run(self) -> None:
        session = self.factory()
        try:
            session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            self.isolation = session.execute(text("SHOW transaction_isolation")).scalar_one()
            self.pid = int(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            self.ready.set()
            self.outcome = unified.write_import(
                session, self.operator, _csv(self.rows), "csv", Settings(_env_file=None)
            )
        except BaseException as exc:  # noqa: BLE001 - 结果收集
            self.outcome = exc
        finally:
            session.close()


def _interleave(*, auth_session_factory, committed_engine, operator, client, code, hostname, net, cidr, rows):
    cluster = _cluster(client, code=code)
    _network(client, cluster["id"], name=net, cidr=cidr)
    created = client.post(
        "/api/v1/resources",
        json={"cluster": cluster["code"], "hostname": hostname, "resource_type": "BARE_METAL"},
    )
    assert created.status_code == 201, created.text
    host = created.json()["resource"]
    assert _http_validate(client, rows).json()["error_count"] == 0

    with auth_session_factory() as snapshot_session:
        before = _snapshot(snapshot_session)

    session_b = auth_session_factory()
    writer = None
    try:
        session_b.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        isolation_b = session_b.execute(text("SHOW transaction_isolation")).scalar_one()
        assert isolation_b == "read committed", f"BLOCKED: session B isolation {isolation_b!r}"
        session_b.execute(
            text("SELECT id FROM resources WHERE id = :id FOR UPDATE"), {"id": host["id"]}
        ).first()
        pid_b = int(session_b.execute(text("SELECT pg_backend_pid()")).scalar_one())

        writer = _Writer(auth_session_factory, operator, rows)
        writer.start()
        assert writer.ready.wait(timeout=20.0), "writer never published its pid"
        assert writer.isolation == "read committed", f"BLOCKED: writer isolation {writer.isolation!r}"
        assert _wait_blocked_by(committed_engine, writer.pid, pid_b), (
            f"BLOCKED: writer pid {writer.pid} never blocked by pid {pid_b} within 20s "
            f"(isolation B={isolation_b} A={writer.isolation}); interleaving not reached"
        )
        # 裸 SQL 软删（同一事务，提交即释放行锁）；version 与 deleted_at 同时更新
        session_b.execute(
            text(
                "UPDATE resources SET deleted_at = now(), version = version + 1 "
                "WHERE id = :id"
            ),
            {"id": host["id"]},
        )
        session_b.commit()
        writer.join(timeout=60)
    finally:
        session_b.close()

    assert writer is not None and not writer.is_alive(), "writer session hung"
    with auth_session_factory() as verify:
        after = _snapshot(verify)
        deleted_at = verify.execute(
            text("SELECT deleted_at FROM resources WHERE id = :id"), {"id": host["id"]}
        ).scalar_one()
    assert deleted_at is not None, "host was not soft-deleted by session B"
    return writer, before, after, host


# ---------------------------------------------------------------- V2.5 (独立)


def _mapped_from_ast() -> dict[str, str]:
    tree = ast.parse(Path(unified.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_app_error_field":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    return {
                        ast.literal_eval(k): ast.literal_eval(v)
                        for k, v in zip(inner.keys, inner.values)
                    }
    raise AssertionError("no mapped dict literal")


def test_tester_v2_5_vocabulary_four_entries_no_new_keys():
    mapped = _mapped_from_ast()
    assert set(mapped) == {
        "address", "virtual_machine.host_resource_id", "interface", "resource",
    }, f"unexpected keys: {sorted(mapped)}"
    assert mapped["resource"] == "hostname"
    assert mapped["address"] == "ip"
    assert mapped["virtual_machine.host_resource_id"] == "host"
    assert mapped["interface"] == "name"
    # 行为面（不经 AST）独立复核四项 + 兜底
    def field(path):
        return unified._app_error_field(
            ValidationError(details={"fields": [{"field": path, "message": "x"}]})
        )
    for path, expected in {
        "address": "ip",
        "virtual_machine.host_resource_id": "host",
        "interface": "name",
        "resource": "hostname",
    }.items():
        assert field(path) == expected, path
    assert field("hardware.model") == "model"


# ------------------------------------------------------------ V2 并发软删归因


def test_tester_v2_concurrent_soft_delete_is_hostname_and_zero_write(
    role_client_factory, auth_session_factory, committed_engine
):
    editor, user, _ = role_client_factory("EDITOR")
    rows = [
        _row(
            cluster="TESTV2",
            hostname="tester-v2-host",
            resource_type="BARE_METAL",
            name="eno1",
            network="tester-v2-net",
            ip="10.96.0.21",
        )
    ]
    writer, before, after, host = _interleave(
        auth_session_factory=auth_session_factory,
        committed_engine=committed_engine,
        operator=_operator(user),
        client=editor,
        code="TESTV2",
        hostname="tester-v2-host",
        net="tester-v2-net",
        cidr="10.96.0.0/24",
        rows=rows,
    )
    failure = writer.outcome
    assert isinstance(failure, ImportValidationFailed), f"outcome={failure!r}"
    assert failure.status_code == 422
    assert failure.code == "IMPORT_VALIDATION_FAILED"
    errors = failure.details["errors"]
    matches = [e for e in errors if e["field"] == "hostname" and e["row"] == 2]
    assert len(matches) == 1, errors
    error = matches[0]
    assert LOCK_REASON_SUBSTRING in error["reason"], error  # TD-I-3 子串口径
    assert error["related_row"] is None, error
    # 零写入：三表计数与窗口内 CREATE Audit 均不变（B 的 UPDATE 不产生 CREATE）
    for table in ("resources", "interfaces", "ip_addresses"):
        assert after[table] == before[table], f"{table}: {before[table]} -> {after[table]}"
    assert after["audit_create"] == before["audit_create"], (before, after)
    # 整批失败不得留下任何挂在被删宿主下的子对象
    with auth_session_factory() as verify:
        children = int(
            verify.execute(
                text("SELECT count(*) FROM interfaces WHERE resource_id = :id"), {"id": host["id"]}
            ).scalar_one()
        )
    assert children == 0, "interfaces written against a soft-deleted host"


def test_tester_v2_3_control_soft_delete_before_write_creates_new(
    role_client_factory, auth_session_factory
):
    """边界对照（V2.3）：软删先于写入预校验 ⇒ 按「不存在」新建。"""
    editor, user, _ = role_client_factory("EDITOR")
    cluster = _cluster(editor, code="TESTV23")
    _network(editor, cluster["id"], name="tester-v23-net", cidr="10.97.0.0/24")
    created = editor.post(
        "/api/v1/resources",
        json={"cluster": cluster["code"], "hostname": "tester-v23-host", "resource_type": "BARE_METAL"},
    )
    assert created.status_code == 201, created.text
    host = created.json()["resource"]
    rows = [
        _row(
            cluster=cluster["code"],
            hostname="tester-v23-host",
            resource_type="BARE_METAL",
            name="eno1",
            network="tester-v23-net",
            ip="10.97.0.21",
        )
    ]
    assert _http_validate(editor, rows).json()["error_count"] == 0

    session = auth_session_factory()
    try:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        session.execute(
            text("UPDATE resources SET deleted_at = now(), version = version + 1 WHERE id = :id"),
            {"id": host["id"]},
        )
        session.commit()
        assert session.execute(text("SHOW transaction_isolation")).scalar_one() == "read committed"
        result = unified.write_import(
            session, _operator(user), _csv(rows), "csv", Settings(_env_file=None)
        )
    finally:
        session.close()
    assert result == (1, 1, 1, 1), result

    with auth_session_factory() as verify:
        rows_now = verify.execute(
            text(
                "SELECT id, deleted_at FROM resources WHERE hostname = 'tester-v23-host'"
            )
        ).all()
    alive = [r for r in rows_now if r.deleted_at is None]
    assert len(alive) == 1, rows_now
    assert str(alive[0].id) != host["id"]


# ------------------------------------------------- V2.4（实测定性，TD 口径偏差）


def test_tester_v2_4a_never_existing_hostname_is_created_as_new(
    role_client_factory, auth_session_factory
):
    """V2.4 情形 1 实测：批次指向**从未存在**的 hostname ⇒ §8.1「不存在→新建」。

    `docs/features/F036/test-report.md` §1 的 `V2.4` 期望（`field=="hostname"` +
    整批 422）与已批准契约 §8.1 二态判定（以及本报告 `V2.3` 的 created==1）
    相矛盾；此处按契约实测记录真实行为（Tester 不自行发明规则）。
    """
    editor, user, _ = role_client_factory("EDITOR")
    cluster = _cluster(editor, code="TESTV24")
    _network(editor, cluster["id"], name="tester-v24-net", cidr="10.98.0.0/24")
    rows = [
        _row(
            cluster=cluster["code"],
            hostname="tester-v24-brand-new",
            resource_type="BARE_METAL",
            name="eno1",
            interface_type="PHYSICAL",
            network="tester-v24-net",
            ip="10.98.0.31",
        )
    ]
    validate = _http_validate(editor, rows)
    assert validate.status_code == 200, validate.text
    assert validate.json()["error_count"] == 0, validate.text

    session = auth_session_factory()
    try:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        result = unified.write_import(
            session, _operator(user), _csv(rows), "csv", Settings(_env_file=None)
        )
    finally:
        session.close()
    # 实测：新建 Resource（不是 422）—— 与 §8.1 二态判定一致
    assert result == (1, 1, 1, 1), result


def test_tester_v2_4b_vm_host_outside_cluster_is_host_column_error(
    role_client_factory, auth_session_factory
):
    """V2.4 情形 2 实测：VM 行 `host` 指向**其它 Cluster** 的宿主 ⇒ `field=="host"`。

    同样按契约核对（模板列名为 `host`），并断言整批 422 + 零写入残留。
    """
    editor, user, _ = role_client_factory("EDITOR")
    other = _cluster(editor, code="TESTV24B")
    _network(editor, other["id"], name="tester-v24b-net", cidr="10.99.0.0/24")
    host_in_other = editor.post(
        "/api/v1/resources",
        json={"cluster": other["code"], "hostname": "tester-v24b-host", "resource_type": "BARE_METAL"},
    )
    assert host_in_other.status_code == 201, host_in_other.text
    target = _cluster(editor, code="TESTV24C")
    _network(editor, target["id"], name="tester-v24c-net", cidr="10.100.0.0/24")

    rows = [
        _row(
            cluster=target["code"],
            hostname="tester-v24c-vm",
            resource_type="VIRTUAL_MACHINE",
            host="tester-v24b-host",
            name="eno1",
            interface_type="PHYSICAL",
            network="tester-v24c-net",
            ip="10.100.0.31",
        )
    ]
    validate = _http_validate(editor, rows)
    assert validate.status_code == 200, validate.text
    body = validate.json()
    assert body["error_count"] == 1, body
    assert body["errors"][0]["field"] == "host", body["errors"]
    assert body["errors"][0]["row"] == 2, body["errors"]

    with auth_session_factory() as snapshot_session:
        before = _snapshot(snapshot_session)
    write = _http_write(editor, rows)
    assert write.status_code == 422, write.text
    assert write.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED", write.text
    with auth_session_factory() as snapshot_session:
        after = _snapshot(snapshot_session)
    assert after == before, (before, after)

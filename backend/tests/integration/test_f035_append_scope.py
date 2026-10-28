"""F035 追加导入 — 行级 §23.2 集群范围（真实 F027 access scope）。

`TD3-F035-T124.5` / `T124.6` 要求真实范围校验，因此本模块声明
``pytest.mark.real_scope``（见 ``tests/conftest.py`` 与
``test_f030_test_harness.py``）；追加语义主体在
``test_f035_append_interface_ip_import.py`` 中以 legacy scope shim 覆盖。

判据：追加行指向未授权 Cluster 时整批失败、无写入、不泄露 Cluster 存在性；
混合批「授权集群新建组 + 未授权集群追加组」同样整批失败，新建组不留存。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from integration.f015_helpers import (  # noqa: F401
    create_cluster,
    create_network,
    create_resource,
    role_client_factory,
)

pytestmark = pytest.mark.real_scope

W_VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
W_WRITE = "/api/v1/imports/resource-interfaces-ips"

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

COUNT_TABLES = ("resources", "interfaces", "ip_addresses", "audit_logs")

A_CODE = "F35SA"
B_CODE = "F35SB"  # authorized to the EDITOR
C_CODE = "F35SC"  # NOT authorized


def _row(**values) -> list[str]:
    return ["" if values.get(h) is None else str(values.get(h)) for h in HEADERS]


def _csv(rows) -> bytes:
    lines = [",".join(HEADERS)]
    lines.extend(",".join(row) for row in rows)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _post(client, path: str, data: bytes):
    return client.post(
        path,
        files={"file": ("f035-scope.csv", data, "text/csv")},
        data={"format": "csv"},
    )


def _find_error(payload: dict, field: str) -> dict | None:
    for error in payload["errors"]:
        if error["field"] == field:
            return error
    return None


def _counts(session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in COUNT_TABLES
    }


def _grant(admin, user_id, cluster_id):
    resp = admin.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster_authorization"]


@pytest.fixture
def scoped(role_client_factory):
    """ADMIN builds A / B / C; the EDITOR is granted B only."""
    admin, _, _ = role_client_factory("ADMIN", username="f035.scope.admin")
    create_cluster(admin, A_CODE, "F035 scope A")
    b = create_cluster(admin, B_CODE, "F035 scope B")
    c = create_cluster(admin, C_CODE, "F035 scope C")
    create_network(admin, B_CODE, name="f35sb-net", cidr="10.70.0.0/24")
    create_network(admin, C_CODE, name="f35sc-net", cidr="10.71.0.0/24")
    hidden_host = create_resource(admin, C_CODE, "f35-c-host")

    editor, editor_user, _ = role_client_factory("EDITOR", username="f035.scope.editor")
    _grant(admin, editor_user.id, b["id"])
    return {"admin": admin, "editor": editor, "user": editor_user, "hidden": hidden_host}


def test_td3_f035_t124_5_out_of_scope_append_row(scoped, auth_session_factory):
    """T124.5: an append row in an unauthorized Cluster fails the whole batch."""
    editor = scoped["editor"]
    data = _csv(
        [
            _row(
                cluster=C_CODE,
                hostname="f35-c-host",
                resource_type="BARE_METAL",
                name="eth0",
                network="f35sc-net",
                ip="10.71.0.11",
            )
        ]
    )
    validated = _post(editor, W_VALIDATE, data)
    assert validated.status_code == 200, validated.text
    body = validated.json()
    assert body["total_rows"] == 1
    assert body["error_count"] == 1
    error = _find_error(body, "cluster")
    assert error is not None and error["row"] == 2
    assert C_CODE not in json.dumps(body), "response leaked the unauthorized code"
    assert "f35sc-net" not in json.dumps(body)

    with auth_session_factory() as session:
        before = _counts(session)
    write = _post(editor, W_WRITE, data)
    assert write.status_code == 422, write.text
    assert write.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
    assert _find_error(write.json()["error"]["details"], "cluster") is not None
    assert C_CODE not in write.text
    with auth_session_factory() as session:
        after = _counts(session)
        appended = session.execute(
            text("SELECT count(*) FROM interfaces WHERE name = 'eth0' AND resource_id = :id"),
            {"id": scoped["hidden"]["id"]},
        ).scalar_one()
    assert after == before
    assert appended == 0


def test_td3_f035_t124_6_mixed_batch_with_out_of_scope_append(scoped, auth_session_factory):
    """T124.6: authorized create group + unauthorized append group -> no residue."""
    editor = scoped["editor"]
    data = _csv(
        [
            _row(
                cluster=B_CODE,
                hostname="f35-b-new",
                resource_type="BARE_METAL",
                name="eth0",
                network="f35sb-net",
                ip="10.70.0.11",
            ),
            _row(
                cluster=C_CODE,
                hostname="f35-c-host",
                resource_type="BARE_METAL",
                name="eth0",
                network="f35sc-net",
                ip="10.71.0.11",
            ),
        ]
    )
    with auth_session_factory() as session:
        before = _counts(session)
    write = _post(editor, W_WRITE, data)
    assert write.status_code == 422, write.text
    details = write.json()["error"]["details"]
    assert _find_error(details, "cluster") is not None
    with auth_session_factory() as session:
        after = _counts(session)
        residue = session.execute(
            text("SELECT count(*) FROM resources WHERE hostname = 'f35-b-new'")
        ).scalar_one()
    assert after == before, f"scope-rejected import left residue: {before} -> {after}"
    assert residue == 0

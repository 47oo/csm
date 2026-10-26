"""F034 CSV text carrier — row-level Cluster scope (real F027 access scope).

`TD3-T115.3` and `TD3-ATOM.3` require the *real* access scope, so this module
declares ``pytest.mark.real_scope`` (see ``tests/conftest.py`` and
``test_f030_test_harness.py``). Everything else about the text carrier is
covered by ``test_f034_csv_text_carrier.py`` under the legacy scope shim.

The assertions are identical for the file carrier and the text carrier: an
out-of-scope Cluster row yields one row-level `cluster` error without leaking
the Cluster code, and the write fails as a whole batch leaving zero residue.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from integration.f015_helpers import (  # noqa: F401
    create_cluster,
    create_network,
    role_client_factory,
)

pytestmark = pytest.mark.real_scope

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

PASTED_FILE_NAME = "csm-pasted-import.csv"
PASTED_MIME = "text/csv;charset=utf-8"
FILE_NAME = "f034-scope-file.csv"
FILE_MIME = "text/csv"

R_VALIDATE = "/api/v1/imports/resources/validate"
R_WRITE = "/api/v1/imports/resources"
W_VALIDATE = "/api/v1/imports/resource-interfaces-ips/validate"
W_WRITE = "/api/v1/imports/resource-interfaces-ips"

BM_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "manufacturer",
    "model", "serial_number", "cpu_model", "cpu_sockets", "cpu_cores",
    "memory_mb", "gpu_model", "gpu_count",
]
W26_HEADERS = [
    "cluster", "hostname", "resource_type", "role", "status", "host", "vcpu",
    "memory_mb", "disk_gb", "hypervisor", "manufacturer", "model",
    "serial_number", "cpu_model", "cpu_sockets", "cpu_cores", "gpu_model",
    "gpu_count", "name", "interface_type", "mac_address", "speed_mbps", "mtu",
    "enabled", "network", "ip",
]
COUNT_TABLES = ("resources", "interfaces", "ip_addresses", "audit_logs")

C_CODE = "F34SC"
B_CODE = "F34SB"


def _post(client, path: str, data: bytes, carrier: str = "text"):
    if carrier == "text":
        files = {"file": (PASTED_FILE_NAME, data, PASTED_MIME)}
    else:
        files = {"file": (FILE_NAME, data, FILE_MIME)}
    return client.post(path, files=files, data={"format": "csv"})


def _line(headers, values) -> str:
    return ",".join("" if values.get(n) is None else str(values.get(n)) for n in headers)


def _csv(headers, rows) -> bytes:
    body = "\n".join([",".join(headers), *(_line(headers, r) for r in rows)]) + "\n"
    return body.encode("utf-8")


def _grant(admin, user_id, cluster_id):
    resp = admin.post(
        f"/api/v1/users/{user_id}/cluster-authorizations",
        json={"cluster_id": str(cluster_id)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["cluster_authorization"]


def _counts(session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in COUNT_TABLES
    }


@pytest.fixture
def scoped(role_client_factory):
    """ADMIN builds clusters A / B / C; an EDITOR is granted A and B only."""
    admin, _, _ = role_client_factory("ADMIN", username="f034.scope.admin")
    a = create_cluster(admin, "F34SA", "F034 scope A")
    b = create_cluster(admin, B_CODE, "F034 scope B")
    create_cluster(admin, C_CODE, "F034 scope C")
    create_network(admin, B_CODE, name="f34sb-net", cidr="10.35.0.0/24")
    create_network(admin, C_CODE, name="f34sc-net", cidr="10.36.0.0/24")

    editor, editor_user, _ = role_client_factory("EDITOR", username="f034.scope.editor")
    _grant(admin, editor_user.id, a["id"])
    _grant(admin, editor_user.id, b["id"])
    return {"admin": admin, "editor": editor, "user": editor_user}


def test_td3_t115_3_atom3_out_of_scope_row_fails_whole_batch(
    scoped, auth_session_factory
):
    """TD3-T115.3 / TD3-ATOM.3: out-of-scope row -> whole batch rejected, no residue."""
    editor = scoped["editor"]
    data = _csv(
        BM_HEADERS,
        [
            {"cluster": B_CODE, "hostname": "f34-s-ok", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE"},
            {"cluster": C_CODE, "hostname": "f34-s-bad", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE"},
        ],
    )

    file_resp = _post(editor, R_VALIDATE, data, "file")
    text_resp = _post(editor, R_VALIDATE, data, "text")
    assert file_resp.status_code == text_resp.status_code == 200, (
        file_resp.text[:300],
        text_resp.text[:300],
    )
    assert file_resp.json() == text_resp.json()
    body = text_resp.json()
    assert body["total_rows"] == 2
    assert body["importable_rows"] == 1
    assert body["error_count"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["field"] == "cluster"
    assert C_CODE not in json.dumps(body), "response leaked the out-of-scope code"

    with auth_session_factory() as session:
        before = _counts(session)
    for carrier in ("file", "text"):
        write = _post(editor, R_WRITE, data, carrier)
        assert write.status_code == 422, write.text[:300]
        assert write.json()["error"]["code"] == "IMPORT_VALIDATION_FAILED"
        assert write.json()["error"]["details"]["errors"][0]["field"] == "cluster"
        assert C_CODE not in write.text

    with auth_session_factory() as session:
        after = _counts(session)
        residue = session.execute(
            text("SELECT count(*) FROM resources WHERE hostname LIKE 'f34-s-%'")
        ).scalar_one()
    assert after == before, f"scope-rejected import left residue: {before} -> {after}"
    assert residue == 0


def test_td3_t115_3_f023_out_of_scope_row(scoped, auth_session_factory):
    """TD3-T115.3 (F023 entry): interfaces / IPs also roll back and stay hidden."""
    editor = scoped["editor"]
    data = _csv(
        W26_HEADERS,
        [
            {"cluster": B_CODE, "hostname": "f34-sw-ok", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE", "name": "eth0", "interface_type": "PHYSICAL", "network": "f34sb-net", "ip": "10.35.0.11"},
            {"cluster": C_CODE, "hostname": "f34-sw-bad", "resource_type": "BARE_METAL", "role": "COMPUTE", "status": "IDLE", "name": "eth0", "interface_type": "PHYSICAL", "network": "f34sc-net", "ip": "10.36.0.11"},
        ],
    )

    file_resp = _post(editor, W_VALIDATE, data, "file")
    text_resp = _post(editor, W_VALIDATE, data, "text")
    assert file_resp.status_code == text_resp.status_code == 200
    assert file_resp.json() == text_resp.json()
    body = text_resp.json()
    assert body["total_rows"] == 2
    assert body["error_count"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["field"] == "cluster"
    assert C_CODE not in json.dumps(body)
    assert "f34sc-net" not in json.dumps(body)

    with auth_session_factory() as session:
        before = _counts(session)
    for carrier in ("file", "text"):
        write = _post(editor, W_WRITE, data, carrier)
        assert write.status_code == 422, write.text[:300]
        assert C_CODE not in write.text
    with auth_session_factory() as session:
        after = _counts(session)
    assert after == before

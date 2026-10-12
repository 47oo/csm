"""Shared helpers for the F016 integration-acceptance tests (Tester-authored).

F016 is an acceptance Feature: these helpers drive the **real** deployed stack
(Nginx entry -> FastAPI -> PostgreSQL) over real HTTP using ``httpx``. They never
use ``TestClient``, never mock and never touch SQLite — constraint/concurrency
evidence stays with the authoritative Feature suites (REUSE anchors).

Environment (guarded so a normal ``pytest tests`` run is a no-op):

* ``F016_ACCEPTANCE=1``                      enable the acceptance module;
* ``F016_BASE_URL`` (``http://localhost:18080``)  entry Nginx origin;
* ``F016_ORIGIN``    (defaults to ``F016_BASE_URL``)  same-origin Origin header;
* ``F016_ADMIN_USERNAME`` / ``F016_ADMIN_PASSWORD``   bootstrap ADMIN.

Writes are always sent with an ``Origin`` equal to the request authority so the
same-origin CSRF guard (Contract §2.1) is exercised exactly as a browser would.
"""

from __future__ import annotations

import csv
import io
import os
import uuid

import httpx

DEFAULT_BASE_URL = "http://localhost:18080"


def acceptance_enabled() -> bool:
    return os.environ.get("F016_ACCEPTANCE") == "1"


def base_url() -> str:
    return os.environ.get("F016_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def origin() -> str:
    return os.environ.get("F016_ORIGIN", base_url()).rstrip("/")


def admin_credentials() -> tuple[str, str]:
    return (
        os.environ.get("F016_ADMIN_USERNAME", "admin"),
        os.environ.get("F016_ADMIN_PASSWORD", ""),
    )


def run_suffix() -> str:
    """Per-process suffix so reruns against a warm database do not collide."""
    return uuid.uuid4().hex[:6]


class Api:
    """Thin real-HTTP client bound to one authenticated (or anonymous) session."""

    def __init__(self, login: tuple[str, str] | None = None) -> None:
        self.base = base_url()
        self.client = httpx.Client(
            base_url=self.base,
            headers={"Origin": origin()},
            timeout=120.0,
            follow_redirects=False,
        )
        if login is not None:
            self.login(*login)

    # --- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Api":
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.close()

    # --- auth --------------------------------------------------------------
    def login(self, username: str, password: str) -> httpx.Response:
        resp = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
        return resp

    # --- raw verbs ---------------------------------------------------------
    def request(self, method: str, path: str, **kw) -> httpx.Response:
        return self.client.request(method, path, **kw)

    def get(self, path: str, **kw) -> httpx.Response:
        return self.client.get(path, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return self.client.post(path, **kw)

    def patch(self, path: str, **kw) -> httpx.Response:
        return self.client.patch(path, **kw)

    def delete(self, path: str, **kw) -> httpx.Response:
        return self.client.delete(path, **kw)


def ok(resp: httpx.Response, *status: int) -> dict:
    """Assert the (expected) success status and return the JSON body."""
    assert resp.status_code in status, f"{resp.request.method} {resp.request.url}: {resp.status_code} {resp.text}"
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


def error_code(resp: httpx.Response) -> str:
    try:
        return resp.json()["error"]["code"]
    except Exception:  # noqa: BLE001
        return ""


def error_reason(resp: httpx.Response) -> str | None:
    try:
        return resp.json()["error"]["details"].get("reason")
    except Exception:  # noqa: BLE001
        return None


# --- account helpers ---------------------------------------------------------


def make_role_api(admin: Api, role: str, password: str = "f016-role-pass") -> Api:
    """Create an account of ``role`` via the real ADMIN endpoint and log it in."""
    username = f"f016-{role.lower()}-{run_suffix()}"
    ok(
        admin.post(
            "/api/v1/users",
            json={"username": username, "password": password, "role": role},
        ),
        201,
    )
    return Api((username, password))


# --- domain helpers (real API) ----------------------------------------------


def create_cluster(api: Api, code: str, name: str | None = None, **extra) -> dict:
    body = {"code": code, "name": name or code}
    body.update(extra)
    return ok(api.post("/api/v1/clusters", json=body), 201)["cluster"]


def create_resource(
    api: Api, cluster: str, hostname: str, resource_type: str = "BARE_METAL", **extra
) -> dict:
    body = {"cluster": cluster, "hostname": hostname, "resource_type": resource_type}
    body.update(extra)
    return ok(api.post("/api/v1/resources", json=body), 201)["resource"]


def create_interface(api: Api, resource_id: str, name: str, **extra) -> dict:
    body = {"resource": resource_id, "name": name}
    body.update(extra)
    return ok(api.post("/api/v1/interfaces", json=body), 201)["interface"]


def create_network(
    api: Api, cluster: str, name: str, cidr: str, **extra
) -> dict:
    body = {"cluster": cluster, "name": name, "cidr": cidr}
    body.update(extra)
    return ok(api.post("/api/v1/networks", json=body), 201)["network"]


def create_pool(api: Api, network_id: str, name: str, start: str, end: str, **extra) -> dict:
    body = {
        "network": network_id,
        "name": name,
        "start_address": start,
        "end_address": end,
    }
    body.update(extra)
    return ok(api.post("/api/v1/ip-pools", json=body), 201)["ip_pool"]


def create_ip(api: Api, network_id: str, address: str, **extra) -> dict:
    body = {"network": network_id, "address": address}
    body.update(extra)
    return ok(api.post("/api/v1/ip-addresses", json=body), 201)["ip_address"]


def bind_ip(api: Api, ip: dict, interface_id: str) -> dict:
    return ok(
        api.patch(
            f"/api/v1/ip-addresses/{ip['id']}",
            json={"version": ip["version"], "interface": interface_id},
        ),
        200,
    )["ip_address"]


def create_service(api: Api, resource_id: str, name: str, **extra) -> dict:
    body = {"resource": resource_id, "name": name}
    body.update(extra)
    return ok(api.post("/api/v1/services", json=body), 201)["service"]


def create_endpoint(
    api: Api, service_id: str, ip_id: str, protocol: str = "TCP", port: int = 22
) -> dict:
    return ok(
        api.post(
            "/api/v1/service-endpoints",
            json={
                "service": service_id,
                "ip_address": ip_id,
                "protocol": protocol,
                "port": port,
            },
        ),
        201,
    )["service_endpoint"]


def soft_delete(api: Api, path: str, version: int) -> None:
    resp = api.delete(f"{path}?version={version}")
    assert resp.status_code == 204, f"delete {path}: {resp.status_code} {resp.text}"


# --- import helpers ----------------------------------------------------------

BM_HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "memory_mb",
    "gpu_model",
    "gpu_count",
]
VM_HEADERS = [
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
]


def csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([("" if v is None else str(v)) for v in row])
    return buffer.getvalue().encode("utf-8")


def bm_row(cluster: str, hostname: str, **extra) -> list:
    row = {"cluster": cluster, "hostname": hostname, "resource_type": "BARE_METAL"}
    row.update(extra)
    return [row.get(h, "") for h in BM_HEADERS]


def vm_row(cluster: str, hostname: str, host: str, **extra) -> list:
    row = {
        "cluster": cluster,
        "hostname": hostname,
        "resource_type": "VIRTUAL_MACHINE",
        "host": host,
    }
    row.update(extra)
    return [row.get(h, "") for h in VM_HEADERS]


def import_request(
    api: Api, path: str, data: bytes, fmt: str = "csv"
) -> httpx.Response:
    return api.post(
        path,
        files={"file": (f"f016.{fmt}", data, "application/octet-stream")},
        data={"format": fmt},
    )


VALIDATE_PATH = "/api/v1/imports/resources/validate"
WRITE_PATH = "/api/v1/imports/resources"
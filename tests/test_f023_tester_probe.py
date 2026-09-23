"""F023 独立验收探针（Tester）。

独立于开发 Agent 的 ``tests/test_f023_ip_range_selection.py`` 与
``tests/test_ip_allocations_api.py``，逐条复验 Product Handoff 的 AC-01 ~
AC-20（契约 ``docs/api/f021-ip-address-allocation.md`` 修订版）。

本文件只新增测试，**不修改任何生产实现**（``backend/app/**``、
``frontend/src/**``）。

运行（真实 PostgreSQL 16）：

    export PGPASSWORD=csm
    export CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm"
    .venv/bin/python -m pytest tests/test_f023_tester_probe.py -q
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import AUTH_PASSWORD, AUTH_USERNAME, create_user, login
from tests.database.helpers import raw_connection_dsn, upgrade_to_head
from tests.ip_address_drift_helpers import find_drift
from tests.test_ip_allocations_api import (
    AUTO,
    MANUAL,
    READ_FIELDS,
    _active_ip_count,
    _auto,
    _create_bm,
    _create_cluster,
    _create_ip,
    _create_nic,
    _create_range,
    _isolated_clients,
    _manual,
    _raw_chain,
    _raw_ip,
    _total_ip_count,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "api" / "f021-ip-address-allocation.md"
MIGRATION_HEAD = "0010_f022_ip_range_metadata"

EXPECTED_TABLES = {
    "alembic_version",
    "bare_metals",
    "clusters",
    "containers",
    "ip_address_ranges",
    "ip_addresses",
    "network_interfaces",
    "service_carriers",
    "services",
    "sessions",
    "users",
    "virtual_machines",
}
IP_ADDRESS_COLUMNS = {
    "id",
    "network_interface_id",
    "cluster_id",
    "ip_address",
    "created_at",
    "updated_at",
    "deleted_at",
}
IP_ADDRESS_RANGE_COLUMNS = {
    "id",
    "cluster_id",
    "start_ip",
    "end_ip",
    "name",
    "subnet_mask",
    "vlan",
    "created_at",
    "updated_at",
    "deleted_at",
}


# --------------------------------------------------------------------------- #
# AC-19：修订后的契约已落盘且 READY；ip_address_range_id 明确必填
# --------------------------------------------------------------------------- #
def test_t23_ac19_contract_persisted_ready_and_required():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "Status: **READY**" in text
    assert "F023 增量修订" in text
    # 请求字段表中 ip_address_range_id 行为「必填」
    assert "| `ip_address_range_id` | integer | **是** | 否 |" in text
    # 旧并集表述已被修订
    assert "全部活跃范围段的并集**内取**数值最小的未占用 IPv4" not in text


# --------------------------------------------------------------------------- #
# AC-01：成功响应恰为 F005 五字段；请求不含回显扩展
# --------------------------------------------------------------------------- #
def test_t23_ac01_response_closed_fields(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cid = _create_cluster(client, "ac01")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.1.0.1", "10.1.0.255")

    resp = _auto(client, nic, rid)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == READ_FIELDS
    assert not ({"cluster_id", "ip_address_range_id", "status", "deleted_at"} & set(body))


# --------------------------------------------------------------------------- #
# AC-02：缺 / 非整数 / null ip_address_range_id → 400 且 field，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["MISSING", "abc", None, 1.5, [], {}])
def test_t23_ac02_missing_or_invalid_range_id(auth_client_and_raw, value):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac02")
    nic = _create_nic(client, _create_bm(client, cid))
    payload: dict = {"network_interface_id": nic}
    if value != "MISSING":
        payload["ip_address_range_id"] = value

    resp = client.post(AUTO, json=payload)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any(
        d["field"] == "ip_address_range_id" for d in resp.json()["error"]["details"]
    )
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-03：字段封闭，未识别字段（含 cluster_id）→ 400，无写入，无「缺字段成功」路径
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "extra",
    [
        {"cluster_id": 1},
        {"status": "ACTIVE"},
        {"mode": "auto"},
        {"reserved_addresses": []},
        {"ip_address": "10.0.0.1"},
    ],
)
def test_t23_ac03_unknown_fields_rejected(auth_client_and_raw, extra):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac03")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.2.0.1", "10.2.0.255")

    resp = client.post(
        AUTO,
        json={"network_interface_id": nic, "ip_address_range_id": rid, **extra},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _total_ip_count(conn) == 0

    # 不存在「未指定范围段也成功」的路径。
    omit = client.post(AUTO, json={"network_interface_id": nic})
    assert omit.status_code == 400
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-04 / AC-05 / AC-06：范围段活跃性 / 归属 / 存在性
# --------------------------------------------------------------------------- #
def test_t23_ac04_soft_deleted_range_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac04")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.3.0.1", "10.3.0.255")
    assert client.delete(f"/api/ip-address-ranges/{rid}").status_code == 204

    resp = _auto(client, nic, rid)
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    d = resp.json()["error"]["details"][0]
    assert d["field"] == "ip_address_range_id"
    assert d["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0


def test_t23_ac05_other_cluster_range_409_and_nic_404_distinct(auth_client_and_raw):
    client, conn = auth_client_and_raw
    a = _create_cluster(client, "ac05-a")
    b = _create_cluster(client, "ac05-b")
    nic_a = _create_nic(client, _create_bm(client, a))
    rid_b = _create_range(client, b, "10.4.0.1", "10.4.0.255")

    resp = _auto(client, nic_a, rid_b)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "CONFLICT"
    d = resp.json()["error"]["details"][0]
    assert d["field"] == "ip_address_range_id"
    assert d["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0

    nic_404 = _auto(client, 999999999, rid_b)
    assert nic_404.status_code == 404
    assert nic_404.json()["error"]["details"] == []


def test_t23_ac06_nonexistent_range_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac06")
    nic = _create_nic(client, _create_bm(client, cid))

    resp = _auto(client, nic, 999999999)
    assert resp.status_code == 404, resp.text
    d = resp.json()["error"]["details"][0]
    assert d["field"] == "ip_address_range_id"
    assert d["code"] == "IP_ADDRESS_RANGE_UNAVAILABLE"
    assert _total_ip_count(conn) == 0


# --------------------------------------------------------------------------- #
# AC-07 / AC-08 / AC-09：单范围取最小、不取未选段、跳过占用
# --------------------------------------------------------------------------- #
def test_t23_ac07_08_09_single_range_min_only(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cid = _create_cluster(client, "ac07")
    nic = _create_nic(client, _create_bm(client, cid))
    low = _create_range(client, cid, "10.5.0.1", "10.5.0.3")
    high = _create_range(client, cid, "10.5.0.10", "10.5.0.12")

    # 选 high：取 high 内最小，不取 low 的更小值。
    first = _auto(client, nic, high)
    assert first.status_code == 201, first.text
    assert first.json()["ip_address"] == "10.5.0.10"

    # 跳过 high 内已占用 → 下一个。
    second = _auto(client, nic, high)
    assert second.status_code == 201, second.text
    assert second.json()["ip_address"] == "10.5.0.11"

    # 选 low：取 low 内最小。
    third = _auto(client, nic, low)
    assert third.status_code == 201, third.text
    assert third.json()["ip_address"] == "10.5.0.1"


# --------------------------------------------------------------------------- #
# AC-10 / AC-11：所选段耗尽 → 409 NO_AVAILABLE_IP，不回退、无写入
# --------------------------------------------------------------------------- #
def test_t23_ac10_11_exhaustion_no_fallback_no_write(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac10")
    nic = _create_nic(client, _create_bm(client, cid))
    full = _create_range(client, cid, "10.6.0.10", "10.6.0.11")
    # 另一活跃段有可用地址，但未被选择。
    _create_range(client, cid, "10.6.0.1", "10.6.0.3")
    _create_ip(client, nic, "10.6.0.10")
    _create_ip(client, nic, "10.6.0.11")
    before = _total_ip_count(conn)

    resp = _auto(client, nic, full)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "CONFLICT"
    d = resp.json()["error"]["details"][0]
    assert d["code"] == "NO_AVAILABLE_IP"
    assert d["field"] is None
    assert _total_ip_count(conn) == before


# --------------------------------------------------------------------------- #
# AC-12 / AC-13：规范化写入；无隐式保留地址
# --------------------------------------------------------------------------- #
def test_t23_ac12_canonical_write(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cid = _create_cluster(client, "ac12")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "010.007.000.001", "010.007.000.003")

    body = _auto(client, nic, rid).json()
    assert body["ip_address"] == "10.7.0.1"
    assert client.get(f"/api/ip-addresses/{body['id']}").json()["ip_address"] == "10.7.0.1"


def test_t23_ac13_no_implicit_reserved_skip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cid = _create_cluster(client, "ac13")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.8.0.0", "10.8.0.255")

    resp = _auto(client, nic, rid)
    assert resp.status_code == 201, resp.text
    assert resp.json()["ip_address"] == "10.8.0.0"

    # 网络地址被占后取下一个（.1），不跳过。
    nic2 = _create_nic(client, _create_bm(client, cid, hostname="n2"), name="eth1")
    resp2 = _auto(client, nic2, rid)
    assert resp2.json()["ip_address"] == "10.8.0.1"


# --------------------------------------------------------------------------- #
# AC-14：占用按字面 / 范围归属按数值；软删释放
# --------------------------------------------------------------------------- #
def test_t23_ac14_literal_vs_numeric_boundaries(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid, _, nic = _raw_chain(conn, "ac14")
    rid = _create_range(client, cid, "10.9.0.1", "10.9.0.2")

    # 活跃字面 "010.0.0.1"（数值同 10.9.0.1 但字面不同）不阻止选中。
    _raw_ip(conn, nic, cid, "010.9.0.1")
    r1 = _auto(client, nic, rid)
    assert r1.status_code == 201, r1.text
    assert r1.json()["ip_address"] == "10.9.0.1"

    # 活跃字面 "10.9.0.1/16" 不阻止选中 10.9.0.2。
    nic2 = _create_nic(client, _create_bm(client, cid, hostname="n2"), name="eth1")
    _raw_ip(conn, nic2, cid, "10.9.0.1/16")
    r2 = _auto(client, nic2, rid)
    assert r2.status_code == 201, r2.text
    assert r2.json()["ip_address"] == "10.9.0.2"


def test_t23_ac14_same_literal_occupied_and_soft_delete_releases(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid, _, nic = _raw_chain(conn, "ac14b")
    rid = _create_range(client, cid, "10.10.0.1", "10.10.0.2")

    _raw_ip(conn, nic, cid, "10.10.0.1")
    r1 = _auto(client, nic, rid)
    assert r1.json()["ip_address"] == "10.10.0.2"

    # 软删 10.10.0.2 → 释放，再次可取。
    conn.execute("UPDATE ip_addresses SET deleted_at = now() WHERE ip_address = '10.10.0.2'")
    r2 = _auto(client, nic, rid)
    assert r2.json()["ip_address"] == "10.10.0.2"


# --------------------------------------------------------------------------- #
# AC-15：手动分配语义不变
# --------------------------------------------------------------------------- #
def test_t23_ac15_manual_unchanged(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "ac15")
    nic = _create_nic(client, _create_bm(client, cid))
    _create_range(client, cid, "10.11.0.1", "10.11.0.255")

    ok = _manual(client, nic, "10.11.0.5")
    assert ok.status_code == 201, ok.text
    assert ok.json()["ip_address"] == "10.11.0.5"

    norm = _manual(client, nic, "010.011.000.006")
    assert norm.status_code == 201, norm.text
    assert norm.json()["ip_address"] == "10.11.0.6"

    bad = _manual(client, nic, "abc")
    assert bad.status_code == 400
    assert bad.json()["error"]["details"][0]["code"] == "INVALID"

    extra = client.post(
        MANUAL,
        json={
            "network_interface_id": nic,
            "ip_address": "10.11.0.7",
            "ip_address_range_id": 1,
        },
    )
    assert extra.status_code == 400

    out = _manual(client, nic, "10.11.9.9")
    assert out.status_code == 409
    assert out.json()["error"]["details"][0]["code"] == "OUT_OF_RANGE"


# --------------------------------------------------------------------------- #
# AC-16：F005 登记端点对范围外字面仍 201
# --------------------------------------------------------------------------- #
def test_t23_ac16_f005_out_of_range_literal(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cid = _create_cluster(client, "ac16")
    nic = _create_nic(client, _create_bm(client, cid))
    _create_range(client, cid, "10.12.0.1", "10.12.0.10")

    resp = client.post(
        "/api/ip-addresses",
        json={"network_interface_id": nic, "ip_address": "203.0.113.9/32"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ip_address"] == "203.0.113.9/32"


# --------------------------------------------------------------------------- #
# AC-17：真实线程并发（auto vs manual vs F005 同一地址）→ 至多一条 201
# --------------------------------------------------------------------------- #
@contextmanager
def _three_clients(database_url: str):
    from app.config import Settings
    from app.main import create_app

    upgrade_to_head(database_url)
    create_user(database_url, AUTH_USERNAME, AUTH_PASSWORD)
    apps = [create_app(Settings(environment="dev", database_url=database_url)) for _ in range(3)]
    with (
        TestClient(apps[0], raise_server_exceptions=False) as c0,
        TestClient(apps[1], raise_server_exceptions=False) as c1,
        TestClient(apps[2], raise_server_exceptions=False) as c2,
    ):
        for c in (c0, c1, c2):
            login(c)
        yield c0, c1, c2


def test_t23_ac17_auto_manual_f005_race(database_url):
    with _three_clients(database_url) as (c_auto, c_manual, c_f005):
        cid = _create_cluster(c_auto, "ac17")
        nic = _create_nic(c_auto, _create_bm(c_auto, cid))
        # 单地址范围：auto 必然瞄准 10.13.0.1。
        rid = _create_range(c_auto, cid, "10.13.0.1", "10.13.0.1")

        barrier = threading.Barrier(3)
        results: dict[str, object] = {}

        def run_auto():
            barrier.wait()
            r = c_auto.post(AUTO, json={"network_interface_id": nic, "ip_address_range_id": rid})
            results["auto"] = (r.status_code, r.json())

        def run_manual():
            barrier.wait()
            r = c_manual.post(MANUAL, json={"network_interface_id": nic, "ip_address": "10.13.0.1"})
            results["manual"] = (r.status_code, r.json())

        def run_f005():
            barrier.wait()
            r = c_f005.post(
                "/api/ip-addresses",
                json={"network_interface_id": nic, "ip_address": "10.13.0.1"},
            )
            results["f005"] = (r.status_code, r.json())

        threads = [
            threading.Thread(target=run_auto),
            threading.Thread(target=run_manual),
            threading.Thread(target=run_f005),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert all(not t.is_alive() for t in threads)

        statuses = sorted(code for code, _ in results.values())
        assert statuses.count(201) <= 1, results
        assert all(code in (201, 409) for code, _ in results.values()), results
        for code, body in results.values():
            if code == 409:
                assert body["error"]["code"] == "CONFLICT"
                assert body["error"]["details"][0]["code"] in {"DUPLICATE"}, results

        with psycopg.connect(raw_connection_dsn(database_url)) as conn:
            conn.autocommit = True
            n = conn.execute(
                "SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL "
                "AND ip_address = '10.13.0.1'"
            ).fetchone()[0]
            assert n <= 1
            assert find_drift(conn) == []


def test_t23_ac17_repeated_auto_race(database_url):
    # 重复 3 轮 auto vs auto，稳健覆盖「至多一条成功」。
    with _isolated_clients(database_url) as (first, second):
        cid = _create_cluster(first, "ac17r")
        nic = _create_nic(first, _create_bm(first, cid))
        for round_no in range(3):
            octet = 20 + round_no
            rid = _create_range(first, cid, f"10.14.{octet}.1", f"10.14.{octet}.1")
            barrier = threading.Barrier(2)
            results: dict[str, object] = {}

            def worker(key, client, _barrier=barrier, _rid=rid, _results=results):
                _barrier.wait()
                r = client.post(
                    AUTO, json={"network_interface_id": nic, "ip_address_range_id": _rid}
                )
                _results[key] = (r.status_code, r.json())

            threads = [
                threading.Thread(target=worker, args=("a", first)),
                threading.Thread(target=worker, args=("b", second)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
            statuses = sorted(code for code, _ in results.values())
            assert statuses.count(201) <= 1, (round_no, results)
            assert all(code in (201, 409) for code, _ in results.values()), results

        with psycopg.connect(raw_connection_dsn(database_url)) as conn:
            conn.autocommit = True
            assert find_drift(conn) == []


# --------------------------------------------------------------------------- #
# AC-20：结构证伪（绕应用层直连 DB）
# --------------------------------------------------------------------------- #
def test_t23_ac20_no_schema_change(auth_client_and_raw):
    client, conn = auth_client_and_raw
    # 先落一条自动分配，确认结构性断言在真实写入后仍成立。
    cid = _create_cluster(client, "ac20")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.15.0.1", "10.15.0.5")
    assert _auto(client, nic, rid).status_code == 201

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE'"
        ).fetchall()
    }
    assert tables == EXPECTED_TABLES

    cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='ip_addresses'"
        ).fetchall()
    }
    assert cols == IP_ADDRESS_COLUMNS

    rcols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ip_address_ranges'"
        ).fetchall()
    }
    assert rcols == IP_ADDRESS_RANGE_COLUMNS

    # ip_addresses 上的非主键唯一索引恰为 R-IP-001 partial unique。
    uniq = {
        r[0]
        for r in conn.execute(
            "SELECT c.relname FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "WHERE t.relname='ip_addresses' AND i.indisunique AND NOT i.indisprimary"
        ).fetchall()
    }
    assert uniq == {"ux_ip_addresses_cluster_ip_active"}

    # 排他约束集合不变（仅 F020 既有的 ip_address_ranges 重叠约束）。
    excl = {
        r[0]
        for r in conn.execute("SELECT conname FROM pg_constraint WHERE contype='x'").fetchall()
    }
    assert excl == {"ex_ip_address_ranges_active_no_overlap"}

    # 无触发器。
    triggers = conn.execute(
        "SELECT count(*) FROM information_schema.triggers WHERE trigger_schema='public'"
    ).fetchone()[0]
    assert triggers == 0

    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == MIGRATION_HEAD
    assert find_drift(conn) == []


def test_t23_ac20_sqlstate_map_keys_unchanged():
    # F023 不新增 SQLSTATE 映射键。
    from app.common import sqlstate

    # 基线（F022 / dd159f3）键集合；F023 不新增。
    expected = {"23502", "23514", "23505", "23503", "23P01"}
    assert set(sqlstate.SQLSTATE_MAP.keys()) == expected


def test_t23_readonly_rejection_no_side_effects(auth_client_and_raw):
    # 只读语义：全部拒绝路径不得产生业务写入 / 变更既有行。
    client, conn = auth_client_and_raw
    cid = _create_cluster(client, "t23ro")
    nic = _create_nic(client, _create_bm(client, cid))
    rid = _create_range(client, cid, "10.16.0.1", "10.16.0.2")
    _create_ip(client, nic, "10.16.0.1")
    _create_ip(client, nic, "10.16.0.2")
    before = conn.execute(
        "SELECT id, ip_address, updated_at, deleted_at FROM ip_addresses ORDER BY id"
    ).fetchall()
    # 耗尽路径
    resp = _auto(client, nic, rid)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"][0]["code"] == "NO_AVAILABLE_IP"
    after = conn.execute(
        "SELECT id, ip_address, updated_at, deleted_at FROM ip_addresses ORDER BY id"
    ).fetchall()
    assert before == after
    assert _active_ip_count(conn) == 2
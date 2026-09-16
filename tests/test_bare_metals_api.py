"""F002 BareMetal API 行为测试（T-01 ~ T-21、T-23、T-24、T-28、T-29）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

import pytest

# 请求 / 响应 / 表结构中禁止出现的位置 / 上级字段（AC-28）。
POSITION_FIELDS = {
    "data_center",
    "datacenter",
    "location",
    "room",
    "rack",
    "u_position",
    "u_position_start",
    "u_position_end",
    "site",
    "campus",
}

READ_FIELDS = {
    "id",
    "cluster_id",
    "hostname",
    "status",
    "vendor",
    "model",
    "serial_number",
    "cpu",
    "memory",
    "gpu",
    "storage",
    "created_at",
    "updated_at",
}

HARDWARE_FIELDS = ("vendor", "model", "serial_number", "cpu", "memory", "gpu", "storage")


def _create_cluster(client, name: str) -> int:
    response = client.post("/api/clusters", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _raw_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[
        0
    ]


def _bm_payload(cluster_id: int, hostname: str, **extra) -> dict:
    return {"cluster_id": cluster_id, "hostname": hostname, **extra}


def _active_bm_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM bare_metals WHERE deleted_at IS NULL").fetchone()[0]


def _total_bm_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM bare_metals").fetchone()[0]


# --------------------------------------------------------------------------- #
# T-01 / AC-01：登记成功，响应字段集合恰为 13 字段
# --------------------------------------------------------------------------- #
def test_t01_create_returns_closed_field_set(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "cn001"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert "deleted_at" not in body
    assert not (POSITION_FIELDS & set(body))
    assert body["cluster_id"] == cluster_id
    assert body["hostname"] == "cn001"
    assert body["status"] == "IDLE"
    assert _active_bm_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-01b / AC-01 / 契约 §3.1：POST 请求 schema 封闭，未识别字段 → 400，无写入
# --------------------------------------------------------------------------- #
def test_t01b_unknown_create_field_is_rejected(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "cn001", rack="R01"))

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "rack" for detail in body["error"]["details"])
    assert _total_bm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-02 / AC-02：hostname 必填 / 非字符串 → 400，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hostname", ["MISSING", 123, None])
def test_t02_invalid_hostname_returns_400_without_write(auth_client_and_raw, hostname):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    payload = {"cluster_id": cluster_id}
    if hostname != "MISSING":
        payload["hostname"] = hostname

    response = client.post("/api/bare-metals", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "hostname" for detail in body["error"]["details"])
    assert _total_bm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-03 / AC-03 / NQ-2：cluster_id 必填 / 非整数 → 400；引用不存在 / 已删 → 404
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cluster_value", ["MISSING", "abc", None, 1.5])
def test_t03_invalid_cluster_id_type_returns_400(auth_client_and_raw, cluster_value):
    client, conn = auth_client_and_raw
    payload = {"hostname": "cn001"}
    if cluster_value != "MISSING":
        payload["cluster_id"] = cluster_value

    response = client.post("/api/bare-metals", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "cluster_id" for detail in body["error"]["details"])
    assert _total_bm_rows(conn) == 0


def test_t03_missing_or_deleted_cluster_returns_404_without_write(auth_client_and_raw):
    client, conn = auth_client_and_raw

    missing = client.post("/api/bare-metals", json=_bm_payload(999999, "cn001"))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []

    gone_id = _raw_cluster(conn, "gone", deleted=True)
    deleted = client.post("/api/bare-metals", json=_bm_payload(gone_id, "cn002"))
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "NOT_FOUND"

    # 不产生写入、非 5xx
    assert _total_bm_rows(conn) == 0


# --------------------------------------------------------------------------- #
# T-04 / AC-04：同 Cluster 活跃 hostname 重复 → 409 + 稳定 code
# --------------------------------------------------------------------------- #
def test_t04_duplicate_active_hostname_returns_409(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).status_code == 201

    response = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    detail = next(d for d in body["error"]["details"] if d["field"] == "hostname")
    assert detail["code"] == "DUPLICATE"
    assert _active_bm_count(conn) == 1


# --------------------------------------------------------------------------- #
# T-05 / AC-05：跨 Cluster 可重名
# --------------------------------------------------------------------------- #
def test_t05_cross_cluster_duplicate_hostname_allowed(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")

    first = client.post("/api/bare-metals", json=_bm_payload(cluster_a, "n1"))
    second = client.post("/api/bare-metals", json=_bm_payload(cluster_b, "n1"))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


# --------------------------------------------------------------------------- #
# T-06 / AC-06：大小写敏感
# --------------------------------------------------------------------------- #
def test_t06_case_sensitive_hostnames_coexist(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    assert client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).status_code == 201
    assert client.post("/api/bare-metals", json=_bm_payload(cluster_id, "N1")).status_code == 201

    listed = client.get("/api/bare-metals", params={"cluster_id": cluster_id}).json()
    hostnames = sorted(item["hostname"] for item in listed["items"])
    assert hostnames == ["N1", "n1"]
    assert _active_bm_count(conn) == 2


# --------------------------------------------------------------------------- #
# T-07 / AC-07：默认 IDLE；显式合法状态被接受（NQ-3 PROPOSED 7）
# --------------------------------------------------------------------------- #
def test_t07_default_status_and_explicit_status(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    default = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))
    assert default.status_code == 201
    assert default.json()["status"] == "IDLE"

    explicit = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n2", status="DOWN"))
    assert explicit.status_code == 201
    assert explicit.json()["status"] == "DOWN"

    db_status = conn.execute(
        "SELECT status FROM bare_metals WHERE hostname = 'n1' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert db_status == "IDLE"


# --------------------------------------------------------------------------- #
# T-08 / AC-08：硬件字段缺省返回 null 而非省略
# --------------------------------------------------------------------------- #
def test_t08_missing_hardware_fields_return_null(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))

    assert response.status_code == 201
    body = response.json()
    for field in HARDWARE_FIELDS:
        assert field in body, f"{field} 必须返回 null 而非省略"
        assert body[field] is None


# --------------------------------------------------------------------------- #
# T-09 / AC-09：中文 hostname 往返
# --------------------------------------------------------------------------- #
def test_t09_chinese_hostname_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    hostname = "计算节点-甲"

    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, hostname))
    assert created.status_code == 201
    assert created.json()["hostname"] == hostname

    listed = client.get("/api/bare-metals", params={"cluster_id": cluster_id}).json()
    assert [item["hostname"] for item in listed["items"]] == [hostname]

    detail = client.get(f"/api/bare-metals/{created.json()['id']}")
    assert detail.json()["hostname"] == hostname


# --------------------------------------------------------------------------- #
# T-10 / AC-10：状态封闭集合（创建与 PATCH 两路径），不写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_status", ["RUNNING", "idle", "", None])
def test_t10_invalid_status_on_create_returns_400(auth_client_and_raw, bad_status):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    response = client.post(
        "/api/bare-metals", json=_bm_payload(cluster_id, "n1", status=bad_status)
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "status" for detail in body["error"]["details"])
    assert _total_bm_rows(conn) == 0


@pytest.mark.parametrize("bad_status", ["RUNNING", "idle", "", None])
def test_t10_invalid_status_on_patch_returns_400(auth_client_and_raw, bad_status):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()

    response = client.patch(f"/api/bare-metals/{created['id']}", json={"status": bad_status})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "status" for detail in body["error"]["details"])
    assert client.get(f"/api/bare-metals/{created['id']}").json()["status"] == "IDLE"


# --------------------------------------------------------------------------- #
# T-12 / AC-12：人工维护状态
# --------------------------------------------------------------------------- #
def test_t12_patch_status_is_persisted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()

    patched = client.patch(f"/api/bare-metals/{created['id']}", json={"status": "ALLOC"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "ALLOC"
    assert patched.json()["id"] == created["id"]
    assert patched.json()["created_at"] == created["created_at"]

    assert client.get(f"/api/bare-metals/{created['id']}").json()["status"] == "ALLOC"
    listed = client.get("/api/bare-metals").json()
    assert listed["items"][0]["status"] == "ALLOC"


def test_t12_patch_hardware_fields_and_clear(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post(
        "/api/bare-metals",
        json=_bm_payload(cluster_id, "n1", vendor="Dell", gpu="4 x A100"),
    ).json()
    assert created["vendor"] == "Dell"

    patched = client.patch(
        f"/api/bare-metals/{created['id']}", json={"gpu": None, "cpu": "2 x Xeon"}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["gpu"] is None
    assert body["cpu"] == "2 x Xeon"
    assert body["vendor"] == "Dell", "未提供的字段保持不变"


def test_t12_patch_empty_body_and_immutable_fields_return_400(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()

    empty = client.patch(f"/api/bare-metals/{created['id']}", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"

    for field, value in (("hostname", "x"), ("cluster_id", 1), ("deleted_at", None)):
        forbidden = client.patch(f"/api/bare-metals/{created['id']}", json={field: value})
        assert forbidden.status_code == 400, field
        assert any(detail["field"] == field for detail in forbidden.json()["error"]["details"]), (
            field
        )


def test_t12_patch_missing_or_deleted_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    assert client.patch("/api/bare-metals/999999", json={"status": "DOWN"}).status_code == 404

    cluster_id = _create_cluster(client, "cluster-a")
    conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) VALUES (%s, 'gone', now())",
        (cluster_id,),
    )
    gone_id = conn.execute("SELECT id FROM bare_metals WHERE hostname = 'gone'").fetchone()[0]
    response = client.patch(f"/api/bare-metals/{gone_id}", json={"status": "DOWN"})
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# T-13 / AC-13：列表、分页、Empty
# --------------------------------------------------------------------------- #
def test_t13_empty_list_is_200_empty_items(auth_client_and_raw):
    client, _ = auth_client_and_raw
    response = client.get("/api/bare-metals")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_t13_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    for index in range(3):
        assert (
            client.post("/api/bare-metals", json=_bm_payload(cluster_id, f"n{index}")).status_code
            == 201
        )

    first = client.get("/api/bare-metals", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["hostname"] for item in first["items"]] == ["n0", "n1"]

    second = client.get("/api/bare-metals", params={"page_size": 2, "page": 2}).json()
    assert [item["hostname"] for item in second["items"]] == ["n2"]


# --------------------------------------------------------------------------- #
# T-14 / AC-14：详情 Not Found（不区分不存在 / 已删）
# --------------------------------------------------------------------------- #
def test_t14_detail_not_found(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    assert client.get("/api/bare-metals/999999").status_code == 404

    conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) VALUES (%s, 'ghost', now())",
        (cluster_id,),
    )
    ghost_id = conn.execute("SELECT id FROM bare_metals WHERE hostname = 'ghost'").fetchone()[0]
    response = client.get(f"/api/bare-metals/{ghost_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-15 / AC-15：按 Cluster 限定读取；Empty 与 Not Found 可区分
# --------------------------------------------------------------------------- #
def test_t15_list_by_cluster_semantics(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")

    # Cluster 不存在 → 404
    missing = client.get("/api/bare-metals", params={"cluster_id": 999999})
    assert missing.status_code == 404

    # Cluster 已删 → 404
    gone_id = _raw_cluster(conn, "gone", deleted=True)
    deleted = client.get("/api/bare-metals", params={"cluster_id": gone_id})
    assert deleted.status_code == 404

    # Cluster 存在但无活跃 BareMetal → 200 空集
    empty = client.get("/api/bare-metals", params={"cluster_id": cluster_a})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0

    # 只返回该 Cluster 的活跃子集
    client.post("/api/bare-metals", json=_bm_payload(cluster_a, "a1"))
    client.post("/api/bare-metals", json=_bm_payload(cluster_b, "b1"))
    only_a = client.get("/api/bare-metals", params={"cluster_id": cluster_a}).json()
    assert [item["hostname"] for item in only_a["items"]] == ["a1"]
    assert only_a["total"] == 1


@pytest.mark.parametrize("cluster_id", ["abc", 0.5])
def test_t15_non_integer_cluster_query_returns_400(auth_client_and_raw, cluster_id):
    client, _ = auth_client_and_raw
    response = client.get("/api/bare-metals", params={"cluster_id": cluster_id})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "cluster_id" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# T-16 / AC-16：R-CLUSTER-004 的 N:1 方向
# --------------------------------------------------------------------------- #
def test_t16_multiple_bare_metals_per_cluster(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    first = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))
    second = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n2"))
    assert first.status_code == 201
    assert second.status_code == 201

    listed = client.get("/api/bare-metals", params={"cluster_id": cluster_id}).json()
    assert listed["total"] == 2
    assert {item["cluster_id"] for item in listed["items"]} == {cluster_id}
    assert len({item["id"] for item in listed["items"]}) == 2


# --------------------------------------------------------------------------- #
# T-17 / AC-17：绕过应用层预置软删行 → 排除；按 id → 404
# --------------------------------------------------------------------------- #
def test_t17_soft_deleted_row_excluded_from_reads(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) VALUES (%s, 'ghost', now())",
        (cluster_id,),
    )
    ghost_id = conn.execute("SELECT id FROM bare_metals WHERE hostname = 'ghost'").fetchone()[0]

    listed = client.get("/api/bare-metals").json()
    assert listed["total"] == 0
    assert [item["id"] for item in listed["items"]] == []

    by_cluster = client.get("/api/bare-metals", params={"cluster_id": cluster_id}).json()
    assert by_cluster["total"] == 0

    assert client.get(f"/api/bare-metals/{ghost_id}").status_code == 404


# --------------------------------------------------------------------------- #
# T-18 / AC-18：逻辑删除（204 无响应体；行仍物理存在）
# --------------------------------------------------------------------------- #
def test_t18_delete_returns_204_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    rows_before = _total_bm_rows(conn)

    response = client.delete(f"/api/bare-metals/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert _total_bm_rows(conn) == rows_before
    row = conn.execute(
        "SELECT deleted_at FROM bare_metals WHERE id = %s", (created["id"],)
    ).fetchone()
    assert row is not None, "逻辑删除不得物理删除行"
    assert row[0] is not None

    assert client.get("/api/bare-metals").json()["total"] == 0
    assert client.get(f"/api/bare-metals/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# T-19 / AC-19：已删释放唯一性；旧行 deleted_at 不被改写
# --------------------------------------------------------------------------- #
def test_t19_delete_releases_hostname_and_preserves_old_row(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    assert client.delete(f"/api/bare-metals/{created['id']}").status_code == 204
    deleted_at_after = conn.execute(
        "SELECT deleted_at FROM bare_metals WHERE id = %s", (created["id"],)
    ).fetchone()[0]

    recreated = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))
    assert recreated.status_code == 201
    assert recreated.json()["id"] != created["id"]

    total = conn.execute(
        "SELECT count(*) FROM bare_metals WHERE cluster_id = %s AND hostname = 'n1'",
        (cluster_id,),
    ).fetchone()[0]
    assert total == 2
    assert (
        conn.execute(
            "SELECT deleted_at FROM bare_metals WHERE id = %s", (created["id"],)
        ).fetchone()[0]
        == deleted_at_after
    )


# --------------------------------------------------------------------------- #
# T-20 / AC-20：删除不级联
# --------------------------------------------------------------------------- #
def test_t20_delete_does_not_cascade(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    other = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "keep")).json()
    target = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "gone")).json()

    cluster_before = conn.execute(
        "SELECT name, created_at, updated_at, deleted_at FROM clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()
    other_before = conn.execute(
        "SELECT hostname, status, deleted_at FROM bare_metals WHERE id = %s", (other["id"],)
    ).fetchone()
    rows_before = _total_bm_rows(conn)

    assert client.delete(f"/api/bare-metals/{target['id']}").status_code == 204

    assert (
        conn.execute(
            "SELECT name, created_at, updated_at, deleted_at FROM clusters WHERE id = %s",
            (cluster_id,),
        ).fetchone()
        == cluster_before
    )
    assert (
        conn.execute(
            "SELECT hostname, status, deleted_at FROM bare_metals WHERE id = %s", (other["id"],)
        ).fetchone()
        == other_before
    )
    assert _total_bm_rows(conn) == rows_before


# --------------------------------------------------------------------------- #
# T-21 / AC-21：无恢复 / 批量 / include_deleted / by-name
# --------------------------------------------------------------------------- #
def test_t21_no_out_of_scope_routes_or_params(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]

    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "deleted", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/bare-metals")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name 端点：{offenders}"

    list_op = paths["/api/bare-metals"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)

    # DELETE 已删行 → 404
    cluster_id = _create_cluster(client, "cluster-a")
    created = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    assert client.delete(f"/api/bare-metals/{created['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# T-23 / AC-23 / R-DELETE-004：Cluster 有活跃 BareMetal → 拒绝删除
# --------------------------------------------------------------------------- #
def test_t23_cluster_with_active_bare_metal_cannot_be_deleted(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    assert client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).status_code == 201

    response = client.delete(f"/api/clusters/{cluster_id}")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in body["error"]["details"])
    # 无部分写入
    assert (
        conn.execute("SELECT deleted_at FROM clusters WHERE id = %s", (cluster_id,)).fetchone()[0]
        is None
    )


# --------------------------------------------------------------------------- #
# T-24 / AC-24：软删全部 BareMetal 后 Cluster 可删
# --------------------------------------------------------------------------- #
def test_t24_cluster_deletable_after_children_soft_deleted(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    first = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    second = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n2")).json()

    assert client.delete(f"/api/bare-metals/{first['id']}").status_code == 204
    assert client.delete(f"/api/bare-metals/{second['id']}").status_code == 204

    response = client.delete(f"/api/clusters/{cluster_id}")
    assert response.status_code == 204


# --------------------------------------------------------------------------- #
# T-28 / AC-28：无位置 / 上级 / 自动发现结构
# --------------------------------------------------------------------------- #
def test_t28_no_position_or_auto_discovery_structure(auth_client_and_raw):
    client, conn = auth_client_and_raw
    from app.db.base import Base

    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='bare_metals'"
        ).fetchall()
    }
    assert not (POSITION_FIELDS & db_columns)
    assert not (POSITION_FIELDS & set(Base.metadata.tables["bare_metals"].columns.keys()))

    cluster_id = _create_cluster(client, "cluster-a")
    body = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    assert not (POSITION_FIELDS & set(body))

    for path in client.app.openapi()["paths"]:
        if path.startswith("/api/bare-metals"):
            assert not any(token in path.lower() for token in POSITION_FIELDS)


# --------------------------------------------------------------------------- #
# T-29 / AC-29：不越界其它资源
# --------------------------------------------------------------------------- #
def test_t29_no_other_resource_endpoints_or_columns(auth_client_and_raw):
    client, conn = auth_client_and_raw
    paths = set(client.app.openapi()["paths"])
    # F006 演进：VirtualMachine 已成为合法资源（``/api/virtual-machines``），从越界
    # prefix 中移除 ``vm`` / ``virtual``。
    # F004 演进：NetworkInterface 已成为合法资源（``/api/network-interfaces``），从
    # 越界 prefix 中移除 ``nic`` / ``network-interface`` / ``network_interface``；
    # ``ip`` / ``container`` / ``service`` 必须保持全局覆盖。
    forbidden_prefixes = (
        "ip",
        "container",
        "service",
    )
    offenders = [
        path
        for path in paths
        if path.startswith("/api/")
        and any(path[len("/api/") :].startswith(prefix) for prefix in forbidden_prefixes)
    ]
    assert offenders == [], f"F002 不得注册其它资源端点：{offenders}"

    columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='bare_metals'"
        ).fetchall()
    }
    assert not any(
        token in column for column in columns for token in ("nic", "vm", "container", "service")
    )

    # 不提供 Cluster 视角专用别名
    assert "/api/bare-metals/by-name/{hostname}" not in paths

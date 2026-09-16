"""F009 Cluster 视角资源查询 API 行为测试（T-01 ~ T-17）。

两条路径分别 / 组合验证：

- **canonical**：``GET /api/bare-metals?cluster_id={id}``（F002 §3.2）。
- **alias**：``GET /api/clusters/by-name/{cluster_name}/bare-metals``（F009 §3）。

数据库夹具 ``auth_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于预置软删行与断言数据库侧状态。
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

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

VALID_STATUSES = {"IDLE", "ALLOC", "DOWN", "UNKNOWN"}


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


def _alias_path(cluster_name: str) -> str:
    return f"/api/clusters/by-name/{quote(cluster_name, safe='')}/bare-metals"


def _canonical(client, cluster_id: int, **params):
    return client.get("/api/bare-metals", params={"cluster_id": cluster_id, **params})


# --------------------------------------------------------------------------- #
# T-01 / AC-01、AC-02：alias 与 canonical 均返回该 Cluster 的 2 台，逐字段一致
# --------------------------------------------------------------------------- #
def test_t01_alias_matches_canonical_envelope(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    ids = [
        client.post("/api/bare-metals", json=_bm_payload(cluster_id, hostname)).json()["id"]
        for hostname in ("n1", "n2")
    ]

    alias = client.get(_alias_path("cluster-a"))
    canonical = _canonical(client, cluster_id)

    assert alias.status_code == 200
    assert canonical.status_code == 200
    assert alias.json() == canonical.json()

    body = alias.json()
    assert [item["id"] for item in body["items"]] == sorted(ids)
    assert body["total"] == 2
    # F002 §3.2 信封形状与字段集合逐字段一致
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page"] == 1
    assert body["page_size"] == 50
    for item in body["items"]:
        assert set(item) == READ_FIELDS


# --------------------------------------------------------------------------- #
# T-02 / AC-02：每条含 hostname 与 status，status 属封闭集合且非空
# --------------------------------------------------------------------------- #
def test_t02_hostname_and_status_present(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1"))
    client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n2", status="DOWN"))

    body = client.get(_alias_path("cluster-a")).json()
    assert len(body["items"]) == 2
    for item in body["items"]:
        assert isinstance(item["hostname"], str) and item["hostname"]
        assert item["status"] is not None
        assert item["status"] in VALID_STATUSES


# --------------------------------------------------------------------------- #
# T-03 / AC-03：只含本 Cluster 的机器
# --------------------------------------------------------------------------- #
def test_t03_only_own_cluster_members(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_a = _create_cluster(client, "cluster-a")
    cluster_b = _create_cluster(client, "cluster-b")
    client.post("/api/bare-metals", json=_bm_payload(cluster_a, "a1"))
    client.post("/api/bare-metals", json=_bm_payload(cluster_b, "b1"))

    only_a = client.get(_alias_path("cluster-a")).json()
    only_b = client.get(_alias_path("cluster-b")).json()

    assert [item["hostname"] for item in only_a["items"]] == ["a1"]
    assert [item["hostname"] for item in only_b["items"]] == ["b1"]
    assert {item["cluster_id"] for item in only_a["items"]} == {cluster_a}


# --------------------------------------------------------------------------- #
# T-04 / AC-04：PATCH 状态后重新查询反映最新事实
# --------------------------------------------------------------------------- #
def test_t04_status_update_is_visible(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    target = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n1")).json()
    other = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "n2")).json()

    patched = client.patch(f"/api/bare-metals/{target['id']}", json={"status": "DOWN"})
    assert patched.status_code == 200

    items = {
        item["id"]: item["status"] for item in client.get(_alias_path("cluster-a")).json()["items"]
    }
    assert items[target["id"]] == "DOWN"
    assert items[other["id"]] == "IDLE"


# --------------------------------------------------------------------------- #
# T-05 / AC-05：中文 Cluster 名称与 hostname 百分号编码往返
# --------------------------------------------------------------------------- #
def test_t05_chinese_name_and_hostname_roundtrip(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_name = "高性能计算集群-A"
    hostname = "计算节点-甲"
    cluster_id = _create_cluster(client, cluster_name)
    client.post("/api/bare-metals", json=_bm_payload(cluster_id, hostname))

    response = client.get(_alias_path(cluster_name))
    assert response.status_code == 200
    assert [item["hostname"] for item in response.json()["items"]] == [hostname]


# --------------------------------------------------------------------------- #
# T-06 / AC-06：Cluster 不存在 → alias 与 canonical 均 404（不得 200 空集）
# --------------------------------------------------------------------------- #
def test_t06_missing_cluster_returns_404(auth_client_and_raw):
    client, _ = auth_client_and_raw

    alias = client.get(_alias_path("does-not-exist"))
    assert alias.status_code == 404
    assert alias.json()["error"]["code"] == "NOT_FOUND"
    assert alias.json()["error"]["details"] == []
    assert "items" not in alias.text

    canonical = client.get("/api/bare-metals", params={"cluster_id": 999999})
    assert canonical.status_code == 404
    assert canonical.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-07 / AC-07：已软删 Cluster（绕过应用层）→ alias 与 canonical 均 404
# --------------------------------------------------------------------------- #
def test_t07_soft_deleted_cluster_returns_404(auth_client_and_raw):
    client, conn = auth_client_and_raw
    gone_id = _raw_cluster(conn, "gone", deleted=True)

    alias = client.get(_alias_path("gone"))
    assert alias.status_code == 404
    assert alias.json()["error"]["code"] == "NOT_FOUND"

    canonical = client.get("/api/bare-metals", params={"cluster_id": gone_id})
    assert canonical.status_code == 404
    assert canonical.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# T-08 / AC-08：Cluster 存在且活跃但无活跃 BareMetal → 200 Empty
# --------------------------------------------------------------------------- #
def test_t08_active_cluster_without_members_is_empty(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")

    alias = client.get(_alias_path("cluster-a"))
    canonical = _canonical(client, cluster_id)

    for response in (alias, canonical):
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0


# --------------------------------------------------------------------------- #
# T-09 / AC-08、AC-10：alias 200 空集不是错误
# --------------------------------------------------------------------------- #
def test_t09_empty_is_not_an_error(auth_client_and_raw):
    client, _ = auth_client_and_raw
    _create_cluster(client, "cluster-a")

    response = client.get(_alias_path("cluster-a"))
    assert response.status_code == 200
    body = response.json()
    assert "error" not in body
    assert body["items"] == []


# --------------------------------------------------------------------------- #
# T-10 / AC-05、§22：alias 大小写敏感
# --------------------------------------------------------------------------- #
def test_t10_alias_is_case_sensitive(auth_client_and_raw):
    client, _ = auth_client_and_raw
    lower = _create_cluster(client, "cluster-a")
    upper = _create_cluster(client, "Cluster-A")
    client.post("/api/bare-metals", json=_bm_payload(lower, "lower-node"))
    client.post("/api/bare-metals", json=_bm_payload(upper, "upper-node"))

    hit_upper = client.get(_alias_path("Cluster-A"))
    assert hit_upper.status_code == 200
    assert [item["hostname"] for item in hit_upper.json()["items"]] == ["upper-node"]

    # 命中结果与 canonical 对 Cluster-A 的 id 结果深等
    assert hit_upper.json() == _canonical(client, upper).json()


# --------------------------------------------------------------------------- #
# T-11 / AC-11：已软删 BareMetal（绕过应用层）不出现
# --------------------------------------------------------------------------- #
def test_t11_soft_deleted_bare_metal_excluded(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    active = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "keep")).json()
    conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname, deleted_at) VALUES (%s, 'ghost', now())",
        (cluster_id,),
    )

    alias = client.get(_alias_path("cluster-a"))
    canonical = _canonical(client, cluster_id)

    for response in (alias, canonical):
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert [item["id"] for item in response.json()["items"]] == [active["id"]]


# --------------------------------------------------------------------------- #
# T-12 / AC-12：DELETE 后从视图消失；其余与 Cluster 不变
# --------------------------------------------------------------------------- #
def test_t12_deleted_bare_metal_disappears(auth_client_and_raw):
    client, conn = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    doomed = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "doomed")).json()
    keeper = client.post("/api/bare-metals", json=_bm_payload(cluster_id, "keeper")).json()
    cluster_before = conn.execute(
        "SELECT name, created_at, updated_at, deleted_at FROM clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()

    assert client.delete(f"/api/bare-metals/{doomed['id']}").status_code == 204

    body = client.get(_alias_path("cluster-a")).json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [keeper["id"]]
    assert (
        conn.execute(
            "SELECT name, created_at, updated_at, deleted_at FROM clusters WHERE id = %s",
            (cluster_id,),
        ).fetchone()
        == cluster_before
    )


# --------------------------------------------------------------------------- #
# T-13 / AC-13：无 include_deleted / restore / undelete / 回收站 入口或参数
# --------------------------------------------------------------------------- #
def test_t13_no_restore_or_include_deleted_surface(auth_client_and_raw):
    client, _ = auth_client_and_raw
    paths = client.app.openapi()["paths"]

    forbidden_tokens = ("restore", "undelete", "purge", "trash", "include_deleted", "deleted")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/clusters")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"Cluster 视角不得有恢复 / 已删入口：{offenders}"

    alias_op = paths["/api/clusters/by-name/{cluster_name}/bare-metals"]["get"]
    param_names = {p.get("name") for p in alias_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# T-14 / AC-16：未认证 → 401 UNAUTHENTICATED，且不返回资源数据
# --------------------------------------------------------------------------- #
def test_t14_unauthenticated_returns_401(app_client):
    response = app_client.get(_alias_path("cluster-a"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "items" not in response.text


# --------------------------------------------------------------------------- #
# T-15 / 契约 §5：非法 page / page_size → 400 VALIDATION_ERROR + details[].field
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "page"),
        ({"page": "x"}, "page"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 201}, "page_size"),
        ({"page_size": "x"}, "page_size"),
    ],
)
def test_t15_invalid_pagination_returns_400(auth_client_and_raw, params, field):
    client, _ = auth_client_and_raw
    _create_cluster(client, "cluster-a")

    response = client.get(_alias_path("cluster-a"), params=params)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == field for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# T-16 / 契约 §3：分页正确（total 为该 Cluster 活跃总数，page / page_size 回显）
# --------------------------------------------------------------------------- #
def test_t16_pagination(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    for index in range(3):
        client.post("/api/bare-metals", json=_bm_payload(cluster_id, f"n{index}"))
    # 另一 Cluster 的成员不得计入 total
    other = _create_cluster(client, "cluster-b")
    client.post("/api/bare-metals", json=_bm_payload(other, "other"))

    first = client.get(_alias_path("cluster-a"), params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert [item["hostname"] for item in first["items"]] == ["n0", "n1"]

    second = client.get(_alias_path("cluster-a"), params={"page_size": 2, "page": 2}).json()
    assert second["total"] == 3
    assert second["page"] == 2
    assert second["page_size"] == 2
    assert [item["hostname"] for item in second["items"]] == ["n2"]


# --------------------------------------------------------------------------- #
# T-17 / 契约 §2：alias 命中结果与 canonical 对同一 Cluster 深等
# --------------------------------------------------------------------------- #
def test_t17_alias_deep_equals_canonical(auth_client_and_raw):
    client, _ = auth_client_and_raw
    cluster_id = _create_cluster(client, "cluster-a")
    for hostname, status in (("n1", None), ("n2", "ALLOC"), ("n3", "UNKNOWN")):
        extra = {} if status is None else {"status": status}
        client.post("/api/bare-metals", json=_bm_payload(cluster_id, hostname, **extra))

    alias = client.get(_alias_path("cluster-a"), params={"page": 1, "page_size": 2})
    canonical = _canonical(client, cluster_id, page=1, page_size=2)
    assert alias.status_code == canonical.status_code == 200
    assert alias.json() == canonical.json()

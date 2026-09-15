"""F001 Cluster API 行为测试（A01 ~ A13、A15 运行时、G3、T9′）。

数据库夹具 ``app_client_and_raw`` 同时提供产品客户端与**绕过应用层**的原始
psycopg 连接，用于断言数据库侧状态与预置软删行。
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from app.clusters.schemas import ClusterCreate, ClusterRead, ClusterUpdate

# 请求 / 响应中禁止出现的位置 / 上级字段（AC-10）。
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
STATUS_FIELDS = {"status", "state"}


def _active_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM clusters WHERE deleted_at IS NULL").fetchone()[0]


def _total_rows(conn) -> int:
    return conn.execute("SELECT count(*) FROM clusters").fetchone()[0]


# --------------------------------------------------------------------------- #
# A01 / AC-01：登记成功，响应字段集合封闭
# --------------------------------------------------------------------------- #
def test_a01_create_returns_closed_field_set(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.post("/api/clusters", json={"name": "cluster-a"})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "created_at", "updated_at"}
    assert "deleted_at" not in body
    assert body["name"] == "cluster-a"
    assert isinstance(body["id"], int)
    assert _active_count(conn) == 1


# --------------------------------------------------------------------------- #
# A02 / AC-02：name 必填且为字符串，无写入
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("payload", [{}, {"name": 123}, {"name": None}])
def test_a02_invalid_name_returns_400_without_write(app_client_and_raw, payload):
    client, conn = app_client_and_raw
    response = client.post("/api/clusters", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _total_rows(conn) == 0


# --------------------------------------------------------------------------- #
# A03 / AC-03 / Q10：/ 禁令在应用层先于数据库，永不 500，无写入
# --------------------------------------------------------------------------- #
def test_a03_slash_in_name_post_returns_400_not_500(app_client_and_raw):
    client, conn = app_client_and_raw
    response = client.post("/api/clusters", json={"name": "a/b"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    detail = next(d for d in body["error"]["details"] if d["field"] == "name")
    assert detail["code"] == "INVALID_CHARACTER"
    assert _total_rows(conn) == 0


def test_a03_slash_in_name_patch_returns_400(app_client_and_raw):
    client, conn = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"})
    cluster_id = created.json()["id"]

    response = client.patch(f"/api/clusters/{cluster_id}", json={"name": "x/y"})
    assert response.status_code == 400
    body = response.json()
    detail = next(d for d in body["error"]["details"] if d["field"] == "name")
    assert detail["code"] == "INVALID_CHARACTER"
    # 未发生写入
    assert (
        conn.execute("SELECT name FROM clusters WHERE id = %s", (cluster_id,)).fetchone()[0]
        == "cluster-a"
    )


# --------------------------------------------------------------------------- #
# A04 / AC-04 / Q6：绕过应用层预检后，数据库唯一索引仍是最终权威
# --------------------------------------------------------------------------- #
def test_a04_db_index_is_authoritative_when_precheck_bypassed(app_client_and_raw, monkeypatch):
    client, conn = app_client_and_raw
    assert client.post("/api/clusters", json={"name": "dup"}).status_code == 201

    import app.clusters.validation as validation

    monkeypatch.setattr(validation, "ensure_active_name_available", lambda *a, **k: None)

    response = client.post("/api/clusters", json={"name": "dup"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _active_count(conn) == 1


# --------------------------------------------------------------------------- #
# A05 / AC-04：常规重复活跃名 → 友好 409，活跃行数不变
# --------------------------------------------------------------------------- #
def test_a05_regular_duplicate_returns_409(app_client_and_raw):
    client, conn = app_client_and_raw
    assert client.post("/api/clusters", json={"name": "cluster-a"}).status_code == 201
    response = client.post("/api/clusters", json={"name": "cluster-a"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["field"] == "name" for detail in body["error"]["details"])
    assert _active_count(conn) == 1


# --------------------------------------------------------------------------- #
# A06 / AC-05 / AC-11：大小写敏感
# --------------------------------------------------------------------------- #
def test_a06_case_sensitive_uniqueness_and_lookup(app_client_and_raw):
    client, _ = app_client_and_raw
    assert client.post("/api/clusters", json={"name": "cluster-a"}).status_code == 201
    assert client.post("/api/clusters", json={"name": "Cluster-A"}).status_code == 201

    hit = client.get("/api/clusters/by-name/Cluster-A")
    assert hit.status_code == 200
    assert hit.json()["name"] == "Cluster-A"

    listed = client.get("/api/clusters")
    assert listed.json()["total"] == 2


# --------------------------------------------------------------------------- #
# A07 / AC-06：by-name 命中与 {id} 逐字段一致；未命中 404
# --------------------------------------------------------------------------- #
def test_a07_by_name_matches_get_by_id(app_client_and_raw):
    client, _ = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    by_id = client.get(f"/api/clusters/{created['id']}")
    by_name = client.get("/api/clusters/by-name/cluster-a")
    assert by_id.status_code == 200
    assert by_name.status_code == 200
    assert by_id.json() == by_name.json()

    missing = client.get("/api/clusters/by-name/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []


def test_a07_non_integer_path_param_returns_400(app_client_and_raw):
    """契约 §4.3：`{cluster_id}` 非整数 → 400 VALIDATION_ERROR，不得 500。"""
    client, _ = app_client_and_raw
    response = client.get("/api/clusters/abc")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "cluster_id" for detail in body["error"]["details"])


def test_a07_by_name_alias_resolves_numeric_name(app_client_and_raw):
    """契约 §3.4(5)：纯数字名称走 by-name 可无歧义解析。"""
    client, _ = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "123"}).json()
    hit = client.get("/api/clusters/by-name/123")
    assert hit.status_code == 200
    assert hit.json()["id"] == created["id"]


# --------------------------------------------------------------------------- #
# A08 / AC-07 / R-DELETE-006：已删不参与查询与解析，同名可重新登记
# --------------------------------------------------------------------------- #
def test_a08_soft_deleted_row_excluded_and_name_reusable(app_client_and_raw):
    client, conn = app_client_and_raw
    # 绕过应用层直接置入 deleted_at 非空行
    conn.execute("INSERT INTO clusters (name, deleted_at) VALUES ('ghost', now())")

    listed = client.get("/api/clusters")
    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()["items"]]
    assert "ghost" not in names
    assert listed.json()["total"] == 0

    ghost_id = conn.execute("SELECT id FROM clusters WHERE name = 'ghost'").fetchone()[0]
    assert client.get(f"/api/clusters/{ghost_id}").status_code == 404
    assert client.get("/api/clusters/by-name/ghost").status_code == 404

    # R-DELETE-006：已删不占唯一性 → 同名可重新登记
    recreated = client.post("/api/clusters", json={"name": "ghost"})
    assert recreated.status_code == 201
    assert recreated.json()["id"] != ghost_id


# --------------------------------------------------------------------------- #
# A09 / AC-08：列表、分页、Empty 语义
# --------------------------------------------------------------------------- #
def test_a09_empty_list_is_200_empty_items(app_client_and_raw):
    client, _ = app_client_and_raw
    response = client.get("/api/clusters")
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_a09_pagination(app_client_and_raw):
    client, _ = app_client_and_raw
    for name in ("c1", "c2", "c3"):
        assert client.post("/api/clusters", json={"name": name}).status_code == 201

    first = client.get("/api/clusters", params={"page_size": 2, "page": 1}).json()
    assert first["total"] == 3
    assert [item["name"] for item in first["items"]] == ["c1", "c2"]

    second = client.get("/api/clusters", params={"page_size": 2, "page": 2}).json()
    assert [item["name"] for item in second["items"]] == ["c3"]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "page"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 201}, "page_size"),
        ({"page": "x"}, "page"),
    ],
)
def test_a09_invalid_pagination_returns_400(app_client_and_raw, params, field):
    client, _ = app_client_and_raw
    response = client.get("/api/clusters", params=params)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == field for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# A10 / AC-09：无状态列 / 无状态字段
# --------------------------------------------------------------------------- #
def test_a10_no_status_column_or_field(app_client_and_raw):
    client, conn = app_client_and_raw

    from app.db.base import Base

    table = Base.metadata.tables["clusters"]
    assert not (STATUS_FIELDS & set(table.columns.keys()))

    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='clusters'"
        ).fetchall()
    }
    assert not (STATUS_FIELDS & db_columns)

    for model in (ClusterCreate, ClusterUpdate, ClusterRead):
        assert not (STATUS_FIELDS & set(model.model_fields))

    body = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    assert not (STATUS_FIELDS & set(body))


# --------------------------------------------------------------------------- #
# A11 / AC-10：无上级 / 位置列与字段
# --------------------------------------------------------------------------- #
def test_a11_no_position_or_parent_field(app_client_and_raw):
    client, conn = app_client_and_raw

    from app.db.base import Base

    db_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='clusters'"
        ).fetchall()
    }
    assert not (POSITION_FIELDS & db_columns)
    assert not (POSITION_FIELDS & set(Base.metadata.tables["clusters"].columns.keys()))

    for model in (ClusterCreate, ClusterUpdate, ClusterRead):
        assert not (POSITION_FIELDS & set(model.model_fields))

    body = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    assert not (POSITION_FIELDS & set(body))


# --------------------------------------------------------------------------- #
# A12 / AC-11：中文名称往返
# --------------------------------------------------------------------------- #
def test_a12_chinese_name_roundtrip(app_client_and_raw):
    client, _ = app_client_and_raw
    name = "高性能计算集群-A"
    created = client.post("/api/clusters", json={"name": name})
    assert created.status_code == 201
    assert created.json()["name"] == name

    listed = client.get("/api/clusters")
    assert [item["name"] for item in listed.json()["items"]] == [name]

    hit = client.get(f"/api/clusters/by-name/{quote(name, safe='')}")
    assert hit.status_code == 200
    assert hit.json()["name"] == name


# --------------------------------------------------------------------------- #
# A13 / AC-12：PATCH 复用同一套规则
# --------------------------------------------------------------------------- #
def test_a13_patch_rename_releases_old_name(app_client_and_raw):
    client, _ = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    renamed = client.patch(f"/api/clusters/{created['id']}", json={"name": "cluster-b"})
    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "cluster-b"
    assert body["id"] == created["id"]
    assert body["created_at"] == created["created_at"]

    # 旧名立即释放
    reused = client.post("/api/clusters", json={"name": "cluster-a"})
    assert reused.status_code == 201


def test_a13_patch_to_own_current_name_returns_200(app_client_and_raw):
    client, _ = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    response = client.patch(f"/api/clusters/{created['id']}", json={"name": "cluster-a"})
    assert response.status_code == 200
    assert response.json()["name"] == "cluster-a"


def test_a13_patch_to_active_duplicate_returns_409(app_client_and_raw):
    client, _ = app_client_and_raw
    first = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    client.post("/api/clusters", json={"name": "cluster-b"})

    response = client.patch(f"/api/clusters/{first['id']}", json={"name": "cluster-b"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_a13_patch_missing_or_soft_deleted_returns_404(app_client_and_raw):
    client, conn = app_client_and_raw
    assert client.patch("/api/clusters/999999", json={"name": "x"}).status_code == 404

    conn.execute("INSERT INTO clusters (name, deleted_at) VALUES ('gone', now())")
    gone_id = conn.execute("SELECT id FROM clusters WHERE name = 'gone'").fetchone()[0]
    response = client.patch(f"/api/clusters/{gone_id}", json={"name": "x"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a13_patch_missing_name_returns_400(app_client_and_raw):
    client, _ = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    response = client.patch(f"/api/clusters/{created['id']}", json={})
    assert response.status_code == 400
    body = response.json()
    assert any(detail["field"] == "name" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# A15 运行时部分：DELETE /api/clusters/{id} 不执行软删
# --------------------------------------------------------------------------- #
def test_a15_delete_endpoint_does_not_soft_delete(app_client_and_raw):
    client, conn = app_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    response = client.delete(f"/api/clusters/{created['id']}")
    assert response.status_code in (404, 405)

    # 该行仍为活跃
    assert (
        conn.execute("SELECT deleted_at FROM clusters WHERE id = %s", (created["id"],)).fetchone()[
            0
        ]
        is None
    )
    assert client.get(f"/api/clusters/{created['id']}").status_code == 200


# --------------------------------------------------------------------------- #
# T9′：产品端点完成 create → list → get → update 往返（F012 判据 5）
# --------------------------------------------------------------------------- #
def test_t9_prime_product_crud_roundtrip(app_client_and_raw):
    client, _ = app_client_and_raw

    created = client.post("/api/clusters", json={"name": "cluster-a"})
    assert created.status_code == 201
    cluster_id = created.json()["id"]

    listed = client.get("/api/clusters").json()
    assert listed["total"] == 1
    assert [item["id"] for item in listed["items"]] == [cluster_id]

    fetched = client.get(f"/api/clusters/{cluster_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "cluster-a"

    updated = client.patch(f"/api/clusters/{cluster_id}", json={"name": "cluster-b"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "cluster-b"

    # soft delete 一段由 A08 的「绕应用层预置 deleted_at → API 读取被排除」承接。


# --------------------------------------------------------------------------- #
# G3 / Q8 / NQ-1：无静默归一化（canary）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", [" cn-a ", "\u00e9", "e\u0301"])
def test_g3_no_silent_normalization(app_client_and_raw, name):
    """断言「实现不做任何 name 变换」，**不**断言这些名称在业务上合法。

    边界声明：``name`` 的长度 / 首尾空白 / 空字符串 / Unicode NFC 规范化属
    ``undefined_constraints``，当前既不确认合法也不确认非法。本用例只证明
    实现原样存取；若产品确认 PROPOSED-1，必须由产品决策同步修改 G1 / G2 / G3。
    """
    client, _ = app_client_and_raw

    created = client.post("/api/clusters", json={"name": name})
    assert created.status_code == 201
    assert created.json()["name"] == name

    listed = client.get("/api/clusters").json()
    assert [item["name"] for item in listed["items"]] == [name]

    hit = client.get(f"/api/clusters/by-name/{quote(name, safe='')}")
    assert hit.status_code == 200
    assert hit.json()["name"] == name

    # 逐字节相同
    assert hit.json()["name"].encode("utf-8") == name.encode("utf-8")

"""F014 逻辑删除 API 行为测试（T-01 ~ T-13）。

数据库断言使用 ``auth_client_and_raw`` 提供的**绕过应用层**原始 psycopg 连接；
并发 / 锁序测试自建第二条原始连接（``tests/database/helpers.py``）。
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest

from tests.database.helpers import raw_connection_dsn

CONFLICT_DETAIL_CODE = "ACTIVE_CHILDREN_EXIST"


def _row(conn, cluster_id: int):
    return conn.execute(
        "SELECT id, name, created_at, updated_at, deleted_at FROM clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()


def _snapshot(conn):
    return {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT id, name, created_at, updated_at, deleted_at FROM clusters ORDER BY id"
        ).fetchall()
    }


# --------------------------------------------------------------------------- #
# T-01 / AC-01：204 无响应体；行仍物理存在且 deleted_at 非空
# --------------------------------------------------------------------------- #
def test_t01_delete_returns_204_without_body_and_row_survives(auth_client_and_raw):
    client, conn = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    rows_before = conn.execute("SELECT count(*) FROM clusters").fetchone()[0]

    response = client.delete(f"/api/clusters/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert conn.execute("SELECT count(*) FROM clusters").fetchone()[0] == rows_before
    row = _row(conn, created["id"])
    assert row is not None, "逻辑删除不得物理删除行"
    assert row[4] is not None, "deleted_at 必须非空"


# --------------------------------------------------------------------------- #
# T-02 / AC-02：删除后不出现在常规读取；Empty 与 Not Found 可区分
# --------------------------------------------------------------------------- #
def test_t02_deleted_excluded_from_all_normal_reads(auth_client_and_raw):
    client, _ = auth_client_and_raw
    deleted = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    kept = client.post("/api/clusters", json={"name": "cluster-b"}).json()

    assert client.delete(f"/api/clusters/{deleted['id']}").status_code == 204

    listed = client.get("/api/clusters").json()
    assert [item["name"] for item in listed["items"]] == ["cluster-b"]
    assert listed["total"] == 1

    by_id = client.get(f"/api/clusters/{deleted['id']}")
    assert by_id.status_code == 404
    assert by_id.json()["error"]["code"] == "NOT_FOUND"

    by_name = client.get("/api/clusters/by-name/cluster-a")
    assert by_name.status_code == 404
    assert by_name.json()["error"]["code"] == "NOT_FOUND"

    # 删空后列表仍为 200 + items==[]（Empty ≠ Not Found）
    assert client.delete(f"/api/clusters/{kept['id']}").status_code == 204
    empty = client.get("/api/clusters")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


# --------------------------------------------------------------------------- #
# T-03 / AC-03：重复删除 404，deleted_at 不被改写；无恢复端点
# --------------------------------------------------------------------------- #
def test_t03_repeat_delete_404_and_no_restore(auth_client_and_raw):
    client, conn = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    assert client.delete(f"/api/clusters/{created['id']}").status_code == 204
    first_deleted_at = _row(conn, created["id"])[4]

    repeat = client.delete(f"/api/clusters/{created['id']}")
    assert repeat.status_code == 404
    assert repeat.json()["error"]["code"] == "NOT_FOUND"
    assert _row(conn, created["id"])[4] == first_deleted_at, "deleted_at 不得被改写"

    paths = client.app.openapi()["paths"]
    assert not any("restore" in path or "undelete" in path for path in paths)


@pytest.mark.parametrize("path", ["/api/clusters/abc", "/api/clusters/by-name"])
def test_t12_delete_non_integer_path_returns_400(auth_client_and_raw, path):
    """契约 §3.1：`cluster_id` 非整数 → 400 VALIDATION_ERROR（写操作无 by-name 别名）。"""
    client, _ = auth_client_and_raw
    response = client.delete(path)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "cluster_id" for detail in body["error"]["details"])


# --------------------------------------------------------------------------- #
# T-04 / AC-07 / §21：后端强制，与 UI 无关
# --------------------------------------------------------------------------- #
def test_t04_guard_is_enforced_by_backend_api(auth_client_and_raw, monkeypatch):
    client, _ = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    # 直接调用 API（无任何前端参与）：注入活跃子检查 → 后端拒绝。
    monkeypatch.setattr(
        "app.clusters.deletion.CLUSTER_ACTIVE_CHILD_CHECKS", (lambda session, pid: True,)
    )
    blocked = client.delete(f"/api/clusters/{created['id']}")
    assert blocked.status_code == 409

    # 无活跃子资源时，同一路径成功（证明拒绝来自守卫而非端点不可用）。
    monkeypatch.setattr("app.clusters.deletion.CLUSTER_ACTIVE_CHILD_CHECKS", ())
    assert client.delete(f"/api/clusters/{created['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# T-05 / AC-04：活跃子资源 → 409 + 稳定 code + 无部分写入
# --------------------------------------------------------------------------- #
def test_t05_active_child_check_conflict_without_partial_write(auth_client_and_raw, monkeypatch):
    client, conn = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    calls: list[int] = []

    def active_child(session, parent_id):
        calls.append(parent_id)
        return True

    monkeypatch.setattr("app.clusters.deletion.CLUSTER_ACTIVE_CHILD_CHECKS", (active_child,))

    response = client.delete(f"/api/clusters/{created['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert any(detail["code"] == CONFLICT_DETAIL_CODE for detail in body["error"]["details"])
    assert calls == [created["id"]], "删除路径必须真实调用声明的活跃子检查"

    row = _row(conn, created["id"])
    assert row is not None
    assert row[4] is None, "守卫命中时不得发生部分写入"


# --------------------------------------------------------------------------- #
# T-06 / AC-04 / AC-09：检查在父行加锁之后、同一事务内执行
# --------------------------------------------------------------------------- #
def test_t06_check_runs_after_parent_row_is_locked(auth_client_and_raw, database_url, monkeypatch):
    client, _ = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    observed: dict[str, bool] = {}

    def check(session, parent_id):
        observed["called"] = True
        # 第二条独立连接尝试对同一父行 NOWAIT 加锁：若父行已由本事务锁住则失败。
        with psycopg.connect(raw_connection_dsn(database_url)) as other:
            other.autocommit = True
            try:
                other.execute(
                    "SELECT id FROM clusters WHERE id = %s FOR UPDATE NOWAIT", (parent_id,)
                )
                observed["lock_available"] = True
            except psycopg.errors.LockNotAvailable:
                observed["lock_available"] = False
        return False

    monkeypatch.setattr("app.clusters.deletion.CLUSTER_ACTIVE_CHILD_CHECKS", (check,))

    response = client.delete(f"/api/clusters/{created['id']}")

    assert response.status_code == 204
    assert observed == {"called": True, "lock_available": False}, (
        "活跃子检查必须在删除事务已锁住父行之后执行"
    )


# --------------------------------------------------------------------------- #
# T-07 / AC-05：不级联，只改目标行
# --------------------------------------------------------------------------- #
def test_t07_delete_changes_only_the_target_row(auth_client_and_raw):
    client, conn = auth_client_and_raw
    target = client.post("/api/clusters", json={"name": "cluster-a"}).json()
    other = client.post("/api/clusters", json={"name": "cluster-b"}).json()

    before = _snapshot(conn)
    assert client.delete(f"/api/clusters/{target['id']}").status_code == 204
    after = _snapshot(conn)

    assert set(before) == set(after), "不得物理删除任何行"
    for cluster_id, columns in before.items():
        if cluster_id == target["id"]:
            assert after[cluster_id][0] == columns[0]  # name 不变
            assert columns[3] is None and after[cluster_id][3] is not None
        else:
            assert after[cluster_id] == columns, f"cluster {cluster_id} 不得被改动"

    # 明确断言其他活跃行仍活跃
    assert _row(conn, other["id"])[4] is None


# --------------------------------------------------------------------------- #
# T-08 / AC-06：已删释放唯一性，同名可重建，旧行保留
# --------------------------------------------------------------------------- #
def test_t08_delete_releases_name_and_old_row_is_preserved(auth_client_and_raw):
    client, conn = auth_client_and_raw
    name = "cluster-a"
    created = client.post("/api/clusters", json={"name": name}).json()
    assert client.delete(f"/api/clusters/{created['id']}").status_code == 204
    deleted_at_after_delete = _row(conn, created["id"])[4]

    recreated = client.post("/api/clusters", json={"name": name})
    assert recreated.status_code == 201
    assert recreated.json()["id"] != created["id"]

    listed = client.get("/api/clusters").json()
    assert [item["id"] for item in listed["items"]] == [recreated.json()["id"]]

    # 旧行保留且 deleted_at 未被改写
    assert conn.execute("SELECT count(*) FROM clusters WHERE name = %s", (name,)).fetchone()[0] == 2
    assert _row(conn, created["id"])[4] == deleted_at_after_delete


# --------------------------------------------------------------------------- #
# T-09 / AC-02：Empty 与 Not Found 语义不同
# --------------------------------------------------------------------------- #
def test_t09_empty_list_versus_not_found_are_distinct(auth_client_and_raw):
    client, _ = auth_client_and_raw

    empty = client.get("/api/clusters")
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    missing = client.get("/api/clusters/999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["details"] == []


# --------------------------------------------------------------------------- #
# T-10 / AC-12：未认证 401 且数据不变；已认证普通用户即可删除
# --------------------------------------------------------------------------- #
def test_t10_unauthenticated_delete_is_401_without_data_change(app_client_and_raw):
    client, conn = app_client_and_raw
    conn.execute("INSERT INTO clusters (name) VALUES ('cluster-a')")
    cluster_id = conn.execute("SELECT id FROM clusters WHERE name = 'cluster-a'").fetchone()[0]

    response = client.delete(f"/api/clusters/{cluster_id}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert _row(conn, cluster_id)[4] is None, "未认证请求不得改变数据"


def test_t10_authenticated_user_needs_no_role(auth_client_and_raw):
    client, _ = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    assert client.delete(f"/api/clusters/{created['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# T-13 / AC-09：删除使用阻塞行锁（另一连接持锁时 DELETE 阻塞）
# --------------------------------------------------------------------------- #
@pytest.mark.database
def test_t13_delete_blocks_while_row_is_locked(auth_client_and_raw, database_url):
    client, _ = auth_client_and_raw
    created = client.post("/api/clusters", json={"name": "cluster-a"}).json()

    blocker = psycopg.connect(raw_connection_dsn(database_url))
    blocker.autocommit = False
    blocker.execute("SELECT id FROM clusters WHERE id = %s FOR UPDATE", (created["id"],))

    result: dict[str, object] = {}

    def worker():
        result["response"] = client.delete(f"/api/clusters/{created['id']}")

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        time.sleep(1.5)
        assert thread.is_alive(), "目标行被锁定期间 DELETE 必须阻塞等待，而非基于快照直接更新"
    finally:
        blocker.rollback()
        blocker.close()

    thread.join(timeout=10)
    assert not thread.is_alive()
    response = result["response"]
    assert getattr(response, "status_code", None) == 204

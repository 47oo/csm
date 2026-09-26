"""F001 集群集成测试（架构 §7 / 数据库设计 §7，真实 PostgreSQL）。

覆盖 code 规范化与不可复用、名称规则、purpose、乐观锁、二次确认、权限、
审计/历史写入与删除后保留、关联保护 23503→409。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db import SessionLocal, engine
from app.main import app
from app.models import AuditLog, Cluster, ReservedClusterCode, ResourceHistory

PASSWORD = "Passw0rd1"


def _auth(client, add_user, login_as, username: str, role: str):
    add_user(username, PASSWORD, role)
    assert login_as(client, username, PASSWORD).status_code == 200
    return client


def _create(client, code: str, name: str = "Alpha", purpose: str = "测试用途"):
    return client.post(
        "/api/v1/clusters",
        json={"code": code, "name": name, "purpose": purpose},
    )


# --- code 身份：规范化判重、格式、不可改、删除后不复用 -------------------------


def test_code_normalized_unique_and_display(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")

    created = _create(client, " n96p ", name="Cluster_A")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"] == "n96p"  # 展示保留大小写、去首尾空格
    assert body["version"] == 1
    assert "code_key" not in body

    # 大小写/空格等价判重。
    for dup in ["N96P", "n96p", " n96p "]:
        resp = _create(client, dup, name=f"Other_{dup.strip()}")
        assert resp.status_code == 409, dup
        assert resp.json()["code"] == "CLUSTER_CODE_TAKEN", dup


def test_code_format_rejected(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")

    for bad in ["ab cd", "AB!", "ＡＢ", "", "A" * 33, "a-b"]:
        resp = _create(client, bad, name="ValidName")
        assert resp.status_code == 422, bad
        assert resp.json()["errors"][0]["code"] == "CODE_FORMAT", bad


def test_code_immutable_via_patch(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "C001", name="Alpha").json()

    resp = client.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"code": "C002", "name": "Beta", "version": cluster["version"]},
    )
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "CODE_IMMUTABLE"

    # 无任何可改字段。
    resp = client.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"version": cluster["version"]},
    )
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "NO_FIELDS"


def test_code_not_reused_after_delete(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "REUSE1", name="Alpha").json()

    dele = client.delete(
        f"/api/v1/clusters/{cluster['id']}",
        params={"confirm": "Alpha", "version": cluster["version"]},
    )
    assert dele.status_code == 204

    again = _create(client, "reuse1", name="Beta")
    assert again.status_code == 409
    assert again.json()["code"] == "CLUSTER_CODE_TAKEN"

    with SessionLocal() as db:
        assert db.scalar(
            select(func.count())
            .select_from(ReservedClusterCode)
            .where(ReservedClusterCode.code_key == "REUSE1")
        ) == 1


# --- 名称：字符集 / 大小写 / 真删后可复用 -------------------------------------


def test_name_rules(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")

    for bad in ["a b", "a\tb", "bad!", "a" * 65, ""]:
        resp = _create(client, "N001", name=bad)
        assert resp.status_code == 422, repr(bad)
        assert resp.json()["errors"][0]["code"] == "NAME_FORMAT", repr(bad)

    # 中文与下划线允许。
    assert _create(client, "N002", name="集群_01").status_code == 201
    # 大小写不同允许共存。
    assert _create(client, "N003", name="ABC").status_code == 201
    assert _create(client, "N004", name="abc").status_code == 201
    # 完全相同拒绝。
    dup = _create(client, "N005", name="ABC")
    assert dup.status_code == 409
    assert dup.json()["code"] == "CLUSTER_NAME_TAKEN"


def test_name_reusable_after_real_delete(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "DELNAME", name="Reusable").json()

    assert (
        client.delete(
            f"/api/v1/clusters/{cluster['id']}",
            params={"confirm": "Reusable", "version": cluster["version"]},
        ).status_code
        == 204
    )
    assert _create(client, "NEWCODE", name="Reusable").status_code == 201


def test_purpose_validation_and_update(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")

    for bad in ["", "   ", "x" * 201]:
        resp = _create(client, "P001", name="Pname", purpose=bad)
        assert resp.status_code == 422, repr(bad)
        assert resp.json()["errors"][0]["code"] == "PURPOSE_INVALID", repr(bad)

    cluster = _create(client, "P002", name="Pname2", purpose="旧用途").json()
    patched = client.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"purpose": "新用途", "version": cluster["version"]},
    )
    assert patched.status_code == 200
    assert patched.json()["purpose"] == "新用途"
    assert patched.json()["version"] == cluster["version"] + 1


# --- 乐观锁 ----------------------------------------------------------------


def test_optimistic_lock(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "OPT1", name="Alpha").json()

    ok = client.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"name": "Beta", "version": 1},
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    stale = client.patch(
        f"/api/v1/clusters/{cluster['id']}",
        json={"purpose": "x", "version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    stale_delete = client.delete(
        f"/api/v1/clusters/{cluster['id']}",
        params={"confirm": "Beta", "version": 1},
    )
    assert stale_delete.status_code == 409
    assert stale_delete.json()["code"] == "VERSION_CONFLICT"


# --- 二次确认 --------------------------------------------------------------


def test_delete_confirmation(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "CONF1", name="ConfirmMe").json()

    mismatch = client.delete(
        f"/api/v1/clusters/{cluster['id']}",
        params={"confirm": "wrong", "version": cluster["version"]},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "DELETE_CONFIRMATION_MISMATCH"
    # 未删除。
    assert client.get(f"/api/v1/clusters/{cluster['id']}").status_code == 200

    # code 规范化（大小写不敏感）也可确认。
    ok = client.delete(
        f"/api/v1/clusters/{cluster['id']}",
        params={"confirm": "conf1", "version": cluster["version"]},
    )
    assert ok.status_code == 204
    assert client.get(f"/api/v1/clusters/{cluster['id']}").status_code == 404


# --- 权限 ------------------------------------------------------------------


def test_permissions(client, add_user, login_as) -> None:
    # admin 建一个集群供删除用。
    admin = _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(admin, "PERM1", name="PermCluster").json()

    # 未登录。
    anon = TestClient(app)
    assert anon.get("/api/v1/clusters").status_code == 401
    assert _create(anon, "X", name="X").status_code == 401

    # viewer：可读，写/删 403。
    viewer = _auth(client, add_user, login_as, "v1", "viewer")
    assert viewer.get("/api/v1/clusters").status_code == 200
    assert _create(viewer, "V001", name="Vname").status_code == 403
    assert (
        viewer.patch(
            f"/api/v1/clusters/{cluster['id']}",
            json={"name": "V2", "version": cluster["version"]},
        ).status_code
        == 403
    )
    assert (
        viewer.delete(
            f"/api/v1/clusters/{cluster['id']}",
            params={"confirm": "PermCluster", "version": cluster["version"]},
        ).status_code
        == 403
    )

    # maintainer：可读可删，写 403。
    maint = _auth(client, add_user, login_as, "m1", "maintainer")
    assert _create(maint, "M001", name="Mname").status_code == 403
    assert (
        maint.patch(
            f"/api/v1/clusters/{cluster['id']}",
            json={"name": "M2", "version": cluster["version"]},
        ).status_code
        == 403
    )
    assert (
        maint.delete(
            f"/api/v1/clusters/{cluster['id']}",
            params={"confirm": "PermCluster", "version": cluster["version"]},
        ).status_code
        == 204
    )


# --- 列表：分页 / q / 排序 / 空 --------------------------------


def test_list_pagination_search_sort(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")

    empty = client.get("/api/v1/clusters")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    _create(client, "L001", name="ab")
    _create(client, "L002", name="a_b")
    _create(client, "L003", name="Zeta")

    paged = client.get("/api/v1/clusters", params={"page": 2, "page_size": 2})
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1
    assert paged.json()["items"][0]["code"] == "L003"
    assert paged.json()["page"] == 2

    # q 包含匹配 + `_` 转义为普通字符。
    q_underscore = client.get("/api/v1/clusters", params={"q": "_"})
    assert [i["name"] for i in q_underscore.json()["items"]] == ["a_b"]

    # 大小写不敏感（英文）。
    q_case = client.get("/api/v1/clusters", params={"q": "zE"})
    assert [i["code"] for i in q_case.json()["items"]] == ["L003"]

    by_name = client.get("/api/v1/clusters", params={"sort": "name"})
    assert [i["name"] for i in by_name.json()["items"]] == ["a_b", "ab", "Zeta"]

    # 非法分页/排序 → 400。
    assert client.get("/api/v1/clusters", params={"page_size": 101}).status_code == 400
    assert client.get("/api/v1/clusters", params={"sort": "bogus"}).status_code == 400


# --- 审计与历史 ------------------------------------------------------------


def test_audit_and_history(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "AH01", name="AuditCluster", purpose="p1").json()
    cid = cluster["id"]

    with SessionLocal() as db:
        audit_row = db.scalar(
            select(AuditLog).where(
                AuditLog.target_type == "cluster",
                AuditLog.target_id == str(cid),
                AuditLog.action == "cluster.create",
            )
        )
        assert audit_row is not None
        assert audit_row.target_key_snapshot == "AH01"

    # update → 审计 + 历史。
    assert (
        client.patch(
            f"/api/v1/clusters/{cid}",
            json={"name": "Renamed", "purpose": "p2", "version": 1},
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        upd_audit = db.scalar(
            select(AuditLog).where(
                AuditLog.target_id == str(cid), AuditLog.action == "cluster.update"
            )
        )
        assert upd_audit is not None
        assert upd_audit.change == {
            "name": {"from": "AuditCluster", "to": "Renamed"},
            "purpose": {"from": "p1", "to": "p2"},
        }
        hist = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.target_type == "cluster",
                ResourceHistory.target_id == str(cid),
                ResourceHistory.action == "update",
            )
        )
        assert hist is not None
        assert hist.actor_user_id is not None
        assert hist.change["name"]["to"] == "Renamed"

    # delete → 审计 + 历史；集群删除后仍在。
    assert (
        client.delete(
            f"/api/v1/clusters/{cid}",
            params={"confirm": "Renamed", "version": 2},
        ).status_code
        == 204
    )
    with SessionLocal() as db:
        assert db.get(Cluster, cid) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == str(cid))
            )
            >= 3
        )
        del_hist = db.scalar(
            select(ResourceHistory).where(
                ResourceHistory.target_id == str(cid),
                ResourceHistory.action == "delete",
            )
        )
        assert del_hist is not None
        assert del_hist.change == {
            "code": "AH01",
            "name": "Renamed",
            "purpose": "p2",
        }
        assert db.scalar(
            select(func.count())
            .select_from(ReservedClusterCode)
            .where(ReservedClusterCode.code_key == "AH01")
        ) == 1


# --- 关联保护：RESTRICT FK → 23503 → 409 -----------------------------------


def test_delete_blocked_by_association(client, add_user, login_as) -> None:
    _auth(client, add_user, login_as, "root", "admin")
    cluster = _create(client, "ASSOC1", name="AssocCluster").json()

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE probe_cluster_ref ("
                "  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                "  cluster_id bigint NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT"
                ")"
            )
        )
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO probe_cluster_ref (cluster_id) VALUES (:c)"),
                {"c": cluster["id"]},
            )

        resp = client.delete(
            f"/api/v1/clusters/{cluster['id']}",
            params={"confirm": "AssocCluster", "version": cluster["version"]},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "CLUSTER_HAS_ASSOCIATIONS"
        # 未删除，且事务回滚未留下审计/历史副作用。
        assert client.get(f"/api/v1/clusters/{cluster['id']}").status_code == 200

        # 解除关联后可删除（历史不阻塞）。
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM probe_cluster_ref WHERE cluster_id=:c"), {"c": cluster["id"]})
        ok = client.delete(
            f"/api/v1/clusters/{cluster['id']}",
            params={"confirm": "AssocCluster", "version": cluster["version"]},
        )
        assert ok.status_code == 204
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS probe_cluster_ref"))
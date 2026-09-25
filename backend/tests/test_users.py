"""用户与角色管理集成测试（场景 75–81）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, ReservedUsername, User

VIEWER_PERMS = ("viewer",)


def _admin(client, add_user, login_as):
    admin_id = add_user("root", "Rootpass1", "admin")
    resp = login_as(client, "root", "Rootpass1")
    assert resp.status_code == 200
    return admin_id


def test_scenario_75_create_user_and_login(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)

    created = client.post(
        "/api/v1/users",
        json={"username": "newbie", "password": "Initpass1", "role": "viewer"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["username"] == "newbie"
    assert body["role"] == "viewer"
    assert body["status"] == "enabled"
    assert body["must_change_password"] is True
    assert body["version"] == 1

    # 新用户可登录。
    worker = TestClient(app)
    login = login_as(worker, "newbie", "Initpass1")
    assert login.status_code == 200
    assert login.json()["role"] == "viewer"

    # 同名（仍存用户）被拒绝。
    dup = client.post(
        "/api/v1/users",
        json={"username": "newbie", "password": "Initpass1", "role": "viewer"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "USERNAME_TAKEN"


def test_scenario_75_username_rules(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)

    for bad in ["ab cd", "abc!", " ab ", "a" * 129, "", "用户名"]:
        resp = client.post(
            "/api/v1/users",
            json={"username": bad, "password": "Initpass1", "role": "viewer"},
        )
        assert resp.status_code == 422, bad
        assert resp.json()["errors"][0]["code"] == "USERNAME_INVALID", bad

    # 区分大小写：Alice 与 alice 是不同用户名。
    assert (
        client.post(
            "/api/v1/users",
            json={"username": "Alice", "password": "Initpass1", "role": "viewer"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/users",
            json={"username": "alice", "password": "Initpass1", "role": "viewer"},
        ).status_code
        == 201
    )


def test_scenario_75_password_policy(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)

    for bad in ["short1", "onlyletters", "12345678"]:
        resp = client.post(
            "/api/v1/users",
            json={"username": "puser", "password": bad, "role": "viewer"},
        )
        assert resp.status_code == 422, bad
        assert resp.json()["errors"][0]["code"] == "PASSWORD_POLICY", bad


def test_scenario_76_role_change_takes_effect_immediately(
    client, add_user, login_as
) -> None:
    _admin(client, add_user, login_as)

    created = client.post(
        "/api/v1/users",
        json={"username": "worker", "password": "Initpass1", "role": "viewer"},
    ).json()
    user_id = created["id"]

    worker = TestClient(app)
    assert login_as(worker, "worker", "Initpass1").status_code == 200
    assert (
        worker.post(
            "/api/v1/auth/change-password",
            json={"current_password": "Initpass1", "new_password": "Workerp1"},
        ).status_code
        == 204
    )

    # 旧角色：viewer 无用户管理权限。
    assert worker.get("/api/v1/users").status_code == 403

    # 改密会自增 version，取当前版本后再做乐观锁更新。
    current = client.get(f"/api/v1/users/{user_id}").json()

    # 提升为 admin。
    patched = client.patch(
        f"/api/v1/users/{user_id}",
        json={"role": "admin", "version": current["version"]},
    )
    assert patched.status_code == 200
    assert patched.json()["role"] == "admin"
    assert patched.json()["version"] == current["version"] + 1

    # 新操作立即按新角色鉴权（无需重新登录）。
    assert worker.get("/api/v1/users").status_code == 200

    # 降回 viewer。
    assert (
        client.patch(
            f"/api/v1/users/{user_id}",
            json={"role": "viewer", "version": current["version"] + 1},
        ).status_code
        == 200
    )
    assert worker.get("/api/v1/users").status_code == 403


def test_username_cannot_be_changed(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "fixedname", "password": "Initpass1", "role": "viewer"},
    ).json()

    resp = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"username": "newname", "role": "admin", "version": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"

    # 无字段可改。
    resp2 = client.patch(
        f"/api/v1/users/{created['id']}", json={"version": 1}
    )
    assert resp2.status_code == 400


def test_scenario_77_delete_user(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "victim", "password": "Initpass1", "role": "viewer"},
    ).json()

    deleted = client.delete(f"/api/v1/users/{created['id']}?version=1")
    assert deleted.status_code == 204

    # 不能登录。
    assert (
        login_as(client, "victim", "Initpass1").status_code == 401
    )

    # 用户名不复用（含已删除历史）。
    reuse = client.post(
        "/api/v1/users",
        json={"username": "victim", "password": "Initpass1", "role": "viewer"},
    )
    assert reuse.status_code == 409
    assert reuse.json()["code"] == "USERNAME_TAKEN"

    with SessionLocal() as db:
        # reserved 与审计保留。
        assert (
            db.scalar(
                select(func.count())
                .select_from(ReservedUsername)
                .where(ReservedUsername.username_key == "victim")
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "user.delete",
                    AuditLog.target_key_snapshot == "victim",
                )
            )
            == 1
        )
        assert db.get(User, created["id"]) is None


def test_scenario_77_cannot_delete_last_enabled_admin(
    client, add_user, login_as
) -> None:
    admin_id = _admin(client, add_user, login_as)

    resp = client.delete(f"/api/v1/users/{admin_id}?version=1")
    assert resp.status_code == 409
    assert resp.json()["code"] == "LAST_ADMIN"

    with SessionLocal() as db:
        assert db.get(User, admin_id) is not None


def test_delete_last_admin_allowed_when_another_enabled_admin(
    client, add_user, login_as
) -> None:
    _admin(client, add_user, login_as)
    second = client.post(
        "/api/v1/users",
        json={"username": "root2", "password": "Rootpass2", "role": "admin"},
    ).json()

    # 存在两个启用 admin，可删其一。
    assert client.delete(f"/api/v1/users/{second['id']}?version=1").status_code == 204


def test_scenario_79_disable_and_enable(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "toggler", "password": "Initpass1", "role": "viewer"},
    ).json()
    user_id = created["id"]

    assert client.post(f"/api/v1/users/{user_id}/disable").status_code == 204
    # 幂等。
    assert client.post(f"/api/v1/users/{user_id}/disable").status_code == 204
    assert login_as(client, "toggler", "Initpass1").status_code == 403

    # 记录保留。
    with SessionLocal() as db:
        assert db.get(User, user_id) is not None

    assert client.post(f"/api/v1/users/{user_id}/enable").status_code == 204
    assert client.post(f"/api/v1/users/{user_id}/enable").status_code == 204
    assert login_as(client, "toggler", "Initpass1").status_code == 200


def test_scenario_79_cannot_disable_last_enabled_admin(
    client, add_user, login_as
) -> None:
    admin_id = _admin(client, add_user, login_as)

    resp = client.post(f"/api/v1/users/{admin_id}/disable")
    assert resp.status_code == 409
    assert resp.json()["code"] == "LAST_ADMIN"

    with SessionLocal() as db:
        assert db.get(User, admin_id).status == "enabled"


def test_scenario_78_admin_reset_password(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    client.post(
        "/api/v1/users",
        json={"username": "resetme", "password": "Initpass1", "role": "viewer"},
    )

    # 先完成首登改密，建立可登录状态。
    worker = TestClient(app)
    assert login_as(worker, "resetme", "Initpass1").status_code == 200
    worker.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Initpass1", "new_password": "Workerp1"},
    )

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "resetme"))
        assert user is not None
        user_id = user.id

    resp = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        json={"new_password": "Resetpass9"},
    )
    assert resp.status_code == 204

    # 旧口令失效、新口令可登录；既有会话被撤销。
    assert login_as(client, "resetme", "Workerp1").status_code == 401
    assert worker.get("/api/v1/auth/me").status_code == 401
    assert login_as(client, "resetme", "Resetpass9").status_code == 200

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.must_change_password is True


def test_scenario_80_non_admin_forbidden_and_data_unchanged(
    client, add_user, login_as
) -> None:
    _admin(client, add_user, login_as)
    target = client.post(
        "/api/v1/users",
        json={"username": "target", "password": "Initpass1", "role": "viewer"},
    ).json()
    add_user("vieweruser", "Viewerp1", "viewer")
    add_user("maintuser", "Maintp1", "maintainer")

    with SessionLocal() as db:
        before_count = db.scalar(select(func.count()).select_from(User))
        before_target = db.get(User, target["id"])
        before_snapshot = (
            before_target.role,
            before_target.status,
            before_target.version,
        )

    for username, password in [("vieweruser", "Viewerp1"), ("maintuser", "Maintp1")]:
        actor = TestClient(app)
        assert login_as(actor, username, password).status_code == 200
        assert actor.get("/api/v1/users").status_code == 403
        assert (
            actor.post(
                "/api/v1/users",
                json={"username": "hacker", "password": "Hackerp1", "role": "admin"},
            ).status_code
            == 403
        )
        assert (
            actor.patch(
                f"/api/v1/users/{target['id']}",
                json={"role": "admin", "version": 1},
            ).status_code
            == 403
        )
        assert (
            actor.delete(f"/api/v1/users/{target['id']}?version=1").status_code == 403
        )
        assert (
            actor.post(f"/api/v1/users/{target['id']}/disable").status_code == 403
        )
        assert (
            actor.post(f"/api/v1/users/{target['id']}/enable").status_code == 403
        )
        assert (
            actor.post(
                f"/api/v1/users/{target['id']}/reset-password",
                json={"new_password": "Hackedpass1"},
            ).status_code
            == 403
        )

    with SessionLocal() as db:
        after_count = db.scalar(select(func.count()).select_from(User))
        after_target = db.get(User, target["id"])
        after_snapshot = (
            after_target.role,
            after_target.status,
            after_target.version,
        )
    assert after_count == before_count
    assert after_snapshot == before_snapshot


def test_scenario_81_audit_records(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "auditee", "password": "Initpass1", "role": "viewer"},
    ).json()
    user_id = created["id"]

    client.patch(f"/api/v1/users/{user_id}", json={"role": "admin", "version": 1})
    client.post(f"/api/v1/users/{user_id}/disable")
    client.post(f"/api/v1/users/{user_id}/enable")
    client.post(
        f"/api/v1/users/{user_id}/reset-password",
        json={"new_password": "Resetpass9"},
    )

    with SessionLocal() as db:
        rows = db.scalars(
            select(AuditLog)
            .where(AuditLog.target_id == str(user_id))
            .order_by(AuditLog.id)
        ).all()
        actions = [row.action for row in rows]
        assert actions == [
            "user.create",
            "user.update_role",
            "user.disable",
            "user.enable",
            "user.reset_password",
        ]
        for row in rows:
            assert row.actor_username_snapshot == "root"
            assert row.target_type == "user"
            assert row.target_key_snapshot == "auditee"
            assert row.result == "success"


def test_optimistic_lock_conflicts(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "locked", "password": "Initpass1", "role": "viewer"},
    ).json()
    user_id = created["id"]

    stale = client.patch(
        f"/api/v1/users/{user_id}", json={"role": "admin", "version": 99}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    assert (
        client.patch(
            f"/api/v1/users/{user_id}", json={"role": "admin", "version": 1}
        ).status_code
        == 200
    )

    stale_delete = client.delete(f"/api/v1/users/{user_id}?version=1")
    assert stale_delete.status_code == 409
    assert stale_delete.json()["code"] == "VERSION_CONFLICT"


def test_not_found(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    assert client.get("/api/v1/users/9999").status_code == 404
    assert client.get("/api/v1/users/9999").json()["code"] == "USER_NOT_FOUND"
    assert client.delete("/api/v1/users/9999?version=1").status_code == 404
    assert client.post("/api/v1/users/9999/disable").status_code == 404


def test_unauthenticated_access(client) -> None:
    assert client.get("/api/v1/users").status_code == 401
    assert client.get("/api/v1/users").json()["code"] == "UNAUTHENTICATED"


def test_list_filters_and_pagination(client, add_user, login_as) -> None:
    _admin(client, add_user, login_as)
    for name in ["zeta", "alpha", "beta"]:
        client.post(
            "/api/v1/users",
            json={"username": name, "password": "Initpass1", "role": "viewer"},
        )

    listing = client.get("/api/v1/users?sort=username")
    assert listing.status_code == 200
    body = listing.json()
    usernames = [item["username"] for item in body["items"]]
    assert usernames == ["alpha", "beta", "root", "zeta"]
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 20

    filtered = client.get("/api/v1/users?role=admin").json()
    assert [i["username"] for i in filtered["items"]] == ["root"]

    search = client.get("/api/v1/users?q=al").json()
    assert [i["username"] for i in search["items"]] == ["alpha"]

    empty = client.get("/api/v1/users?q=nomatch").json()
    assert empty["items"] == []
    assert empty["total"] == 0

    paged = client.get("/api/v1/users?page=2&page_size=2&sort=username").json()
    assert [i["username"] for i in paged["items"]] == ["root", "zeta"]


def test_delete_cascades_and_preserves_username(
    client, add_user, login_as
) -> None:
    _admin(client, add_user, login_as)
    created = client.post(
        "/api/v1/users",
        json={"username": "cascade", "password": "Initpass1", "role": "viewer"},
    ).json()
    user_id = created["id"]

    # 建立会话后删除，会话应随用户删除。
    worker = TestClient(app)
    assert login_as(worker, "cascade", "Initpass1").status_code == 200

    assert client.delete(f"/api/v1/users/{user_id}?version=1").status_code == 204
    assert worker.get("/api/v1/auth/me").status_code == 401

    with SessionLocal() as db:
        reserved = db.scalar(
            select(func.count())
            .select_from(ReservedUsername)
            .where(ReservedUsername.username_key == "cascade")
        )
        assert reserved == 1
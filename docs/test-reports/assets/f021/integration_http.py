"""F021 独立真实 HTTP 集成（真实 uvicorn + 真实 PostgreSQL）。

独立 Tester 资产。先外部启动：
    CSM_DATABASE_URL=postgresql+psycopg://csm:csm@localhost:55432/csm_f021_integration \
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8798

用法：
    .venv/bin/python docs/test-reports/assets/f021/integration_http.py \
        http://127.0.0.1:8798 postgresql://csm:csm@localhost:55432/csm_f021_integration

覆盖：认证 / 自动分配 / 手动分配 / 耗尽 / 字段封闭 / NIC 404 / F005 不拦截 /
耗尽原子性 / 直连 DB cluster_id 推导与漂移。
"""

from __future__ import annotations

import sys

import httpx
import psycopg

PASS = 0
FAIL = 0
AUTH = ("tester", "tester-password-123")
READ_FIELDS = {"id", "network_interface_id", "ip_address", "created_at", "updated_at"}


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {label} {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {label} {detail}")


def reset(dsn: str) -> None:
    raw_url = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(raw_url) as conn:
        conn.autocommit = True
        conn.execute(
            "TRUNCATE ip_addresses, ip_address_ranges, network_interfaces, bare_metals, clusters, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


def fresh_count(dsn: str, sql: str, params: tuple = ()) -> int:
    url = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as conn:
        return conn.execute(sql, params).fetchone()[0]


def ensure_admin(dsn: str) -> None:
    """通过应用服务建立初始管理员（测试夹具，非复制业务规则）。"""
    from app.auth import service
    from app.config import Settings
    from app.db.session import create_db_engine, create_session_factory

    engine = create_db_engine(Settings(environment="test", database_url=dsn))
    try:
        with create_session_factory(engine)() as session:
            service.create_initial_admin(session, AUTH[0], AUTH[1])
            session.commit()
    finally:
        engine.dispose()


def main(base: str, dsn: str) -> int:
    reset(dsn)
    ensure_admin(dsn)
    raw = psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://", 1))
    raw.autocommit = True

    def count_ip() -> int:
        # 使用全新连接，避免持久连接的快照滞后（独立测试探针可靠性）。
        x = psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://", 1))
        try:
            return x.execute("SELECT count(*) FROM ip_addresses").fetchone()[0]
        finally:
            x.close()

    def chain(c: httpx.Client, name: str, ranges=None):
        cid = c.post("/api/clusters", json={"name": name}).json()["id"]
        bm = c.post("/api/bare-metals", json={"cluster_id": cid, "hostname": name + "-n1"}).json()["id"]
        nic = c.post(
            "/api/network-interfaces",
            json={"bare_metal_id": bm, "name": "eth0", "technology_type": "Ethernet", "purpose": "Business"},
        ).json()["id"]
        for s, e in ranges or []:
            r = c.post("/api/ip-address-ranges", json={"cluster_id": cid, "start_ip": s, "end_ip": e})
            assert r.status_code == 201, r.text
        return cid, bm, nic

    with httpx.Client(base_url=base, timeout=30.0) as c:
        # 1) 未认证 → 401
        r1 = httpx.post(f"{base}/api/ip-addresses/allocate", json={"network_interface_id": 1})
        r2 = httpx.post(f"{base}/api/ip-addresses/allocate-manual",
                        json={"network_interface_id": 1, "ip_address": "10.0.0.1"})
        check("1. unauth auto 401", r1.status_code == 401 and r1.json()["error"]["code"] == "UNAUTHENTICATED",
              str(r1.status_code))
        check("1. unauth manual 401", r2.status_code == 401 and r2.json()["error"]["code"] == "UNAUTHENTICATED",
              str(r2.status_code))

        # login
        lr = c.post("/api/auth/login", json={"username": AUTH[0], "password": AUTH[1]})
        check("2. login", lr.status_code == 200, str(lr.status_code))

        # 3) 自动分配全局最小（范围打乱顺序：先建大段）
        cid, bm, nic = chain(c, "c1", [("10.0.0.10", "10.0.0.12"), ("10.0.0.1", "10.0.0.3")])
        a = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic})
        check("3. auto global-min across disjoint ranges", a.status_code == 201 and a.json()["ip_address"] == "10.0.0.1",
              a.text)
        check("3. response field set exactly", set(a.json()) == READ_FIELDS, str(set(a.json())))
        check("3. response has no cluster_id", "cluster_id" not in a.json())

        # 4) 已占用跳过
        occupied = c.post("/api/ip-addresses", json={"network_interface_id": nic, "ip_address": "10.0.0.2"})
        check("4. F005 register in-range 201", occupied.status_code == 201, occupied.text)
        b = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic})
        check("4. auto skips occupied 10.0.0.2 -> 10.0.0.3", b.status_code == 201 and b.json()["ip_address"] == "10.0.0.3",
              b.text)

        # 5) 无隐式保留：范围含 10.0.0.0
        cid2, _, nic2 = chain(c, "c2", [("10.0.0.0", "10.0.0.255")])
        c2 = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic2})
        check("5. network address 10.0.0.0 not skipped", c2.status_code == 201 and c2.json()["ip_address"] == "10.0.0.0",
              c2.text)

        # 6) 手动分配 + 规范化
        cid3, _, nic3 = chain(c, "c3", [("10.0.0.1", "10.0.0.255")])
        m = c.post("/api/ip-addresses/allocate-manual",
                   json={"network_interface_id": nic3, "ip_address": "010.0.0.5"})
        check("6. manual non-canonical normalised", m.status_code == 201 and m.json()["ip_address"] == "10.0.0.5", m.text)
        stored = raw.execute("SELECT ip_address FROM ip_addresses WHERE id=%s", (m.json()["id"],)).fetchone()[0]
        check("6. stored canonical", stored == "10.0.0.5", stored)

        # 7) 非法格式 → 400 且无写入
        before = count_ip()
        for bad in ["10.0.0.256", "10.0.0", "abc", "1.2.3.4/24", "2001:db8::1", "", " 10.0.0.1", "10.0.0.1 "]:
            rr = c.post("/api/ip-addresses/allocate-manual",
                        json={"network_interface_id": nic3, "ip_address": bad})
            ok = (rr.status_code == 400 and rr.json()["error"]["code"] == "VALIDATION_ERROR"
                  and any(d["field"] == "ip_address" and d.get("code") == "INVALID"
                          for d in rr.json()["error"]["details"]))
            check(f"7. invalid {bad!r} -> 400 INVALID", ok, rr.text[:120])
        check("7. no write on invalid", count_ip() == before, f"{count_ip()} vs {before}")

        # 8) 范围外 → 409 OUT_OF_RANGE
        o = c.post("/api/ip-addresses/allocate-manual",
                   json={"network_interface_id": nic3, "ip_address": "10.9.9.9"})
        check("8. manual out of range -> 409 OUT_OF_RANGE",
              o.status_code == 409 and o.json()["error"]["details"][0]["code"] == "OUT_OF_RANGE", o.text)

        # 9) 范围内已占用 → 409 DUPLICATE
        d = c.post("/api/ip-addresses/allocate-manual",
                   json={"network_interface_id": nic3, "ip_address": "10.0.0.5"})
        check("9. manual duplicate -> 409 DUPLICATE",
              d.status_code == 409 and d.json()["error"]["details"][0]["code"] == "DUPLICATE", d.text)

        # 10) 请求字段封闭
        before = count_ip()
        for extra in [{"cluster_id": cid3}, {"status": "ACTIVE"}, {"deleted_at": None},
                      {"reserved_addresses": []}, {"mode": "auto"}]:
            payload = {"network_interface_id": nic3, "ip_address": "10.0.0.9", **extra}
            e = c.post("/api/ip-addresses/allocate-manual", json=payload)
            check(f"10. extra field {list(extra)[0]} -> 400", e.status_code == 400 and
                  e.json()["error"]["code"] == "VALIDATION_ERROR", e.text[:120])
        ae = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic3, "cluster_id": cid3})
        check("10. auto extra cluster_id -> 400", ae.status_code == 400, ae.text[:120])
        check("10. no write on extra fields", count_ip() == before, f"{count_ip()} vs {before}")

        # 11) NIC 不存在 / 已软删 / 宿主不活跃 → 404 无写入
        nf = c.post("/api/ip-addresses/allocate", json={"network_interface_id": 999999999})
        check("11. nonexistent NIC -> 404", nf.status_code == 404 and nf.json()["error"]["code"] == "NOT_FOUND", nf.text)
        # soft-deleted NIC via raw
        cid4, bm4, _ = chain(c, "c4", [("10.0.0.1", "10.0.0.5")])
        nic_del = raw.execute(
            "INSERT INTO network_interfaces (bare_metal_id,name,technology_type,purpose,deleted_at) "
            "VALUES (%s,'eth9','Ethernet','Business',now()) RETURNING id", (bm4,)).fetchone()[0]
        nf2 = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic_del})
        check("11. deleted NIC -> 404", nf2.status_code == 404, nf2.text)
        # inactive host BM
        cid5, bm5, _ = chain(c, "c5", [("10.0.0.1", "10.0.0.5")])
        raw.execute("UPDATE bare_metals SET deleted_at=now() WHERE id=%s", (bm5,))
        nic5 = raw.execute("SELECT id FROM network_interfaces WHERE bare_metal_id=%s", (bm5,)).fetchone()[0]
        nf3 = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic5})
        check("11. inactive host BM -> 404", nf3.status_code == 404, nf3.text)

        # 12) cluster_id 受控推导直接 DB 校验 + 漂移 0
        cid6, _, nic6 = chain(c, "c6", [("10.0.0.1", "10.0.0.5")])
        a6 = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic6})
        row = raw.execute(
            "SELECT ip.cluster_id, bm.cluster_id FROM ip_addresses ip "
            "JOIN network_interfaces nic ON nic.id=ip.network_interface_id "
            "JOIN bare_metals bm ON bm.id=nic.bare_metal_id WHERE ip.id=%s", (a6.json()["id"],)).fetchone()
        check("12. derived cluster_id matches host BM", row[0] == row[1] == cid6, str(row))
        drift = raw.execute(
            "SELECT ip.id FROM ip_addresses ip JOIN network_interfaces nic ON nic.id=ip.network_interface_id "
            "JOIN bare_metals bm ON bm.id=nic.bare_metal_id WHERE ip.cluster_id <> bm.cluster_id").fetchall()
        check("12. drift query = 0", drift == [], str(drift))

        # 13) 耗尽：填满范围后自动分配 → 409 NO_AVAILABLE_IP，行数不变
        cid7, _, nic7 = chain(c, "c7", [("10.0.0.1", "10.0.0.2")])
        for ipstr in ["10.0.0.1", "10.0.0.2"]:
            c.post("/api/ip-addresses", json={"network_interface_id": nic7, "ip_address": ipstr})
        before = count_ip()
        ex = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic7})
        check("13. exhausted -> 409 NO_AVAILABLE_IP",
              ex.status_code == 409 and ex.json()["error"]["details"][0]["code"] == "NO_AVAILABLE_IP", ex.text)
        check("13. exhausted no write (atomic)", count_ip() == before, f"{count_ip()} vs {before}")

        # 14) 无活跃范围段 → 同耗尽语义
        cid8, _, nic8 = chain(c, "c8")
        ex2 = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic8})
        check("14. no active range -> 409 NO_AVAILABLE_IP",
              ex2.status_code == 409 and ex2.json()["error"]["details"][0]["code"] == "NO_AVAILABLE_IP", ex2.text)

        # 15) F005 对范围外字面仍 201
        cid9, _, nic9 = chain(c, "c9", [("10.0.0.1", "10.0.0.10")])
        f5 = c.post("/api/ip-addresses", json={"network_interface_id": nic9, "ip_address": "10.0.0.20"})
        check("15. F005 out-of-range literal still 201", f5.status_code == 201, f5.text)

        # 17) 多范围段（乱序）跳过已占用取下一个全局最小
        cid10, _, nic10 = chain(c, "c10", [
            ("10.0.0.20", "10.0.0.22"),
            ("10.0.0.1", "10.0.0.3"),
            ("10.0.0.10", "10.0.0.12"),
        ])
        for ipstr in ["10.0.0.1", "10.0.0.2"]:
            c.post("/api/ip-addresses", json={"network_interface_id": nic10, "ip_address": ipstr})
        nxt = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic10})
        check("17. multi-range skip occupied -> 10.0.0.3",
              nxt.status_code == 201 and nxt.json()["ip_address"] == "10.0.0.3", nxt.text)

        # 18) 广播地址不被跳过（范围末端）
        cid11, _, nic11 = chain(c, "c11", [("10.0.0.253", "10.0.0.255")])
        for ipstr in ["10.0.0.253", "10.0.0.254"]:
            c.post("/api/ip-addresses", json={"network_interface_id": nic11, "ip_address": ipstr})
        bcast = c.post("/api/ip-addresses/allocate", json={"network_interface_id": nic11})
        check("18. broadcast 10.0.0.255 not skipped",
              bcast.status_code == 201 and bcast.json()["ip_address"] == "10.0.0.255", bcast.text)

        # 19) 真实线程并发两条自动分配（同一 Cluster）→ 怡一条 201，另一条 409 DUPLICATE
        cid12, _, nic12 = chain(c, "c12", [("10.0.0.1", "10.0.0.2")])
        results: list = []
        barrier = __import__("threading").Barrier(2)

        def race() -> None:
            with httpx.Client(base_url=base, timeout=30.0, cookies=c.cookies) as cc:
                barrier.wait()
                rr = cc.post("/api/ip-addresses/allocate", json={"network_interface_id": nic12})
                results.append((rr.status_code, rr.json()))

        import threading as _t
        threads = [_t.Thread(target=race) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        codes = sorted(s for s, _ in results)
        check("19. concurrent auto: exactly one 201 + one 409, no 5xx", codes == [201, 409], str(codes))
        loser = next(b for s, b in results if s == 409)
        check("19. loser is 409 DUPLICATE",
              loser["error"]["code"] == "CONFLICT" and loser["error"]["details"][0]["code"] == "DUPLICATE",
              str(loser))
        lit_active = fresh_count(
            dsn,
            "SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL AND cluster_id=%s AND ip_address='10.0.0.1'",
            (cid12,),
        )
        check("19. same literal active rows <= 1", lit_active <= 1, str(lit_active))

    # orphan invariant
    orphan = raw.execute(
        "SELECT count(*) FROM ip_addresses ip JOIN network_interfaces nic ON nic.id=ip.network_interface_id "
        "WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL").fetchone()[0]
    check("16. active IP on soft-deleted NIC = 0", orphan == 0, str(orphan))

    raw.close()
    print(f"\n===== HTTP INTEGRATION RESULT: PASS {PASS} FAIL {FAIL} =====")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
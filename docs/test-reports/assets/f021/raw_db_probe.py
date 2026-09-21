"""F021 独立证伪：绕过应用层，直连 PostgreSQL 原始 SQL。

独立 Tester 资产（非实现方测试）。运行前 `alembic upgrade head`。

用法：
    .venv/bin/python docs/test-reports/assets/f021/raw_db_probe.py \
        "postgresql://csm:csm@localhost:55432/csm_f021_tester"
"""

from __future__ import annotations

import sys

import psycopg

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {label}: {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {label}: {detail}")


def reset(conn: psycopg.Connection) -> None:
    conn.execute(
        "TRUNCATE ip_addresses, ip_address_ranges, network_interfaces, bare_metals, clusters "
        "RESTART IDENTITY CASCADE"
    )


def chain(conn: psycopg.Connection, name: str) -> tuple[int, int, int]:
    cid = conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[0]
    bm = conn.execute(
        "INSERT INTO bare_metals (cluster_id, hostname) VALUES (%s, %s) RETURNING id",
        (cid, name + "-n1"),
    ).fetchone()[0]
    nic = conn.execute(
        "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose) "
        "VALUES (%s, 'eth0', 'Ethernet', 'Business') RETURNING id",
        (bm,),
    ).fetchone()[0]
    return cid, bm, nic


def ip(conn: psycopg.Connection, nic: int, cid: int, literal: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (nic, cid, literal),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address) "
        "VALUES (%s, %s, %s) RETURNING id",
        (nic, cid, literal),
    ).fetchone()[0]


def main(url: str) -> int:
    with psycopg.connect(url) as conn:
        conn.autocommit = True
        reset(conn)

        # --- 证伪 1：同 Cluster 两条活跃且字面相同 → 23505（R-IP-001 partial unique 权威） ---
        cid, _, nic = chain(conn, "c1")
        ip(conn, nic, cid, "10.0.0.1")
        try:
            ip(conn, nic, cid, "10.0.0.1")
            check("1. duplicate active literal -> 23505", False, "insert unexpectedly succeeded")
        except psycopg.errors.UniqueViolation as exc:
            check("1. duplicate active literal -> 23505", exc.sqlstate == "23505", exc.sqlstate)

        # --- 证伪 2：数值相同、字面不同（010.0.0.1 vs 10.0.0.1）均成功 ---
        reset(conn)
        cid, _, nic = chain(conn, "c2")
        i1 = ip(conn, nic, cid, "010.0.0.1")
        i2 = ip(conn, nic, cid, "10.0.0.1")
        n = conn.execute("SELECT count(*) FROM ip_addresses WHERE deleted_at IS NULL").fetchone()[0]
        check("2. numeric-equal literal-different coexist", n == 2, f"ids={i1},{i2} active={n}")

        # --- 证伪 2b：软删释放（同字面软删后可再插） ---
        reset(conn)
        cid, _, nic = chain(conn, "c3")
        ip(conn, nic, cid, "10.0.0.9", deleted=True)
        ip(conn, nic, cid, "10.0.0.9")
        check("2b. soft-deleted releases literal", True, "second active insert ok")

        # --- 证伪 3：活跃 IP 挂已软删 NIC 不变式查询非 vacuous ---
        reset(conn)
        cid, bm, nic = chain(conn, "c4")
        nic_del = conn.execute(
            "INSERT INTO network_interfaces (bare_metal_id, name, technology_type, purpose, deleted_at) "
            "VALUES (%s, 'eth1', 'Ethernet', 'Business', now()) RETURNING id",
            (bm,),
        ).fetchone()[0]
        ip(conn, nic_del, cid, "10.0.0.7")
        orphan_q = (
            "SELECT count(*) FROM ip_addresses ip JOIN network_interfaces nic "
            "ON nic.id = ip.network_interface_id WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL"
        )
        detected = conn.execute(orphan_q).fetchone()[0]
        check("3. orphan query detects orphan (non-vacuous)", detected == 1, f"detected={detected}")
        reset(conn)

        # --- 证伪 4：cluster_id 漂移查询 ---
        cid, bm, nic = chain(conn, "c5")
        ip(conn, nic, cid, "10.0.0.3")
        drift_q = (
            "SELECT ip.id FROM ip_addresses ip JOIN network_interfaces nic "
            "ON nic.id = ip.network_interface_id JOIN bare_metals bm ON bm.id = nic.bare_metal_id "
            "WHERE ip.cluster_id <> bm.cluster_id"
        )
        drift = conn.execute(drift_q).fetchall()
        check("4. cluster_id drift = 0 (consistent data)", drift == [], f"rows={drift}")

        # --- 结构证伪：表 / 列 / 唯一索引 / 排他约束 / 触发器 / extension / head ---
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ).fetchall()
        }
        expected_tables = {
            "alembic_version",
            "bare_metals",
            "clusters",
            "containers",
            "ip_addresses",
            "ip_address_ranges",
            "network_interfaces",
            "service_carriers",
            "services",
            "sessions",
            "users",
            "virtual_machines",
        }
        check("5. table set unchanged (no allocation table)", tables == expected_tables,
              f"diff={tables ^ expected_tables}")

        ip_cols = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='ip_addresses' "
                "ORDER BY ordinal_position"
            ).fetchall()
        ]
        check("6. ip_addresses columns unchanged",
              ip_cols == ["id", "network_interface_id", "cluster_id", "ip_address", "created_at",
                          "updated_at", "deleted_at"],
              str(ip_cols))

        # 非 PK 的唯一索引集合（排除主键）。
        uniq_ip = {
            r[0]
            for r in conn.execute(
                "SELECT i.relname FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_class t ON t.oid = x.indrelid "
                "WHERE t.relname = 'ip_addresses' AND x.indisunique AND NOT x.indisprimary"
            ).fetchall()
        }
        check("7. ip_addresses non-PK unique indexes == {ux_ip_addresses_cluster_ip_active}",
              uniq_ip == {"ux_ip_addresses_cluster_ip_active"}, str(uniq_ip))

        excl = conn.execute(
            "SELECT conname FROM pg_constraint WHERE contype='x' ORDER BY conname"
        ).fetchall()
        check("8. exclusion constraints == {ex_ip_address_ranges_active_no_overlap}",
              [r[0] for r in excl] == ["ex_ip_address_ranges_active_no_overlap"], str(excl))

        trig = conn.execute(
            "SELECT count(*) FROM information_schema.triggers WHERE trigger_schema='public'"
        ).fetchone()[0]
        check("9. no triggers", trig == 0, f"triggers={trig}")

        ext = {r[0] for r in conn.execute("SELECT extname FROM pg_extension").fetchall()}
        check("10. btree_gist present", "btree_gist" in ext, str(ext))

        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        check("11. migration head still 0009", head == "0009_f020_ip_address_ranges", head)

        # 无 CASCADE FK
        cascades = conn.execute(
            "SELECT conname FROM pg_constraint WHERE contype='f' AND confdeltype='c'"
        ).fetchall()
        check("12. no ON DELETE CASCADE", cascades == [], str(cascades))

    print(f"\n===== RAW DB PROBE: PASS {PASS} FAIL {FAIL} =====")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
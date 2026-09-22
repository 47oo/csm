#!/usr/bin/env python3
"""F022 independent raw-DB falsification (bypasses the application layer).

Run against a dedicated throwaway DB (csm_f022_tester), never production.
Prints the raw SQL + raw output / SQLSTATE for each probe (Database Handoff
V-1 ~ V-25; Tester task item 9).

Usage:
    .venv/bin/python docs/test-reports/assets/f022/raw_db_probe.py \
        "postgresql://csm:csm@localhost:55432/csm_f022_tester"
"""
from __future__ import annotations

import sys

import psycopg

DSN = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "postgresql://csm:csm@localhost:55432/csm_f022_tester"
)

results: list[tuple[str, bool, str]] = []


def record(pid: str, expected: str, outcome: str, ok: bool) -> None:
    results.append((pid, ok, outcome))
    print(f"\n===== {pid} ===== expected: {expected}")
    print(f"     RESULT: {outcome}")
    print(f"     VERDICT: {'PASS' if ok else 'FAIL'}")


def new_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id",
            (name,),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]


def new_range(
    conn,
    cluster_id: int,
    start_ip: int,
    end_ip: int,
    *,
    name: str | None = None,
    subnet_mask: str | None = None,
    vlan: int | None = None,
    deleted: bool = False,
) -> int:
    cols = "cluster_id, start_ip, end_ip, name, subnet_mask, vlan"
    vals = "%s, %s, %s, %s, %s, %s"
    params: list[object] = [cluster_id, start_ip, end_ip, name, subnet_mask, vlan]
    if deleted:
        cols += ", deleted_at"
        vals += ", now()"
    return conn.execute(
        f"INSERT INTO ip_address_ranges ({cols}) VALUES ({vals}) RETURNING id", params
    ).fetchone()[0]


with psycopg.connect(DSN) as conn:
    conn.autocommit = True

    # ---- V-11 same cluster two ACTIVE same name -> 23505 -----------------------
    c = new_cluster(conn, "f022-11")
    new_range(conn, c, 10, 20, name="业务网")
    try:
        conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, name) "
            "VALUES (%s,%s,%s,%s)",
            (c, 30, 40, "业务网"),
        )
        record("V-11", "23505 UniqueViolation", "inserted (NO ERROR)", False)
    except psycopg.errors.UniqueViolation as exc:
        record("V-11", "23505", f"{type(exc).__name__} sqlstate={exc.sqlstate}", exc.sqlstate == "23505")
    except psycopg.Error as exc:  # noqa: BLE001
        record("V-11", "23505", f"{type(exc).__name__} sqlstate={exc.sqlstate}", False)

    # ---- V-12 case-sensitive web / Web both accepted ---------------------------
    c = new_cluster(conn, "f022-12")
    try:
        a = new_range(conn, c, 10, 20, name="web")
        b = new_range(conn, c, 30, 40, name="Web")
        record("V-12", "web / Web both succeed (case sensitive)", f"ids={a},{b}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-12", "both succeed", f"{type(exc).__name__}: {exc}", False)

    # ---- V-13 soft-deleted row releases name; NULL names do not collide ---------
    c = new_cluster(conn, "f022-13")
    old = new_range(conn, c, 10, 20, name="release")
    conn.execute("UPDATE ip_address_ranges SET deleted_at = now() WHERE id = %s", (old,))
    try:
        nid = new_range(conn, c, 50, 60, name="release")
        record("V-13a", "soft-deleted name released", f"new_active_id={nid}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-13a", "success", f"{type(exc).__name__}: {exc}", False)
    try:
        n1 = new_range(conn, c, 70, 80, name=None)
        n2 = new_range(conn, c, 90, 100, name=None)
        record("V-13b", "multiple NULL names allowed", f"ids={n1},{n2}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-13b", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-14 cross-cluster same name succeeds ----------------------------------
    ca = new_cluster(conn, "f022-14a")
    cb = new_cluster(conn, "f022-14b")
    try:
        a = new_range(conn, ca, 10, 20, name="业务网")
        b = new_range(conn, cb, 10, 20, name="业务网")
        record("V-14", "cross-cluster same name succeeds", f"ids={a},{b}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-14", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-15 vlan out of range -> 23514 ----------------------------------------
    for vlan in (0, 4095, 5000, -1):
        c = new_cluster(conn, f"f022-15-{vlan}")
        try:
            new_range(conn, c, 10, 20, vlan=vlan)
            record(f"V-15[{vlan}]", "23514", "inserted (NO ERROR)", False)
        except psycopg.errors.CheckViolation as exc:
            record(f"V-15[{vlan}]", "23514", f"sqlstate={exc.sqlstate}", exc.sqlstate == "23514")
        except psycopg.Error as exc:  # noqa: BLE001
            record(f"V-15[{vlan}]", "23514", f"{type(exc).__name__} sqlstate={exc.sqlstate}", False)

    # ---- V-16 vlan 1 / 4094 / NULL accepted -------------------------------------
    c = new_cluster(conn, "f022-16")
    try:
        ids = [new_range(conn, c, 10, 20, vlan=1), new_range(conn, c, 30, 40, vlan=4094)]
        ids.append(new_range(conn, c, 50, 60, vlan=None))
        record("V-16", "vlan 1/4094/NULL all accepted", f"ids={ids}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-16", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-17 empty / whitespace / long names accepted (no CHECK; not "legal") --
    c = new_cluster(conn, "f022-17")
    try:
        empty = new_range(conn, c, 10, 20, name="")
        spaced = new_range(conn, c, 30, 40, name="  业务网  ")
        longn = new_range(conn, c, 50, 60, name="x" * 5000)
        record("V-17", "empty / whitespace / long names accepted (no DB CHECK)",
               f"ids={empty},{spaced},{longn}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-17", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-18 arbitrary subnet_mask string accepted by DB ------------------------
    c = new_cluster(conn, "f022-18")
    try:
        bad = new_range(conn, c, 10, 20, subnet_mask="255.0.255.0")
        garbage = new_range(conn, c, 30, 40, subnet_mask="not-a-mask")
        record("V-18", "DB accepts any subnet_mask string (app-layer only)",
               f"ids={bad},{garbage}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-18", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-19 nonexistent cluster -> 23503 --------------------------------------
    try:
        new_range(conn, 999999999, 10, 20)
        record("V-19", "23503", "inserted (NO ERROR)", False)
    except psycopg.errors.ForeignKeyViolation as exc:
        record("V-19", "23503", f"sqlstate={exc.sqlstate}", exc.sqlstate == "23503")
    except psycopg.Error as exc:  # noqa: BLE001
        record("V-19", "23503", f"{type(exc).__name__} sqlstate={exc.sqlstate}", False)

    # ---- V-20 soft-delete releases BOTH name and overlap -------------------------
    c = new_cluster(conn, "f022-20")
    old = new_range(conn, c, 100, 200, name="shared")
    conn.execute("UPDATE ip_address_ranges SET deleted_at = now() WHERE id = %s", (old,))
    try:
        nid = new_range(conn, c, 150, 250, name="shared")
        record("V-20", "soft-deleted releases name + overlap", f"new_active_id={nid}", True)
    except Exception as exc:  # noqa: BLE001
        record("V-20", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- V-1 column set exactly 10, nullable + no default on the three -----------
    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable, column_default, collation_name "
        "FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='ip_address_ranges' ORDER BY ordinal_position"
    ).fetchall()
    cols = [r[0] for r in rows]
    expected_cols = [
        "id", "cluster_id", "start_ip", "end_ip", "created_at", "updated_at",
        "deleted_at", "name", "subnet_mask", "vlan",
    ]
    forbidden = {"status", "description", "purpose", "cidr", "prefix_length", "ipv6",
                 "gateway", "dhcp", "dns", "utilization", "capacity", "usage",
                 "assigned_to", "assigned_at", "reclaimed_at", "network_address",
                 "broadcast_address"}
    ok = cols == expected_cols and not (forbidden & set(cols))
    record("V-1", f"columns exactly {expected_cols}, no forbidden", f"{cols}", ok)

    by = {r[0]: r for r in rows}
    three_ok = all(
        by[n][2] == "YES" and by[n][3] is None for n in ("name", "subnet_mask", "vlan")
    )
    types_ok = (
        by["name"][1] == "text" and by["subnet_mask"][1] == "text" and by["vlan"][1] == "integer"
    )
    record("V-2a", "name/subnet_mask/vlan nullable, no default", f"{[by[n][2:4] for n in ('name','subnet_mask','vlan')]}", three_ok)
    record("V-2b", "data types text/text/integer", f"{[by[n][1] for n in ('name','subnet_mask','vlan')]}", types_ok)

    # no explicit collation on any column
    colls = {r[0]: r[4] for r in rows}
    record("V-10b", "all columns collation_name IS NULL", f"{colls}", all(v is None for v in colls.values()))

    # ---- V-3 PK ----------------------------------------------------------------
    pk = conn.execute(
        "SELECT conname, contype FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
        "WHERE t.relname='ip_address_ranges' AND contype='p'"
    ).fetchall()
    record("V-3", "PK exactly pk_ip_address_ranges", f"{pk}", pk == [("pk_ip_address_ranges", "p")])

    # ---- V-4 CHECK set ----------------------------------------------------------
    cks = conn.execute(
        "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "JOIN pg_class t ON t.oid=c.conrelid WHERE t.relname='ip_address_ranges' AND contype='c' "
        "ORDER BY conname"
    ).fetchall()
    check_names = {r[0] for r in cks}
    vlan_def = dict(cks).get("ck_ip_address_ranges_vlan_range", "")
    ok = check_names == {"ck_ip_address_ranges_bounds", "ck_ip_address_ranges_vlan_range"} and all(
        tok in vlan_def for tok in ("vlan", "1", "4094", "IS NULL")
    )
    record("V-4", "CHECK set exactly {bounds, vlan_range}, vlan def has vlan/1/4094/IS NULL",
           f"{cks}", ok)

    # ---- V-5 FK -----------------------------------------------------------------
    fk = conn.execute(
        "SELECT conname, confdeltype, confupdtype FROM pg_constraint c "
        "JOIN pg_class t ON t.oid=c.conrelid WHERE t.relname='ip_address_ranges' AND contype='f'"
    ).fetchall()
    record("V-5", "FK exactly fk_ip_address_ranges_cluster RESTRICT/RESTRICT",
           f"{fk}", fk == [("fk_ip_address_ranges_cluster", "r", "r")])

    # ---- V-6 unique index set + indexdef ----------------------------------------
    idx = conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
        "AND tablename='ip_address_ranges'"
    ).fetchall()
    # "UNIQUE indexes" here means unique indexes other than the PRIMARY KEY's
    # implicit unique index (pg_indexes lists pk_ip_address_ranges too).
    uniques = {r[0]: r[1] for r in idx if "UNIQUE" in r[1] and r[0] != "pk_ip_address_ranges"}
    d = uniques.get("ux_ip_address_ranges_cluster_name_active", "")
    ok = set(uniques) == {"ux_ip_address_ranges_cluster_name_active"}
    ok = ok and "UNIQUE" in d and "(cluster_id, name)" in d
    ok = ok and "deleted_at IS NULL" in d and "name IS NOT NULL" in d
    ok = ok and "COLLATE" not in d and "lower(" not in d
    record("V-6", "unique indexes exactly {ux_...}; indexdef has predicate, no COLLATE/lower",
           f"uniques={sorted(uniques)} def={d}", ok)

    # ---- V-7 exclusion constraint ------------------------------------------------
    ex = conn.execute(
        "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "JOIN pg_class t ON t.oid=c.conrelid WHERE t.relname='ip_address_ranges' AND contype='x'"
    ).fetchall()
    record("V-7", "exclusion exactly ex_ip_address_ranges_active_no_overlap",
           f"{ex}", {r[0] for r in ex} == {"ex_ip_address_ranges_active_no_overlap"})

    # ---- V-8 normal index --------------------------------------------------------
    record("V-8", "normal index ix_ip_address_ranges_cluster_id present",
           f"{sorted(r[0] for r in idx)}", "ix_ip_address_ranges_cluster_id" in {r[0] for r in idx})

    # ---- V-9 no CASCADE anywhere -------------------------------------------------
    casc = conn.execute(
        "SELECT conname, confdeltype FROM pg_constraint WHERE confdeltype='c'"
    ).fetchall()
    record("V-9", "no CASCADE FKs in whole DB", f"cascades={casc}", casc == [])

    # ---- V-10 no triggers, no collate -------------------------------------------
    trig = conn.execute(
        "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "WHERE c.relname='ip_address_ranges' AND NOT t.tgisinternal"
    ).fetchall()
    record("V-10a", "no user triggers on ip_address_ranges", f"triggers={trig}", trig == [])

    # ---- R-1..R-5 invariant regressions (expect 0) ------------------------------
    r1 = conn.execute(
        "SELECT a.id, b.id FROM ip_address_ranges a JOIN ip_address_ranges b "
        "ON a.cluster_id=b.cluster_id AND a.id<b.id "
        "AND a.deleted_at IS NULL AND b.deleted_at IS NULL "
        "AND a.start_ip<=b.end_ip AND a.end_ip>=b.start_ip"
    ).fetchall()
    record("R-1", "active overlap drift = 0 rows", f"rows={r1}", r1 == [])

    r2 = conn.execute(
        "SELECT count(*) FROM ip_address_ranges r JOIN clusters c ON c.id=r.cluster_id "
        "WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL"
    ).fetchone()[0]
    record("R-2", "active range under soft-deleted cluster = 0", f"count={r2}", r2 == 0)

    r3 = conn.execute(
        "SELECT ip.id FROM ip_addresses ip JOIN network_interfaces nic ON nic.id=ip.network_interface_id "
        "JOIN bare_metals bm ON bm.id=nic.bare_metal_id WHERE ip.cluster_id<>bm.cluster_id"
    ).fetchall()
    record("R-3", "F005 drift = 0 rows", f"rows={r3}", r3 == [])

    r4 = conn.execute(
        "SELECT a.id, b.id, a.name FROM ip_address_ranges a JOIN ip_address_ranges b "
        "ON a.cluster_id=b.cluster_id AND a.id<b.id "
        "AND a.deleted_at IS NULL AND b.deleted_at IS NULL "
        "AND a.name IS NOT NULL AND b.name IS NOT NULL AND a.name=b.name"
    ).fetchall()
    record("R-4", "same-cluster active duplicate name = 0", f"rows={r4}", r4 == [])

    r5 = conn.execute(
        "SELECT id FROM ip_address_ranges WHERE vlan IS NOT NULL AND (vlan<1 OR vlan>4094)"
    ).fetchall()
    record("R-5", "vlan out of range = 0", f"rows={r5}", r5 == [])

    # ---- V-26 no backfill (all rows inserted by migration have NULL metadata) ---
    #   In this probe DB every row was inserted by us; check the migration predicate
    #   indirectly: three columns exist and older F020-style INSERTs default to NULL.
    c = new_cluster(conn, "f022-26")
    nid = new_range(conn, c, 1000, 2000)
    vals = conn.execute(
        "SELECT name, subnet_mask, vlan FROM ip_address_ranges WHERE id=%s", (nid,)
    ).fetchone()
    record("V-26", "metadata columns default to NULL when omitted (no backfill)", f"{vals}", vals == (None, None, None))

print("\n\n================ SUMMARY ================")
passed = sum(1 for _, ok, _ in results if ok)
failed = len(results) - passed
for pid, ok, outcome in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {pid}: {outcome}")
print(f"\n===== RAW DB PROBE RESULT: PASS {passed} FAIL {failed} =====")
sys.exit(0 if failed == 0 else 1)
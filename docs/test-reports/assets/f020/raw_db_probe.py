#!/usr/bin/env python3
"""Independent raw-DB falsification for F020 ip_address_ranges (bypasses app layer).

Run against a dedicated throwaway DB (csm_tester), never the production DB.
Prints raw SQL + raw output/exception for each probe.
"""
from __future__ import annotations

import sys

import psycopg

DSN = sys.argv[1] if len(sys.argv) > 1 else "postgresql://csm:csm@localhost:55432/csm_tester"

results: list[tuple[str, str, str]] = []


def record(pid: str, expected: str, outcome: str, ok: bool) -> None:
    results.append((pid, expected, outcome))
    print(f"\n===== {pid} ===== expected: {expected}")
    print(f"     RESULT: {outcome}")
    print(f"     VERDICT: {'PASS' if ok else 'FAIL'}")


def new_cluster(conn, name: str, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO clusters (name, deleted_at) VALUES (%s, now()) RETURNING id", (name,)
        ).fetchone()[0]
    return conn.execute("INSERT INTO clusters (name) VALUES (%s) RETURNING id", (name,)).fetchone()[0]


def new_range(conn, cluster_id: int, start_ip: int, end_ip: int, *, deleted: bool = False) -> int:
    if deleted:
        return conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, deleted_at) "
            "VALUES (%s, %s, %s, now()) RETURNING id",
            (cluster_id, start_ip, end_ip),
        ).fetchone()[0]
    return conn.execute(
        "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip) VALUES (%s, %s, %s) RETURNING id",
        (cluster_id, start_ip, end_ip),
    ).fetchone()[0]


with psycopg.connect(DSN) as conn:
    conn.autocommit = True

    # ---- 1) same cluster two ACTIVE overlapping ranges -> 23P01 -----------------
    c = new_cluster(conn, "probe-1")
    sql = "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip) VALUES (%s,%s,%s)"
    new_range(conn, c, 10, 20)
    try:
        conn.execute(sql, (c, 20, 30))  # shares endpoint 20
        record("1", "23P01 ExclusionViolation on shared-endpoint overlap", "inserted (NO ERROR)", False)
    except psycopg.errors.ExclusionViolation as exc:
        record("1", "23P01", f"{type(exc).__name__} sqlstate={exc.sqlstate}", exc.sqlstate == "23P01")

    # ---- 2) cross-cluster IDENTICAL range -> success ----------------------------
    a = new_cluster(conn, "probe-2a")
    b = new_cluster(conn, "probe-2b")
    new_range(conn, a, 100, 200)
    try:
        rid = new_range(conn, b, 100, 200)
        record("2", "cross-cluster identical range succeeds", f"inserted id={rid}", True)
    except Exception as exc:  # noqa: BLE001
        record("2", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- 3) start_ip > end_ip -> 23514 ------------------------------------------
    c = new_cluster(conn, "probe-3")
    try:
        new_range(conn, c, 30, 10)
        record("3", "23514 CheckViolation", "inserted (NO ERROR)", False)
    except psycopg.errors.CheckViolation as exc:
        record("3", "23514", f"{type(exc).__name__} sqlstate={exc.sqlstate}", exc.sqlstate == "23514")

    # ---- 4) out-of-range values -> 23514 ----------------------------------------
    for start, end, label in [(-1, 10, "start_ip<0"), (0, 4294967296, "end_ip>4294967295")]:
        c = new_cluster(conn, f"probe-4-{label}")
        try:
            new_range(conn, c, start, end)
            record(f"4[{label}]", "23514", "inserted (NO ERROR)", False)
        except psycopg.errors.CheckViolation as exc:
            record(f"4[{label}]", "23514", f"sqlstate={exc.sqlstate}", exc.sqlstate == "23514")

    # ---- 5) soft-deleted row releases overlap (predicate works) -----------------
    c = new_cluster(conn, "probe-5")
    deleted = new_range(conn, c, 300, 400, deleted=True)
    try:
        active = new_range(conn, c, 350, 450)
        record(
            "5",
            "soft-deleted predicate releases overlap; overlapping active insert succeeds",
            f"deleted_id={deleted} new_active_id={active}",
            True,
        )
    except Exception as exc:  # noqa: BLE001
        record("5", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- 5b) adjacency [1,10] / [11,20] is NOT overlap (Product NQ-A) -----------
    c = new_cluster(conn, "probe-5b")
    try:
        new_range(conn, c, 1, 10)
        new_range(conn, c, 11, 20)
        record("5b", "adjacent closed ranges do not overlap", "both inserted", True)
    except Exception as exc:  # noqa: BLE001
        record("5b", "success", f"{type(exc).__name__}: {exc}", False)

    # ---- 6) column set is exactly 7, no forbidden columns -----------------------
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ip_address_ranges' ORDER BY ordinal_position"
        ).fetchall()
    ]
    expected_cols = {
        "id", "cluster_id", "start_ip", "end_ip", "created_at", "updated_at", "deleted_at",
    }
    forbidden = {"status", "name", "description", "cidr", "prefix_length", "ipv6"}
    ok = set(cols) == expected_cols and not (forbidden & set(cols)) and len(cols) == 7
    print(f"\n{cols}")
    record("6", "exactly 7 columns, no status/name/description/CIDR/IPv6", f"{cols}", ok)

    # ---- 7) constraints + no triggers -------------------------------------------
    cons = conn.execute(
        "SELECT conname, contype FROM pg_constraint WHERE conrelid='ip_address_ranges'::regclass "
        "ORDER BY conname"
    ).fetchall()
    trig = conn.execute(
        "SELECT count(*) FROM information_schema.triggers WHERE event_object_table='ip_address_ranges'"
    ).fetchone()[0]
    ex = [r for r in cons if r[1] == "x"]
    ck = [r for r in cons if r[1] == "c"]
    ok = (
        any(r[0] == "ex_ip_address_ranges_active_no_overlap" for r in ex)
        and any(r[0] == "ck_ip_address_ranges_bounds" for r in ck)
        and trig == 0
    )
    print(f"\n{cons}\ntriggers={trig}")
    record("7", "EXCLUDE 'x' name present, CHECK present, 0 triggers", f"cons={cons} triggers={trig}", ok)

    # ---- 8) non-overlap drift query = 0 -----------------------------------------
    q8 = """
    SELECT a.id, b.id FROM ip_address_ranges a
    JOIN ip_address_ranges b
      ON a.cluster_id=b.cluster_id AND a.id<b.id
     AND a.deleted_at IS NULL AND b.deleted_at IS NULL
     AND a.start_ip<=b.end_ip AND a.end_ip>=b.start_ip
    """
    rows8 = conn.execute(q8).fetchall()
    record("8", "no active overlap drift (0 rows)", f"rows={rows8}", rows8 == [])

    # ---- 9) active range under soft-deleted cluster = 0 -------------------------
    dc = new_cluster(conn, "probe-9-deleted", deleted=True)
    # FK only sees physical existence; DB allows it. App layer prevents it. We assert
    # that a raw insert CAN happen (DB does not guarantee) and the regression query
    # detects it -> non-vacuous. Then clean up.
    try:
        raw = new_range(conn, dc, 1, 2)
        detected = conn.execute(
            "SELECT count(*) FROM ip_address_ranges r JOIN clusters c ON c.id=r.cluster_id "
            "WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL"
        ).fetchone()[0]
        # It is expected that the DB does NOT prevent this (documented non-guarantee);
        # the drift query must detect it. Remove the injected row afterward.
        conn.execute("DELETE FROM ip_address_ranges WHERE id=%s", (raw,))
        record(
            "9",
            "DB does not guarantee orphan; regression query detects it (non-vacuous)",
            f"raw_orphan_id={raw} detected_count={detected}",
            detected >= 1,
        )
    except Exception as exc:  # noqa: BLE001
        record("9", "inject + detect", f"{type(exc).__name__}: {exc}", False)

    # ---- extra: FK violate 23503, no CASCADE, no UNIQUE index -------------------
    try:
        new_range(conn, 999999999, 1, 2)
        record("E1", "23503 FK violation", "inserted (NO ERROR)", False)
    except psycopg.errors.ForeignKeyViolation as exc:
        record("E1", "23503", f"sqlstate={exc.sqlstate}", exc.sqlstate == "23503")

    cascades = conn.execute(
        "SELECT conname FROM pg_constraint WHERE contype='f' AND confdeltype='c'"
    ).fetchall()
    idx = [r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename='ip_address_ranges'").fetchall()]
    record("E2", "no CASCADE FK anywhere; no ux_ index", f"cascades={cascades} indexes={idx}",
           cascades == [] and not any(n.startswith("ux_") for n in idx))

    ext = conn.execute("SELECT extname FROM pg_extension WHERE extname='btree_gist'").fetchone()
    record("E3", "btree_gist extension present", f"{ext}", ext is not None)

print("\n\n================ SUMMARY ================")
for pid, expected, outcome in results:
    print(f"{pid:12s} | {expected[:55]:55s} | {outcome}")
#!/usr/bin/env python3
"""F022 adversarial falsification: prove the key DB constraints are the real
authority (and that the raw probe would fail without them), then restore the
exact original DDL byte-for-byte.

Run against the throwaway DB csm_f022_tester. Never production.
"""
from __future__ import annotations

import sys

import psycopg

DSN = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "postgresql://csm:csm@localhost:55432/csm_f022_tester"
)

INDEX_DDL = (
    "CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active "
    "ON public.ip_address_ranges USING btree (cluster_id, name) "
    "WHERE ((deleted_at IS NULL) AND (name IS NOT NULL))"
)
CHECK_DDL = (
    "ALTER TABLE public.ip_address_ranges "
    "ADD CONSTRAINT ck_ip_address_ranges_vlan_range "
    "CHECK (((vlan IS NULL) OR ((vlan >= 1) AND (vlan <= 4094))))"
)


def indexdef(conn) -> str | None:
    return conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ux_ip_address_ranges_cluster_name_active'"
    ).fetchone()[0] if conn.execute(
        "SELECT 1 FROM pg_indexes WHERE indexname='ux_ip_address_ranges_cluster_name_active'"
    ).fetchone() else None


def checkdef(conn) -> str | None:
    row = conn.execute(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "JOIN pg_class t ON t.oid=c.conrelid "
        "WHERE t.relname='ip_address_ranges' AND c.conname='ck_ip_address_ranges_vlan_range'"
    ).fetchone()
    return row[0] if row else None


with psycopg.connect(DSN) as conn:
    conn.autocommit = True

    print("BEFORE indexdef:", indexdef(conn))
    print("BEFORE checkdef:", checkdef(conn))

    # ---- 1) drop partial unique index -> duplicate name insert succeeds --------
    import time

    cname = f"adv-dup-{int(time.time() * 1000)}"
    c = conn.execute(
        "INSERT INTO clusters (name) VALUES (%s) RETURNING id", (cname,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, name) VALUES (%s,1,2,'dup')",
        (c,),
    )
    conn.execute("DROP INDEX ux_ip_address_ranges_cluster_name_active")
    try:
        conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, name) "
            "VALUES (%s,3,4,'dup')",
            (c,),
        )
        print("1) after DROP INDEX duplicate name insert: SUCCEEDED  -> probe V-11 would FAIL (index is authority)")
    except Exception as exc:  # noqa: BLE001
        print("1) UNEXPECTED:", type(exc).__name__, exc)

    # remove the injected duplicate row BEFORE restoring the index (else CREATE fails)
    conn.execute(
        "DELETE FROM ip_address_ranges WHERE cluster_id=%s AND name='dup' AND start_ip=3",
        (c,),
    )
    # restore index exactly
    conn.execute(INDEX_DDL)
    print("   restored indexdef:", indexdef(conn))

    # ---- 2) drop vlan CHECK -> vlan=0 insert succeeds ---------------------------
    conn.execute(
        "ALTER TABLE public.ip_address_ranges DROP CONSTRAINT ck_ip_address_ranges_vlan_range"
    )
    try:
        conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, vlan) VALUES (%s,10,20,0)",
            (c,),
        )
        print("2) after DROP CHECK vlan=0 insert: SUCCEEDED  -> probe V-15 would FAIL (CHECK is authority)")
    except Exception as exc:  # noqa: BLE001
        print("2) UNEXPECTED:", type(exc).__name__, exc)

    conn.execute(
        "DELETE FROM ip_address_ranges WHERE cluster_id=%s AND vlan=0 AND start_ip=10",
        (c,),
    )
    conn.execute(CHECK_DDL)
    print("   restored checkdef:", checkdef(conn))

    # ---- 3) confirm both constraints reject again after restore ------------------
    try:
        conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, name) VALUES (%s,5,6,'dup')",
            (c,),
        )
        print("3a) duplicate after restore: SUCCEEDED (BAD)")
    except psycopg.errors.UniqueViolation as exc:
        print("3a) duplicate after restore -> 23505 OK", exc.sqlstate)
    try:
        conn.execute(
            "INSERT INTO ip_address_ranges (cluster_id, start_ip, end_ip, vlan) VALUES (%s,30,40,0)",
            (c,),
        )
        print("3b) vlan=0 after restore: SUCCEEDED (BAD)")
    except psycopg.errors.CheckViolation as exc:
        print("3b) vlan=0 after restore -> 23514 OK", exc.sqlstate)

    print("\nafter indexdef:", indexdef(conn))
    print("after checkdef:", checkdef(conn))
    assert indexdef(conn) == (
        "CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active ON public.ip_address_ranges "
        "USING btree (cluster_id, name) WHERE ((deleted_at IS NULL) AND (name IS NOT NULL))"
    ), "index not restored byte-for-byte"
    assert checkdef(conn) == (
        "CHECK (((vlan IS NULL) OR ((vlan >= 1) AND (vlan <= 4094))))"
    ), "check not restored byte-for-byte"
    print("\nRESTORE VERIFIED (indexdef + checkdef identical to original).")
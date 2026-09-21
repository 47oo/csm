#!/usr/bin/env python3
"""Real HTTP integration (uvicorn + PostgreSQL) driving the F020 product API.

Verifies AC-01..AC-27 contract semantics and error branches, plus DB-side
read-only / no-partial-write / no-cascade assertions. Does not import app code.
"""
from __future__ import annotations

import sys

import httpx
import psycopg

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
DB = sys.argv[2] if len(sys.argv) > 2 else "postgresql://csm:csm@localhost:55432/csm_integration"

passed = 0
failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed.append(name)
        print(f"FAIL  {name}  {detail}")


READ_FIELDS = {"id", "cluster_id", "start_ip", "end_ip", "created_at", "updated_at"}

admin = httpx.Client(base_url=BASE, timeout=20.0)
anon = httpx.Client(base_url=BASE, timeout=20.0)
db = psycopg.connect(DB, autocommit=True)

r = admin.post("/api/auth/login", json={"username": "tester", "password": "integration-pass-123"})
check("login 200", r.status_code == 200, r.text)

# ---------------- AC-01 unauthenticated ----------------
codes = [
    anon.get("/api/ip-address-ranges").status_code,
    anon.get("/api/ip-address-ranges/1").status_code,
    anon.post("/api/ip-address-ranges", json={"cluster_id": 1, "start_ip": "1.2.3.4", "end_ip": "1.2.3.5"}).status_code,
    anon.patch("/api/ip-address-ranges/1", json={"start_ip": "1.2.3.4"}).status_code,
    anon.delete("/api/ip-address-ranges/1").status_code,
]
check("AC-01 all 5 endpoints unauthenticated -> 401", codes == [401] * 5, str(codes))
check("AC-01 body has UNAUTHENTICATED", anon.get("/api/ip-address-ranges").json()["error"]["code"] == "UNAUTHENTICATED")


def new_cluster(name):
    return admin.post("/api/clusters", json={"name": name}).json()["id"]


def new_bm(cid, hostname="n1"):
    return admin.post("/api/bare-metals", json={"cluster_id": cid, "hostname": hostname}).json()["id"]


def new_nic(bmid, name="eth0"):
    return admin.post(
        "/api/network-interfaces",
        json={"bare_metal_id": bmid, "name": name, "technology_type": "Ethernet", "purpose": "Business"},
    ).json()["id"]


def new_ip(nic_id, ip):
    return admin.post("/api/ip-addresses", json={"network_interface_id": nic_id, "ip_address": ip})


def new_range(cid, start, end):
    return admin.post("/api/ip-address-ranges", json={"cluster_id": cid, "start_ip": start, "end_ip": end})


# ---------------- AC-20 global empty ----------------
r = admin.get("/api/ip-address-ranges")
check("AC-20 global empty 200/[]/total0", r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0, r.text)

cid = new_cluster("ic-a")
cid2 = new_cluster("ic-b")
cid3 = new_cluster("ic-c")

# ---------------- AC-02 field closure ----------------
r = new_range(cid, "10.0.0.1", "10.0.0.255")
check("AC-02 create 201", r.status_code == 201, r.text)
body = r.json()
check("AC-02 response fields exactly 6", set(body) == READ_FIELDS, str(set(body)))
check("AC-02 no status/deleted_at/name", not ({"status", "deleted_at", "name", "description"} & set(body)))
range_id = body["id"]

# ---------------- AC-09 normalization ----------------
r = new_range(cid2, "010.000.000.001", "010.000.000.009")
check("AC-09 leading zeros normalized", r.status_code == 201 and r.json()["start_ip"] == "10.0.0.1" and r.json()["end_ip"] == "10.0.0.9", r.text)
stored = db.execute("SELECT start_ip,end_ip FROM ip_address_ranges WHERE id=%s", (r.json()["id"],)).fetchone()
check("AC-09 stored canonical numeric", stored == (167772161, 167772169), str(stored))

# ---------------- AC-03 request closure + no write ----------------
before = db.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0]
r = admin.post("/api/ip-address-ranges", json={"cluster_id": cid, "start_ip": "10.1.0.1", "end_ip": "10.1.0.2", "name": "pool"})
after = db.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0]
check("AC-03 unknown field -> 400 VALIDATION_ERROR", r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR", r.text)
check("AC-03 no record written", before == after)

# ---------------- AC-04 cluster_id required ----------------
ok = all(
    admin.post("/api/ip-address-ranges", json=p).status_code == 400
    for p in ({"start_ip": "10.2.0.1", "end_ip": "10.2.0.2"}, {"cluster_id": "x", "start_ip": "10.2.0.1", "end_ip": "10.2.0.2"}, {"cluster_id": None, "start_ip": "10.2.0.1", "end_ip": "10.2.0.2"})
)
check("AC-04 missing/invalid cluster_id -> 400", ok)

# ---------------- AC-05 active cluster ----------------
r = new_range(999999999, "10.3.0.1", "10.3.0.2")
check("AC-05 nonexistent cluster -> 404", r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND", r.text)
dcid = db.execute("INSERT INTO clusters (name, deleted_at) VALUES ('ic-deleted', now()) RETURNING id").fetchone()[0]
r = new_range(dcid, "10.3.0.1", "10.3.0.2")
check("AC-05 soft-deleted cluster -> 404 (no 5xx)", r.status_code == 404, r.text)

# ---------------- AC-06/07/08 ----------------
ok6 = all(
    admin.post("/api/ip-address-ranges", json=p).status_code == 400
    for p in ({"cluster_id": cid, "end_ip": "10.4.0.2"}, {"cluster_id": cid, "start_ip": "10.4.0.1"}, {"cluster_id": cid, "start_ip": 123, "end_ip": "10.4.0.2"})
)
check("AC-06 start/end required -> 400", ok6)
ok7 = new_range(cid, "10.4.0.10", "10.4.0.1").status_code == 400
check("AC-07 start>end -> 400", ok7)
bad_ips = ["10.0.0.256", "10.0.0", "abc", "1.2.3.4/24", "2001:db8::1", ""]
ok8 = all(new_range(cid, b, "10.9.9.9").status_code == 400 for b in bad_ips)
check("AC-08 illegal IPv4 -> 400", ok8)

# ---------------- AC-10 overlap 409 OVERLAP ----------------
r = new_range(cid, "10.0.0.200", "10.0.1.10")  # overlaps 10.0.0.1-255
d = r.json()["error"]
check("AC-10 same-cluster overlap -> 409 CONFLICT", r.status_code == 409 and d["code"] == "CONFLICT", r.text)
check("AC-10 details code OVERLAP", any(x.get("code") == "OVERLAP" for x in d["details"]), str(d))
shared_end = new_range(cid, "10.0.0.255", "10.0.0.255")
check("AC-10 shared endpoint counts as overlap", shared_end.status_code == 409)

# ---------------- AC-11 cross-cluster same range ----------------
r = new_range(cid3, "10.0.0.1", "10.0.0.255")
check("AC-11 cross-cluster identical range 201", r.status_code == 201, r.text)

# ---------------- AC-13 PATCH valid ----------------
created = new_range(cid3, "10.5.0.1", "10.5.0.5").json()
r = admin.patch(f"/api/ip-address-ranges/{created['id']}", json={"start_ip": "10.5.0.2", "end_ip": "10.5.0.9"})
check("AC-13 PATCH 200 new values", r.status_code == 200 and r.json()["start_ip"] == "10.5.0.2" and r.json()["end_ip"] == "10.5.0.9", r.text)
check("AC-13 cluster_id/created_at unchanged", r.json()["cluster_id"] == cid3 and r.json()["created_at"] == created["created_at"])
check("AC-13 re-read same", admin.get(f"/api/ip-address-ranges/{created['id']}").json()["start_ip"] == "10.5.0.2")

# ---------------- AC-12 PATCH overlap revalidation, no partial write ----------------
before_row = db.execute("SELECT start_ip,end_ip FROM ip_address_ranges WHERE id=%s", (created["id"],)).fetchone()
r = admin.patch(f"/api/ip-address-ranges/{created['id']}", json={"start_ip": "10.0.0.100"})
after_row = db.execute("SELECT start_ip,end_ip FROM ip_address_ranges WHERE id=%s", (created["id"],)).fetchone()
check("AC-12 PATCH overlap -> 409", r.status_code == 409, r.text)
check("AC-12 no partial write", before_row == after_row, f"{before_row} -> {after_row}")

# ---------------- AC-14 soft delete ----------------
target = new_range(cid2, "10.6.0.1", "10.6.0.10").json()
r = admin.delete(f"/api/ip-address-ranges/{target['id']}")
check("AC-14 DELETE 204 empty body", r.status_code == 204 and r.content == b"", f"{r.status_code} {r.content!r}")
check("AC-14 immediate detail -> 404", admin.get(f"/api/ip-address-ranges/{target['id']}").status_code == 404)
row = None
for _ in range(40):  # allow request-commit to become visible
    row = db.execute("SELECT deleted_at FROM ip_address_ranges WHERE id=%s", (target["id"],)).fetchone()
    if row and row[0] is not None:
        break
    import time; time.sleep(0.05)
check("AC-14 row still physically present with deleted_at", row is not None and row[0] is not None, str(row))
listing = admin.get(f"/api/ip-address-ranges?cluster_id={cid2}").json()
check("AC-14 deleted not in list", target["id"] not in [i["id"] for i in listing["items"]])
check("AC-14 deleted detail -> 404", admin.get(f"/api/ip-address-ranges/{target['id']}").status_code == 404)

# ---------------- AC-15 soft delete releases overlap ----------------
r = new_range(cid2, "10.6.0.5", "10.6.0.15")
check("AC-15 soft-deleted range no longer overlaps -> 201", r.status_code == 201, r.text)
reuse_id = r.json()["id"]

# ---------------- guard: active IP in range blocks delete ----------------
bmid = new_bm(cid2, "bm-guard")
nic = new_nic(bmid, "eth0")
ipr = new_range(cid2, "10.7.0.1", "10.7.0.10").json()
new_ip(nic, "10.7.0.5")
r = admin.delete(f"/api/ip-address-ranges/{ipr['id']}")
d = r.json()["error"]
check("AC-16 active IP in range -> 409 CONFLICT", r.status_code == 409 and d["code"] == "CONFLICT", r.text)
check("AC-16 details code ACTIVE_CHILDREN_EXIST", any(x.get("code") == "ACTIVE_CHILDREN_EXIST" for x in d["details"]), str(d))
still = db.execute("SELECT deleted_at FROM ip_address_ranges WHERE id=%s", (ipr["id"],)).fetchone()[0]
check("AC-16 target deleted_at still NULL (no partial write)", still is None)

# guard semantics: 10.0.1.1 and 10.0.1.1/16 hit; abc / '' / leading space skipped
def guard_case(ip_literal):
    c = new_cluster(f"guard-{abs(hash(ip_literal)) % 10**9}")
    b = new_bm(c, "n1")
    n = new_nic(b, "eth0")
    rng = new_range(c, "10.0.1.1", "10.0.1.255").json()
    new_ip(n, ip_literal)
    return admin.delete(f"/api/ip-address-ranges/{rng['id']}")

r = guard_case("10.0.1.1")
check("guard 10.0.1.1 hits -> 409", r.status_code == 409, r.text)
r = guard_case("10.0.1.1/16")
check("guard 10.0.1.1/16 hits -> 409", r.status_code == 409, r.text)
for lit in ("abc", "", "   ", "not-an-ip", "2001:db8::1"):
    r = guard_case(lit)
    check(f"guard {lit!r} skipped -> 204 no 500", r.status_code == 204, f"{r.status_code} {r.text}")

# ---------------- AC-17 soft-delete IP then range deletable ----------------
for ip_row in db.execute("SELECT id FROM ip_addresses WHERE network_interface_id=%s AND deleted_at IS NULL", (nic,)).fetchall():
    admin.delete(f"/api/ip-addresses/{ip_row[0]}")
r = admin.delete(f"/api/ip-address-ranges/{ipr['id']}")
check("AC-17 range deletable after all in-range IPs soft-deleted -> 204", r.status_code == 204, r.text)

# ---------------- AC-18 no cascade ----------------
cluster_row_before = db.execute("SELECT name,deleted_at FROM clusters WHERE id=%s", (cid2,)).fetchone()
bm_before = db.execute("SELECT hostname,deleted_at FROM bare_metals WHERE id=%s", (bmid,)).fetchone()
nic_before = db.execute("SELECT name,deleted_at FROM network_interfaces WHERE id=%s", (nic,)).fetchone()
ip_rows_before = db.execute("SELECT id,ip_address,deleted_at FROM ip_addresses WHERE network_interface_id=%s ORDER BY id", (nic,)).fetchall()
admin.delete(f"/api/ip-address-ranges/{reuse_id}")  # delete a range that (maybe) has no active IPs
check("AC-18 cluster unchanged", db.execute("SELECT name,deleted_at FROM clusters WHERE id=%s", (cid2,)).fetchone() == cluster_row_before)
check("AC-18 bare metal unchanged", db.execute("SELECT hostname,deleted_at FROM bare_metals WHERE id=%s", (bmid,)).fetchone() == bm_before)
check("AC-18 NIC unchanged", db.execute("SELECT name,deleted_at FROM network_interfaces WHERE id=%s", (nic,)).fetchone() == nic_before)
check("AC-18 IPAddresses unchanged", db.execute("SELECT id,ip_address,deleted_at FROM ip_addresses WHERE network_interface_id=%s ORDER BY id", (nic,)).fetchall() == ip_rows_before)

# ---------------- AC-19 no status ----------------
openapi = admin.get("/openapi.json").json()
props = openapi["components"]["schemas"]["IpAddressRangeRead"]["properties"]
check("AC-19 read schema has no status", "status" not in props, str(props))
list_params = {p.get("name") for p in openapi["paths"]["/api/ip-address-ranges"]["get"].get("parameters", [])}
check("AC-19 list query params closed", list_params == {"page", "page_size", "cluster_id"}, str(list_params))
check("AC-19 no status column", db.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='ip_address_ranges' AND column_name='status'").fetchone()[0] == 0)

# ---------------- AC-20 list empty for existing cluster w/o ranges ----------------
empty_cid = new_cluster("ic-empty")
r = admin.get(f"/api/ip-address-ranges?cluster_id={empty_cid}")
check("AC-20 existing cluster no ranges -> 200 Empty", r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0, r.text)
r = admin.get("/api/ip-address-ranges?cluster_id=999999999")
check("AC-20 missing cluster -> 404 (Not Found distinct from Empty)", r.status_code == 404, r.text)

# ---------------- AC-21 / AC-22 ----------------
check("AC-21 detail not found -> 404", admin.get("/api/ip-address-ranges/999999999").status_code == 404)
deleted_details = db.execute("SELECT id FROM ip_address_ranges WHERE deleted_at IS NOT NULL LIMIT 1").fetchone()
check("AC-22 deleted detail -> 404", admin.get(f"/api/ip-address-ranges/{deleted_details[0]}").status_code == 404)

# ---------------- AC-25/26/27 no extra endpoints ----------------
paths = [p for p in openapi["paths"] if p.startswith("/api/ip-address-ranges")]
check("AC-25/26/27 exactly 2 paths", sorted(paths) == ["/api/ip-address-ranges", "/api/ip-address-ranges/{ip_address_range_id}"], str(sorted(paths)))
check("AC-25 no allocate/assign keywords", not any(t in p.lower() for p in paths for t in ("allocate", "assign", "usage")))

# ---------------- read-only GET no side effects ----------------
before_ts = db.execute("SELECT updated_at, deleted_at FROM ip_address_ranges ORDER BY id").fetchall()
admin.get("/api/ip-address-ranges")
admin.get(f"/api/ip-address-ranges?cluster_id={cid}")
after_ts = db.execute("SELECT updated_at, deleted_at FROM ip_address_ranges ORDER BY id").fetchall()
check("read-only GET no data mutation", before_ts == after_ts)

# ---------------- drift queries = 0 (product paths) ----------------
overlap = db.execute(
    "SELECT a.id,b.id FROM ip_address_ranges a JOIN ip_address_ranges b "
    "ON a.cluster_id=b.cluster_id AND a.id<b.id AND a.deleted_at IS NULL AND b.deleted_at IS NULL "
    "AND a.start_ip<=b.end_ip AND a.end_ip>=b.start_ip"
).fetchall()
orphan = db.execute(
    "SELECT count(*) FROM ip_address_ranges r JOIN clusters c ON c.id=r.cluster_id "
    "WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL"
).fetchone()[0]
drift = db.execute(
    "SELECT ip.id FROM ip_addresses ip JOIN network_interfaces nic ON nic.id=ip.network_interface_id "
    "JOIN bare_metals bm ON bm.id=nic.bare_metal_id WHERE ip.cluster_id <> bm.cluster_id"
).fetchall()
check("invariant overlap=0", overlap == [], str(overlap))
check("invariant orphan=0", orphan == 0)
check("F005 drift=0", drift == [], str(drift))

print(f"\n===== HTTP INTEGRATION RESULT: PASS {passed} FAIL {len(failed)} =====")
if failed:
    for name in failed:
        print("  FAILED:", name)
    sys.exit(1)
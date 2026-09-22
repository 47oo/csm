#!/usr/bin/env python3
"""F022 real HTTP integration (uvicorn + PostgreSQL) driving the product API.

Covers the F022 contract (name / subnet_mask / vlan on ip_address_ranges) plus
the unchanged F020 semantics, error branches, Empty vs Not Found, no-write
side-effects and read-only guarantees. Does not import app code.

Usage:
    CSM_TEST_ADMIN_PASSWORD=<一次性测试口令> \
    .venv/bin/python docs/test-reports/assets/f022/integration_http.py \
        http://127.0.0.1:8799 "postgresql://csm:csm@localhost:55432/csm_f022_integration"

管理员口令从环境变量 `CSM_TEST_ADMIN_PASSWORD` 读取（一次性测试库的一次性账号），
不写入本文件；用户名可用 `CSM_TEST_ADMIN_USER` 覆盖（默认 `tester`）。
"""
from __future__ import annotations

import os
import sys

import httpx
import psycopg

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
DB = (
    sys.argv[2]
    if len(sys.argv) > 2
    else "postgresql://csm:csm@localhost:55432/csm_f022_integration"
)
ADMIN_USER = os.environ.get("CSM_TEST_ADMIN_USER", "tester")
PASSWORD = os.environ.get("CSM_TEST_ADMIN_PASSWORD")
if not PASSWORD:
    print(
        "环境变量 CSM_TEST_ADMIN_PASSWORD 未设置：请提供一次性测试管理员口令（不落盘）。",
        file=sys.stderr,
    )
    sys.exit(2)

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


READ_FIELDS = {
    "id", "cluster_id", "start_ip", "end_ip",
    "name", "subnet_mask", "vlan", "created_at", "updated_at",
}
FORBIDDEN = {
    "deleted_at", "status", "state", "description", "purpose", "cidr",
    "prefix_length", "network_address", "broadcast_address", "gateway",
    "dhcp", "dns", "capacity", "usage", "utilization", "assigned_at",
    "reclaimed_at", "assigned_to",
}

admin = httpx.Client(base_url=BASE, timeout=20.0)
anon = httpx.Client(base_url=BASE, timeout=20.0)
db = psycopg.connect(DB, autocommit=True)

r = admin.post("/api/auth/login", json={"username": ADMIN_USER, "password": PASSWORD})
check("login 200", r.status_code == 200, r.text)


def new_cluster(name: str) -> int:
    r = admin.post("/api/clusters", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def new_range(cid, start, end, **meta):
    return admin.post(
        "/api/ip-address-ranges",
        json={"cluster_id": cid, "start_ip": start, "end_ip": end, **meta},
    )


def active_count() -> int:
    return db.execute(
        "SELECT count(*) FROM ip_address_ranges WHERE deleted_at IS NULL"
    ).fetchone()[0]


def total_count() -> int:
    return db.execute("SELECT count(*) FROM ip_address_ranges").fetchone()[0]


# ---------------- AC-01 unauthenticated ----------------
before = total_count()
codes = [
    anon.get("/api/ip-address-ranges").status_code,
    anon.get("/api/ip-address-ranges/1").status_code,
    anon.post("/api/ip-address-ranges",
              json={"cluster_id": 1, "start_ip": "1.2.3.4", "end_ip": "1.2.3.5"}).status_code,
    anon.patch("/api/ip-address-ranges/1", json={"start_ip": "1.2.3.4"}).status_code,
    anon.delete("/api/ip-address-ranges/1").status_code,
]
check("AC-01 all 5 endpoints unauthenticated -> 401", codes == [401] * 5, str(codes))
check("AC-01 body UNAUTHENTICATED",
      anon.get("/api/ip-address-ranges").json()["error"]["code"] == "UNAUTHENTICATED")
check("AC-01 no write", total_count() == before)

# ---------------- global empty ----------------
r = admin.get("/api/ip-address-ranges")
check("list empty 200/[]/total0",
      r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0, r.text)

cid = new_cluster("f022-a")
cid2 = new_cluster("f022-b")

# ---------------- AC-02 field closure + round-trip (AC-05) ----------------
r = new_range(cid, "10.0.0.1", "10.0.0.255",
              name="业务网", subnet_mask="255.255.255.0", vlan=100)
check("AC-02 create with metadata 201", r.status_code == 201, r.text)
body = r.json()
check("AC-02 response fields exactly 9", set(body) == READ_FIELDS, str(set(body)))
check("AC-02 no forbidden fields", not (FORBIDDEN & set(body)), str(FORBIDDEN & set(body)))
check("AC-02 metadata values echoed",
      (body["name"], body["subnet_mask"], body["vlan"]) == ("业务网", "255.255.255.0", 100), str(body))
rid = body["id"]
detail = admin.get(f"/api/ip-address-ranges/{rid}").json()
check("AC-05 round-trip read identical",
      detail == body, f"{detail} != {body}")

# ---------------- AC-03 request closure ----------------
for extra in ({"description": "x"}, {"status": "ACTIVE"}, {"deleted_at": None}, {"id": 1},
              {"created_at": "2026-01-01T00:00:00Z"}, {"updated_at": "2026-01-01T00:00:00Z"},
              {"gateway": "10.0.0.254"}, {"cidr": "10.0.0.0/24"}, {"prefix_length": 24},
              {"purpose": "business"}):
    r = admin.post("/api/ip-address-ranges",
                   json={"cluster_id": cid2, "start_ip": "10.1.0.1", "end_ip": "10.1.0.2", **extra})
    check(f"AC-03 unknown create field {list(extra)[0]} -> 400",
          r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR", r.text)
check("AC-03 no writes from unknown fields", active_count() == 1)

# ---------------- AC-04 three fields optional ----------------
r = new_range(cid2, "10.1.0.1", "10.1.0.10")
check("AC-04 missing metadata -> 201", r.status_code == 201, r.text)
b = r.json()
check("AC-04 three fields null (not omitted)",
      (b["name"], b["subnet_mask"], b["vlan"]) == (None, None, None), str(b))
check("AC-04 keys present", all(k in b for k in ("name", "subnet_mask", "vlan")), str(b))

# ---------------- name semantics ----------------
cid3 = new_cluster("f022-c")
check("AC-06 first name 201",
      new_range(cid3, "10.2.0.1", "10.2.0.10", name="业务网").status_code == 201)
before_dup = active_count()
r = new_range(cid3, "10.2.0.20", "10.2.0.30", name="业务网")
check("AC-06 duplicate name same cluster -> 409 CONFLICT",
      r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT", r.text)
dup_details = r.json()["error"]["details"]
check("AC-06 details code DUPLICATE",
      any(d.get("code") == "DUPLICATE" for d in dup_details), str(dup_details))
check("AC-06 details field name",
      any(d.get("field") == "name" for d in dup_details), str(dup_details))
check("AC-06 no write on duplicate", active_count() == before_dup)

r = new_range(cid2, "10.3.0.1", "10.3.0.10", name="业务网")
check("AC-07 cross-cluster same name -> 201", r.status_code == 201, r.text)

cid4 = new_cluster("f022-d")
check("AC-08 case-sensitive web 201",
      new_range(cid4, "10.4.0.1", "10.4.0.10", name="web").status_code == 201)
check("AC-08 case-sensitive Web 201",
      new_range(cid4, "10.4.0.20", "10.4.0.30", name="Web").status_code == 201)

cid5 = new_cluster("f022-e")
tmp = new_range(cid5, "10.5.0.1", "10.5.0.10", name="release")
assert tmp.status_code == 201
admin.delete(f"/api/ip-address-ranges/{tmp.json()['id']}")
r = new_range(cid5, "10.5.0.20", "10.5.0.30", name="release")
check("AC-09 soft-delete releases name -> 201", r.status_code == 201, r.text)

cid6 = new_cluster("f022-f")
r = new_range(cid6, "10.6.0.1", "10.6.0.10", name="")
check("AC-10 empty name currently accepted (not asserted legal)",
      r.status_code == 201, r.text)
r = new_range(cid6, "10.6.0.20", "10.6.0.30", name="  空格  ")
check("AC-10 whitespace name currently accepted (not asserted legal)",
      r.status_code == 201, r.text)

# ---------------- subnet_mask ----------------
cid7 = new_cluster("f022-g")
for mask in ("255.255.255.0", "255.255.0.0", "255.0.0.0", "0.0.0.0", "255.255.255.255"):
    r = new_range(cid7, f"10.7.{len(mask)}.1", f"10.7.{len(mask)}.5", subnet_mask=mask)
    check(f"AC-11 legal mask {mask} -> 201 + echo",
          r.status_code == 201 and r.json()["subnet_mask"] == mask, r.text)

cid8 = new_cluster("f022-h")
active_before = active_count()
bad_masks = ["255.0.255.0", "255.255.255.1", "255.255.255.256", "10.0.0.1",
             "abc", "/24", "2001:db8::1", "", " 255.255.255.0", "255.255.255.0 "]
for i, mask in enumerate(bad_masks):
    r = new_range(cid8, f"10.8.{i}.1", f"10.8.{i}.5", subnet_mask=mask)
    ok = r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    ok = ok and any(d.get("field") == "subnet_mask" for d in r.json()["error"]["details"])
    check(f"AC-12 illegal mask {mask!r} -> 400 field subnet_mask", ok, r.text)
check("AC-12 no writes from illegal masks", active_count() == active_before)

cid9 = new_cluster("f022-i")
r = new_range(cid9, "10.1.1.1", "10.1.2.10", subnet_mask="255.255.255.0")
check("AC-13 mask not self-consistent with start/end -> 201", r.status_code == 201, r.text)

# ---------------- vlan ----------------
cid10 = new_cluster("f022-j")
check("AC-15 vlan 1 -> 201",
      new_range(cid10, "10.10.0.1", "10.10.0.5", vlan=1).status_code == 201)
check("AC-15 vlan 4094 -> 201",
      new_range(cid10, "10.10.0.10", "10.10.0.15", vlan=4094).status_code == 201)

cid11 = new_cluster("f022-k")
bad_vlans = [0, 4095, 4096, -1, 100.5, "100", True, False, 1.0]
for i, vlan in enumerate(bad_vlans):
    r = new_range(cid11, f"10.11.{i}.1", f"10.11.{i}.5", vlan=vlan)
    ok = r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    ok = ok and any(d.get("field") == "vlan" for d in r.json()["error"]["details"])
    check(f"AC-16 illegal vlan {vlan!r} -> 400 field vlan", ok, r.text)

cid12 = new_cluster("f022-l")
check("AC-17 shared vlan first -> 201",
      new_range(cid12, "10.12.0.1", "10.12.0.5", vlan=200).status_code == 201)
check("AC-17 shared vlan second -> 201",
      new_range(cid12, "10.12.0.10", "10.12.0.15", vlan=200).status_code == 201)

# ---------------- PATCH ----------------
cid13 = new_cluster("f022-m")
p = new_range(cid13, "10.13.0.1", "10.13.0.10",
              name="orig", subnet_mask="255.255.255.0", vlan=10).json()
r = admin.patch(f"/api/ip-address-ranges/{p['id']}",
                json={"name": "fixed", "subnet_mask": "255.255.0.0", "vlan": 20})
check("PATCH fixes three metadata fields 200",
      r.status_code == 200 and (r.json()["name"], r.json()["subnet_mask"], r.json()["vlan"])
      == ("fixed", "255.255.0.0", 20), r.text)
check("PATCH cluster_id/created_at immutable",
      r.json()["cluster_id"] == p["cluster_id"] and r.json()["created_at"] == p["created_at"])

r = admin.patch(f"/api/ip-address-ranges/{p['id']}",
                json={"name": None, "subnet_mask": None, "vlan": None})
check("PATCH null clears three optional fields",
      r.status_code == 200 and (r.json()["name"], r.json()["subnet_mask"], r.json()["vlan"])
      == (None, None, None), r.text)

for payload in ({"start_ip": None}, {"end_ip": None}):
    r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json=payload)
    check(f"PATCH {list(payload)[0]}=null -> 400", r.status_code == 400, r.text)

r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={})
check("PATCH empty body -> 400", r.status_code == 400, r.text)

# PATCH duplicate name -> 409 no partial write
other = new_range(cid13, "10.13.100.1", "10.13.100.5", name="taken").json()
admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"name": "self-name"})
r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"name": "taken", "vlan": 999})
check("PATCH duplicate name -> 409 DUPLICATE", r.status_code == 409
      and any(d.get("code") == "DUPLICATE" for d in r.json()["error"]["details"]), r.text)
row = db.execute("SELECT name, vlan FROM ip_address_ranges WHERE id=%s", (p["id"],)).fetchone()
check("PATCH duplicate name no partial write", row == ("self-name", None), str(row))

r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"name": "self-name"})
check("PATCH own name -> 200", r.status_code == 200, r.text)

# PATCH invalid mask / vlan -> 400
r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"subnet_mask": "255.0.255.0"})
check("PATCH illegal mask -> 400 field subnet_mask",
      r.status_code == 400 and any(d.get("field") == "subnet_mask"
                                   for d in r.json()["error"]["details"]), r.text)
r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"vlan": 4095})
check("PATCH illegal vlan -> 400 field vlan",
      r.status_code == 400 and any(d.get("field") == "vlan"
                                   for d in r.json()["error"]["details"]), r.text)
r = admin.patch(f"/api/ip-address-ranges/{p['id']}", json={"cluster_id": 1})
check("PATCH immutable cluster_id -> 400", r.status_code == 400, r.text)

# ---------------- existing semantics unchanged ----------------
cid14 = new_cluster("f022-n")
a = new_range(cid14, "10.14.0.1", "10.14.0.100", name="one").json()
r = new_range(cid14, "10.14.0.50", "10.14.0.200", name="two")
check("AC-19 overlap same cluster -> 409 OVERLAP",
      r.status_code == 409 and any(d.get("code") == "OVERLAP"
                                   for d in r.json()["error"]["details"]), r.text)
check("AC-19 cross-cluster same range 201",
      new_range(cid2, "10.14.0.1", "10.14.0.100").status_code == 201)

admin.delete(f"/api/ip-address-ranges/{a['id']}")
check("AC-20 soft-delete releases overlap -> 201",
      new_range(cid14, "10.14.0.50", "10.14.0.200").status_code == 201)

# delete guard
cid15 = new_cluster("f022-o")
bm = admin.post("/api/bare-metals", json={"cluster_id": cid15, "hostname": "n1"}).json()["id"]
nic = admin.post("/api/network-interfaces",
                 json={"bare_metal_id": bm, "name": "eth0",
                       "technology_type": "Ethernet", "purpose": "Business"}).json()["id"]
ip = admin.post("/api/ip-addresses",
                json={"network_interface_id": nic, "ip_address": "10.15.0.5"}).json()
g = new_range(cid15, "10.15.0.1", "10.15.0.10").json()
r = admin.delete(f"/api/ip-address-ranges/{g['id']}")
check("AC-21 delete guard -> 409 ACTIVE_CHILDREN_EXIST no partial write",
      r.status_code == 409 and any(d.get("code") == "ACTIVE_CHILDREN_EXIST"
                                   for d in r.json()["error"]["details"])
      and db.execute("SELECT deleted_at FROM ip_address_ranges WHERE id=%s",
                     (g["id"],)).fetchone()[0] is None, r.text)
admin.delete(f"/api/ip-addresses/{ip['id']}")
check("AC-21 after soft-deleting IP -> 204",
      admin.delete(f"/api/ip-address-ranges/{g['id']}").status_code == 204)

# AC-22 no status
check("AC-22 no status field in response", "status" not in body)
r = admin.post("/api/ip-address-ranges",
               json={"cluster_id": cid15, "start_ip": "10.16.0.1", "end_ip": "10.16.0.5",
                     "status": "ACTIVE"})
check("AC-22 status in request -> 400", r.status_code == 400, r.text)

# AC-23 IPv4 normalization
r = new_range(cid2, "010.020.000.001", "010.020.000.005")
check("AC-23 leading zeros normalized",
      r.status_code == 201 and r.json()["start_ip"] == "10.20.0.1"
      and r.json()["end_ip"] == "10.20.0.5", r.text)

# AC-26 F005 free-text unchanged
cid16 = new_cluster("f022-p")
bm16 = admin.post("/api/bare-metals", json={"cluster_id": cid16, "hostname": "n1"}).json()["id"]
nic16 = admin.post("/api/network-interfaces",
                   json={"bare_metal_id": bm16, "name": "eth0",
                         "technology_type": "Ethernet", "purpose": "Business"}).json()["id"]
r = admin.post("/api/ip-addresses",
               json={"network_interface_id": nic16, "ip_address": "  weird literal  "})
check("AC-26 F005 free-text stored literally",
      r.status_code == 201 and r.json()["ip_address"] == "  weird literal  ", r.text)

# ---------------- Empty vs Not Found + 404 + no write ----------------
cid17 = new_cluster("f022-q")
r = admin.get(f"/api/ip-address-ranges?cluster_id={cid17}")
check("empty cluster -> 200 [] (Empty)", r.status_code == 200 and r.json()["items"] == [], r.text)
r = admin.get("/api/ip-address-ranges?cluster_id=999999999")
check("missing cluster -> 404 NOT_FOUND", r.status_code == 404
      and r.json()["error"]["code"] == "NOT_FOUND", r.text)
r = admin.get("/api/ip-address-ranges/999999999")
check("missing range -> 404 NOT_FOUND",
      r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND", r.text)
check("missing cluster create -> 404", new_range(999999999, "10.99.0.1", "10.99.0.2").status_code == 404)

# read-only: GET does not mutate
snap_before = db.execute(
    "SELECT id, name, subnet_mask, vlan, updated_at, deleted_at FROM ip_address_ranges ORDER BY id"
).fetchall()
for _ in range(3):
    admin.get("/api/ip-address-ranges")
    admin.get(f"/api/ip-address-ranges/{p['id']}")
snap_after = db.execute(
    "SELECT id, name, subnet_mask, vlan, updated_at, deleted_at FROM ip_address_ranges ORDER BY id"
).fetchall()
check("read-only GET has no side-effects", snap_before == snap_after)

print(f"\n===== HTTP INTEGRATION RESULT: PASS {passed} FAIL {len(failed)} =====")
if failed:
    for name in failed:
        print("  FAILED:", name)
sys.exit(0 if not failed else 1)
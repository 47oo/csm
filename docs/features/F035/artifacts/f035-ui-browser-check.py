"""F035 B 层（浏览器）验证 — 真实部署栈 + 真实前端产物 + 真实 API。

与 F034 的静态 `dist` + 转发方案不同，本次 `csmtest` 栈的 **frontend 与 backend
容器均用候选 HEAD `187ddf3` 重建**，因此直接驱动 `http://localhost:18080`
（nginx → 候选前端 → 候选后端），无 mock、无 header 改写、同源 CSRF 真实生效。

覆盖：
* `TD3-F035-T117.5`：面板粘贴追加行 → 预校验 0 错误 → 「确认导入」可用 → 成功提示
* 面板文案（`architecture.md` §7.3 / `implementation.md` §2）：
  - 标题含「已存在机器可追加网卡/IP」
  - 追加规则 **6 条** `<li>`（逐条关键措辞）
  - `created===0` 定性说明（「本批未新建资源（全部追加到既有资源）」），且
    **不展示追加数量 M**（DR-F035-11）
  - F014 面板差异说明（「资源导入不支持向已存在 hostname 追加网卡/IP」）
* 行错误呈现（`field=role` 断言）+ 门控（有错误时「确认导入」禁用）

写入范围：脚本自建 Cluster / Network / Resource / Interface / IP（前缀 `f35b-`），
结束后按依赖顺序软删（Cluster `code_key` 全局唯一，故每轮使用新 code）。

Run:  CSM_PASSWORD=testadmin python3 docs/features/F035/artifacts/f035-ui-browser-check.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
BASE = os.environ.get("CSM_BASE_URL", "http://localhost:18080")
USERNAME = os.environ.get("CSM_USERNAME", "admin")
# TEST credential only; never stored in the repo (`.env.test` is git-ignored).
PASSWORD = os.environ.get("CSM_PASSWORD", "")

HEADERS = [
    "cluster",
    "hostname",
    "resource_type",
    "role",
    "status",
    "host",
    "vcpu",
    "memory_mb",
    "disk_gb",
    "hypervisor",
    "manufacturer",
    "model",
    "serial_number",
    "cpu_model",
    "cpu_sockets",
    "cpu_cores",
    "gpu_model",
    "gpu_count",
    "name",
    "interface_type",
    "mac_address",
    "speed_mbps",
    "mtu",
    "enabled",
    "network",
    "ip",
]

lines: list[str] = []
results: dict[str, object] = {}
failures = 0


def log(message: str) -> None:
    lines.append(message)
    print(message)


def check(name: str, ok: bool, detail: str = "") -> bool:
    global failures
    if not ok:
        failures += 1
    log(f"{'PASS' if ok else 'FAIL'} {name}{f' — {detail}' if detail else ''}")
    return ok


def csv_text(rows: list[dict[str, str]]) -> str:
    out = [",".join(HEADERS)]
    for row in rows:
        out.append(",".join(str(row.get(h, "")) for h in HEADERS))
    return "\n".join(out) + "\n"


class API:
    """Plain API client for fixture setup/teardown (never used for the assertion path)."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.session = requests.Session()

    def login(self) -> None:
        response = self.session.post(
            f"{self.base}/api/v1/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=15,
        )
        assert response.status_code == 200, response.text

    def get(self, path: str, **params):
        return self.session.get(f"{self.base}{path}", params=params, timeout=15)

    def post(self, path: str, payload):
        return self.session.post(f"{self.base}{path}", json=payload, timeout=15)

    def patch(self, path: str, payload):
        return self.session.patch(f"{self.base}{path}", json=payload, timeout=15)

    def delete(self, path: str, version: int):
        return self.session.delete(f"{self.base}{path}", params={"version": version}, timeout=15)


def main() -> int:
    if not PASSWORD:
        log("FAIL CSM_PASSWORD must be provided (TEST stack credential; do not commit it)")
        return 2
    LOGS.mkdir(parents=True, exist_ok=True)

    index = requests.get(f"{BASE}/", timeout=15).text
    asset = index.split('src="')[1].split('"')[0] if 'src="' in index else ""
    check("部署前端为候选产物", asset == "/assets/index-TGYZNgB0.js", asset)

    api = API(BASE)
    api.login()
    code = os.environ.get("CSM_F035_BROWSER_CLUSTER_CODE") or f"F35B{time.strftime('%H%M%S')}"
    created = {"cluster": None, "network": None, "resource": None, "interfaces": [], "ips": []}

    cluster = api.post("/api/v1/clusters", {"code": code, "name": "F035 B-layer cluster"})
    assert cluster.status_code == 201, cluster.text
    created["cluster"] = cluster.json()["cluster"]
    network = api.post(
        "/api/v1/networks",
        {"cluster": created["cluster"]["id"], "name": "f35b-net", "cidr": "10.181.0.0/24"},
    )
    assert network.status_code == 201, network.text
    created["network"] = network.json()["network"]
    host = api.post(
        "/api/v1/resources",
        {
            "cluster": code,
            "hostname": "f35b-host",
            "resource_type": "BARE_METAL",
            "role": "COMPUTE",
            "status": "IDLE",
            "hardware": {"manufacturer": "Dell", "cpu_cores": 16, "memory_mb": 65536},
        },
    )
    assert host.status_code == 201, host.text
    created["resource"] = host.json()["resource"]
    iface = api.post("/api/v1/interfaces", {"resource": created["resource"]["id"], "name": "eth0"})
    assert iface.status_code == 201, iface.text
    created["interfaces"].append(iface.json()["interface"])
    ip = api.post("/api/v1/ip-addresses", {"network": created["network"]["id"], "address": "10.181.0.10"})
    assert ip.status_code == 201, ip.text
    bind = api.patch(f"/api/v1/ip-addresses/{ip.json()['ip_address']['id']}", {
        "version": ip.json()["ip_address"]["version"],
        "interface": created["interfaces"][0]["id"],
    })
    assert bind.status_code == 200, bind.text
    created["ips"].append(bind.json()["ip_address"])

    host_before = api.get(f"/api/v1/resources/{created['resource']['id']}").json()["resource"]

    append_text = csv_text(
        [
            {
                "cluster": code,
                "hostname": "f35b-host",
                "resource_type": "BARE_METAL",
                "role": "COMPUTE",
                "status": "IDLE",
                "manufacturer": "Dell",
                "cpu_cores": "16",
                "memory_mb": "65536",
                "name": "f35b-eth1",
                "interface_type": "PHYSICAL",
                "network": "f35b-net",
                "ip": "10.181.0.11",
            }
        ]
    )
    mismatch_text = csv_text(
        [
            {
                "cluster": code,
                "hostname": "f35b-host",
                "resource_type": "BARE_METAL",
                "role": "GPU",
                "name": "f35b-eth2",
                "network": "f35b-net",
                "ip": "10.181.0.12",
            }
        ]
    )

    api_calls: list[dict[str, object]] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.on(
            "response",
            lambda response: api_calls.append(
                {"url": response.url, "status": response.status, "method": response.request.method}
            )
            if "/api/v1/" in response.url
            else None,
        )

        page.goto(f"{BASE}/", wait_until="networkidle")
        page.fill("#login-username", USERNAME)
        page.fill("#login-password", PASSWORD)
        page.click("button:has-text('登录')")
        page.get_by_role("button", name="登出", exact=True).wait_for(timeout=15000)
        console_errors.clear()
        check("浏览器登录真实后端", True)

        page.get_by_role("button", name="Resources", exact=True).click()
        page.wait_for_timeout(1200)

        # --- F014 panel: difference note ----------------------------------
        page.get_by_role("button", name="批量导入", exact=True).click()
        page.wait_for_timeout(600)
        page.get_by_role("menuitem", name="批量导入…", exact=True).click()
        page.wait_for_timeout(800)
        page.locator("#resource-import-carrier").wait_for(timeout=8000)
        f014_text = page.inner_text("body")
        check(
            "F014 面板写明「资源导入不支持向已存在 hostname 追加网卡/IP」",
            "资源导入不支持向已存在 hostname 追加网卡/IP" in f014_text
            and "需追加请用「资源+网卡+IP」导入" in f014_text,
            "",
        )
        page.screenshot(path=str(LOGS / "f035-f014-panel.png"), full_page=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        page.mouse.click(5, 5)
        page.wait_for_timeout(400)

        # --- F023/F035 panel: copy + rules ---------------------------------
        page.get_by_role("button", name="批量导入", exact=True).click()
        page.wait_for_timeout(600)
        page.get_by_role("menuitem", name="资源+网卡+IP 批量导入…", exact=True).click()
        page.wait_for_timeout(1000)
        page.locator("#resource-interface-ip-import-carrier").wait_for(timeout=8000)
        panel = page.locator(".panel").filter(
            has=page.locator("h2:has-text('已存在机器可追加网卡/IP')")
        )
        check("F035 面板标题含「已存在机器可追加网卡/IP」", panel.count() == 1, f"count={panel.count()}")
        rules = panel.locator("ul.list-disc > li").all_inner_texts()
        results["appendRules"] = rules
        check("追加规则恰 6 条", len(rules) == 6, f"count={len(rules)}")
        expected_fragments = [
            "必须与既有值完全一致（区分大小写）",
            "留空 = 省略",
            "不能经导入补填",
            "既有同名网卡（区分大小写）与同集群既有 IP 仍报行错误",
            "不支持向既有网卡再绑定 IP",
            "补录已有机器时只提交新增行",
            "VM 追加行的 host 仍必填",
        ]
        joined = "\n".join(rules)
        for fragment in expected_fragments:
            check(f"追加规则含「{fragment}」", fragment in joined, "")

        # --- error rendering: field=role + gated confirm -------------------
        page.locator("#resource-interface-ip-import-carrier").click()
        page.wait_for_timeout(400)
        dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last
        dropdown.locator(".ant-select-item-option", has_text="粘贴 CSV 文本").first.click()
        page.wait_for_timeout(400)
        textarea = page.locator("#resource-interface-ip-import-text")
        textarea.fill(mismatch_text)
        page.wait_for_timeout(300)
        validate_btn = panel.locator("button:has-text('预校验（不写入数据）')")
        with page.expect_response(
            lambda r: r.url.endswith("/imports/resource-interfaces-ips/validate") and r.request.method == "POST"
        ) as validate_info:
            validate_btn.click()
        check("浏览器真实 /validate（错误批）返回 200", validate_info.value.status == 200, str(validate_info.value.status))
        page.wait_for_selector("text=预校验完成", timeout=20000)
        page.wait_for_timeout(600)
        error_text = panel.inner_text()
        confirm = panel.locator("button:has-text('确认导入')")
        check(
            "行错误呈现 field=role（既有值不一致）",
            "role" in error_text and "does not match the existing resource value" in error_text,
            "",
        )
        check("存在行错误时「确认导入」禁用", confirm.is_disabled(), "")
        page.screenshot(path=str(LOGS / "f035-panel-role-error.png"), full_page=True)

        # --- real append write through the UI -----------------------------
        textarea.fill(append_text)
        page.wait_for_timeout(400)
        with page.expect_response(
            lambda r: r.url.endswith("/imports/resource-interfaces-ips/validate") and r.request.method == "POST"
        ) as validate_info2:
            validate_btn.click()
        check("浏览器真实 /validate（追加批）返回 200", validate_info2.value.status == 200, str(validate_info2.value.status))
        page.wait_for_selector("text=预校验通过", timeout=20000)
        page.wait_for_timeout(800)
        validate_calls = [
            call for call in api_calls if call["url"].endswith("/imports/resource-interfaces-ips/validate")
        ]
        check(
            "浏览器真实 /validate 往返（追加行 0 错误）",
            len(validate_calls) == 2 and validate_calls[-1]["status"] == 200,
            str(validate_calls[-1] if validate_calls else None),
        )
        expect(confirm).to_be_enabled(timeout=15000)
        check("预校验 0 错误后「确认导入」可用", not confirm.is_disabled(), "")
        confirm.click()
        page.wait_for_selector("text=导入成功", timeout=30000)
        page.wait_for_timeout(800)
        success_text = panel.inner_text()
        write_calls = [
            call
            for call in api_calls
            if call["url"].endswith("/imports/resource-interfaces-ips") and call["method"] == "POST"
        ]
        check(
            "浏览器真实写入 201",
            len(write_calls) == 1 and write_calls[0]["status"] == 201,
            str(write_calls),
        )
        check(
            "成功提示为 created===0 定性说明（未新建资源，全部追加）",
            "本批未新建资源（全部追加到既有资源）" in success_text,
            "",
        )
        check(
            "成功提示不展示追加数量 M（DR-F035-11）",
            "追加 1" not in success_text and "追加数" not in success_text and "追加 1 个资源" not in success_text,
            "",
        )
        check(
            "成功提示含新建网卡 / IP 计数",
            "新建网卡 1 个" in success_text and "IP 1 个" in success_text,
            "",
        )
        page.screenshot(path=str(LOGS / "f035-append-success.png"), full_page=True)

        storage = page.evaluate(
            "() => ({localKeys: Object.keys(localStorage), sessionKeys: Object.keys(sessionStorage),"
            " cookie: document.cookie})"
        )
        results["storage"] = storage
        check("无 console error", console_errors == [], str(console_errors[:3]))
        check(
            "追加行文本未落 localStorage/sessionStorage",
            "f35b-eth1" not in json.dumps(storage) and "10.181.0.11" not in json.dumps(storage),
            json.dumps(storage),
        )
        results["apiCalls"] = api_calls
        results["consoleErrors"] = console_errors
        browser.close()

    # --- post-write API assertions (independent of the UI) ----------------
    host_after = api.get(f"/api/v1/resources/{created['resource']['id']}").json()["resource"]
    check(
        "真实栈追加后既有 Resource 未变（全字段含 version/updated_at）",
        host_after == host_before,
        f"version {host_before['version']}→{host_after['version']}",
    )
    ifaces_after = api.get("/api/v1/interfaces", resource_id=created["resource"]["id"]).json()
    new_iface = next((item for item in ifaces_after["items"] if item["name"] == "f35b-eth1"), None)
    check("新 Interface 归属既有宿主", new_iface is not None, str(new_iface and new_iface["id"]))
    ips_after = api.get("/api/v1/ip-addresses", page_size=100).json()
    new_ip = next((item for item in ips_after["items"] if item["address"].startswith("10.181.0.11")), None)
    check(
        "新 IP 绑定到新 Interface",
        new_ip is not None and new_iface is not None and new_ip["interface"]["id"] == new_iface["id"],
        str(new_ip and new_ip["interface"]),
    )
    activity = api.get(f"/api/v1/resources/{created['resource']['id']}/activity", page_size=100).json()
    check(
        "宿主 Activity 无 UPDATE 项",
        {item["action"] for item in activity["items"]} <= {"CREATE"},
        str({item["action"] for item in activity["items"]}),
    )
    if new_ip:
        created["ips"].append(new_ip)
    if new_iface:
        created["interfaces"].append(new_iface)

    # --- cleanup ---------------------------------------------------------
    cleanup = []
    for ip_row in created["ips"]:
        current = api.get(f"/api/v1/ip-addresses/{ip_row['id']}").json()["ip_address"]
        cleanup.append(api.delete(f"/api/v1/ip-addresses/{ip_row['id']}", current["version"]).status_code)
    for iface_row in created["interfaces"]:
        current = api.get(f"/api/v1/interfaces/{iface_row['id']}").json()["interface"]
        cleanup.append(api.delete(f"/api/v1/interfaces/{iface_row['id']}", current["version"]).status_code)
    current = api.get(f"/api/v1/resources/{created['resource']['id']}").json()["resource"]
    cleanup.append(api.delete(f"/api/v1/resources/{created['resource']['id']}", current["version"]).status_code)
    current = api.get(f"/api/v1/networks/{created['network']['id']}").json()["network"]
    cleanup.append(api.delete(f"/api/v1/networks/{created['network']['id']}", current["version"]).status_code)
    current = api.get(f"/api/v1/clusters/{created['cluster']['id']}").json()["cluster"]
    cleanup.append(api.delete(f"/api/v1/clusters/{created['cluster']['id']}", current["version"]).status_code)
    results["cleanup"] = cleanup
    check("清理：自建对象全部软删（204）", all(item == 204 for item in cleanup), str(cleanup))

    results["failures"] = failures
    results["base"] = BASE
    results["clusterCode"] = code
    (HERE / "f035-browser-check.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (LOGS / "f035-browser-check.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"\n{len(lines)} lines, {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

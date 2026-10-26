"""F034 B-layer (browser) verification — real built frontend, real backend API.

Environment facts that shape this harness:

* The `csmtest-frontend-1` container still runs the **pre-F034** image, so it
  cannot show the new UI. Instead this script serves the freshly built
  `frontend/dist` (produced by `npm run build`, i.e. the candidate source) from a
  plain static file server and drives it with Playwright/Chromium.
* `vite dev` has no `/api/v1` proxy (see `frontend/vite.config.ts`), so the
  `/api/v1/**` requests are forwarded by the test harness to the **real running
  backend** at `http://localhost:18080` (compose project `csmtest`). Nothing is
  mocked: responses are the real API responses. The harness strips the browser's
  `Origin`/`Sec-Fetch-*` headers when forwarding, which makes it a non-browser
  API client for the backend's CSRF guard (`app/core/csrf.py` treats a request
  with neither header as a non-browser client). Disclosed in the Test Report.
* Read-only against the deployment: the flow only uses `POST /validate`
  (no writes), so no business data is created in `csmtest`.

Covers `TD3-T107.7`, `TD3-T115.8`, `TD3-T116.9` (and the visible half of
`TD3-T107.1` / `TD3-T108.4` / `TD3-T116.4/6`).

Run:  python3 docs/features/F034/artifacts/f034-ui-browser-check.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DIST = REPO / "frontend" / "dist"
CORPUS = HERE / "corpus"
BACKEND = os.environ.get("CSM_BASE_URL", "http://localhost:18080")
USERNAME = os.environ.get("CSM_USERNAME", "admin")
# TEST credential only; never stored in the repo (`.env.test` is git-ignored).
PASSWORD = os.environ.get("CSM_PASSWORD", "")

STATIC_PORT = 4173
PAGE_ORIGIN = f"http://127.0.0.1:{STATIC_PORT}"

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


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence the static server
        pass


def serve_dist() -> ThreadingHTTPServer:
    handler = partial(QuietHandler, directory=str(DIST))
    server = ThreadingHTTPServer(("127.0.0.1", STATIC_PORT), handler)
    thread_import = __import__("threading")
    thread_import.Thread(target=server.serve_forever, daemon=True).start()
    for _ in range(50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", STATIC_PORT)) == 0:
                return server
        time.sleep(0.1)
    raise RuntimeError("static server did not start")


def open_options(page, selector: str) -> list[str]:
    """Open an antd Select and return the visible option labels."""
    page.click(selector)
    page.wait_for_timeout(500)
    dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last
    dropdown.wait_for(state="visible", timeout=8000)
    return [text.strip() for text in dropdown.locator(".ant-select-item-option").all_inner_texts()]


def pick(page, selector: str, option_text: str) -> None:
    """Open an antd Select (custom listbox) and choose an option by exact text."""
    options = open_options(page, selector)
    assert option_text in options, f"{option_text!r} not in {options!r}"
    dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last
    dropdown.locator(".ant-select-item-option", has_text=option_text).first.click()
    page.wait_for_timeout(400)


def main() -> int:
    if not PASSWORD:
        log("FAIL CSM_PASSWORD must be provided (TEST stack credential; do not commit it)")
        return 2
    if not (DIST / "index.html").is_file():
        log(f"FAIL frontend build missing at {DIST} (run `npm run build` first)")
        return 1
    if subprocess.run(["docker", "inspect", "csmtest-nginx-1"], capture_output=True).returncode != 0:
        log("FAIL csmtest stack not running")
        return 1

    server = serve_dist()
    payload = (CORPUS / "F-01.txt").read_text(encoding="utf-8")
    marker = "F034-MARKER-8a1f4c0d-6f4f-4ef3-9d4a-9f7f3c1b2e55"

    api_calls: list[dict[str, object]] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))

        def forward(route, request):
            headers = {
                key: value
                for key, value in request.headers.items()
                if key.lower() not in {"origin", "referer", "sec-fetch-site", "sec-fetch-mode", "host", "content-length"}
            }
            body = request.post_data_buffer
            response = context.request.fetch(
                BACKEND + request.url[len(PAGE_ORIGIN):],
                method=request.method,
                headers=headers,
                data=body,
                fail_on_status_code=False,
            )
            api_calls.append({"method": request.method, "url": request.url, "status": response.status})
            route.fulfill(
                status=response.status,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in {"content-encoding", "content-length", "transfer-encoding", "connection"}
                },
                body=response.body(),
            )

        page.route("**/api/v1/**", forward)

        # --- login through the real UI + real API ---------------------------
        page.goto(PAGE_ORIGIN + "/", wait_until="networkidle")
        page.fill("#login-username", USERNAME)
        page.fill("#login-password", PASSWORD)
        page.click("button:has-text('登录')")
        page.get_by_role("button", name="登出", exact=True).wait_for(timeout=15000)
        login_calls = [
            c for c in api_calls if str(c["url"]).endswith("/api/v1/auth/login")
        ]
        check(
            "browser login against real backend",
            len(login_calls) == 1 and login_calls[0]["status"] == 200,
            str(login_calls),
        )
        # The app probes GET /auth/me before login by design (401 is the expected
        # pre-login answer); only post-login console errors matter here.
        console_errors.clear()

        # --- navigate to Resources and open the F014 import panel -----------
        page.get_by_role("button", name="Resources", exact=True).click()
        page.wait_for_timeout(1500)
        page.get_by_role("button", name="批量导入", exact=True).click()
        page.wait_for_timeout(600)
        page.get_by_role("menuitem", name="批量导入…", exact=True).click()
        page.wait_for_timeout(800)
        panel = page.locator("#resource-import-carrier")
        panel.wait_for(timeout=8000)
        check("F014 panel exposes the carrier control", panel.count() == 1)
        options = open_options(page, "#resource-import-carrier")
        check(
            "TD3-T107.7 both carriers listed side by side",
            options == ["上传文件（CSV / .xlsx）", "粘贴 CSV 文本（仅 CSV）"],
            str(options),
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check(
            "TD3-T107.1 file input still present next to the text carrier",
            page.locator("#resource-import-file[type=file]").count() == 1,
        )

        # --- switch to the text carrier -------------------------------------
        pick(page, "#resource-import-carrier", "粘贴 CSV 文本（仅 CSV）")
        textarea = page.locator("#resource-import-text")
        check("TD3-T107.7 text carrier renders a textarea", textarea.count() == 1)
        check(
            "TD3-T116.4/5 format is locked to csv in the text carrier",
            page.locator("#resource-import-format").is_disabled()
            or "ant-select-disabled"
            in (page.locator("#resource-import-format").evaluate("el => el.closest('.ant-select').className") or ""),
            page.locator("#resource-import-format").evaluate("el => el.closest('.ant-select').className"),
        )
        check(
            "TD3-T116.4 switching carrier clears the result area",
            page.locator("text=尚未预校验").count() >= 1,
        )

        # --- real pre-validation round-trip ---------------------------------
        textarea.fill(payload)
        page.wait_for_timeout(300)
        confirm = page.locator("button:has-text('确认导入')")
        check("TD3-T108.4 confirm disabled before any pre-validation", confirm.is_disabled())
        page.click("button:has-text('预校验（不写入数据）')")
        page.wait_for_selector("text=共", timeout=20000)
        page.wait_for_timeout(500)
        validate_calls = [c for c in api_calls if str(c["url"]).endswith("/imports/resources/validate")]
        check(
            "real /validate round-trip from the browser",
            len(validate_calls) == 1 and validate_calls[0]["status"] == 200,
            str(validate_calls),
        )
        body_text = page.inner_text("body")
        check(
            "pre-validation result is rendered (row errors visible)",
            "总行数" in body_text or "错误" in body_text,
            body_text[:0],
        )
        # The `csmtest` database has no Cluster, so the row-level errors keep the
        # confirm button disabled — that is the correct two-step behaviour.
        check("TD3-T108.4 confirm still disabled with row errors", confirm.is_disabled())

        # --- TD3-T116.9 editing invalidates the stale result ----------------
        textarea.fill(payload.replace("f34-h1", "f34-h1x"))
        page.wait_for_timeout(400)
        check(
            "TD3-T116.9 editing the text resets the result area",
            page.locator("text=尚未预校验").count() >= 1,
        )
        check("TD3-T116.9 confirm stays disabled after editing", confirm.is_disabled())

        # --- second entry point (F023) --------------------------------------
        page.get_by_role("button", name="批量导入", exact=True).click()
        page.wait_for_timeout(600)
        page.get_by_role("menuitem", name="资源+网卡+IP 批量导入…", exact=True).click()
        page.wait_for_timeout(1000)
        panel2 = page.locator("#resource-interface-ip-import-carrier")
        panel2.wait_for(timeout=8000)
        options2 = open_options(page, "#resource-interface-ip-import-carrier")
        check("TD3-T107.7 F023 panel exposes both carriers too", options2 == options, str(options2))
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        pick(page, "#resource-interface-ip-import-carrier", "粘贴 CSV 文本（仅 CSV）")
        check(
            "TD3-T107.7 F023 text carrier renders its own textarea",
            page.locator("#resource-interface-ip-import-text").count() == 1,
        )

        # --- TD3-T115.8 no storage / console / URL leakage -------------------
        storage = page.evaluate(
            "() => ({"
            " localKeys: Object.keys(localStorage),"
            " sessionKeys: Object.keys(sessionStorage),"
            " localDump: JSON.stringify(Object.entries(localStorage)),"
            " sessionDump: JSON.stringify(Object.entries(sessionStorage)),"
            " cookies: document.cookie})"
        )
        check(
            "TD3-T115.8 no pasted payload in localStorage/sessionStorage/document.cookie",
            all(
                probe not in json.dumps(storage, ensure_ascii=False)
                for probe in ("f34-h1", marker, "cluster,hostname,resource_type")
            ),
            f"localKeys={storage['localKeys']} sessionKeys={storage['sessionKeys']} cookies={storage['cookies']!r}",
        )
        check("TD3-T115.8 no browser console errors", console_errors == [], str(console_errors[:3]))
        leaked = [c["url"] for c in api_calls if "f34-h1" in str(c["url"]) or marker in str(c["url"])]
        check("TD3-T115.7 no payload in any request URL", leaked == [], str(leaked))
        results["apiCalls"] = api_calls
        results["storage"] = storage
        results["consoleErrors"] = console_errors

        page.screenshot(path=str(HERE / "logs" / "browser-text-carrier.png"), full_page=True)
        browser.close()

    server.shutdown()
    log(f"\n{failures} failures")
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / "browser-check.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HERE / "browser-check-results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""CSM 离线主机信息采集脚本（F024）。

在目标 Linux 主机本地手工运行，读取本机可观测事实，生成符合
``docs/api/F023.md`` §6 冻结的「资源 + 网卡 + IP」26 列统一宽模板的 CSV，
供维护人员补全业务字段后经既有的两步导入流程导入 CSM。

定位与边界（requirements §24.2 / §24.3 / §24.4）：

* 离线、只读、手动：不连接 CSM、不调用平台 API、不上传、不写库；
* ``--resource-type`` 为必填参数（仅 ``BARE_METAL`` / ``VIRTUAL_MACHINE``），
  写入 ``resource_type`` 列并决定填充硬件列或 VM 列；缺省或非法时本地失败，
  不采集、不写文件、不输出 CSV、不联网；
* 只生成文件，唯一写入目标是 ``-o/--output`` 指定的文件；未指定时默认文件名
  按类型区分：``csm_host_info_bare_metal.csv`` / ``csm_host_info_virtual_machine.csv``；
* 无法可靠获得的业务/归属字段（cluster / role / status / host / network）
  一律留空，由人工补全或经参数提供，不写占位或推断值；
* 无 root 时优先读取免特权来源（如 ``/sys/class/dmi/id``），其余特权字段
  留空且不报错，绝不自动提权；
* 不修改、不扩展 F014 / F023 已冻结模板与导入行为。

仅使用 Python 3 标准库，兼容 Python 3.8+。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# F023 §6 冻结的 26 列统一宽模板（列名与列序不得改动）
# ---------------------------------------------------------------------------

TEMPLATE_COLUMNS = [
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

# 脚本不采集、由人工补全的业务/归属字段。
MANUAL_COLUMNS = {"cluster", "resource_type", "role", "status", "host", "network"}

DEFAULT_EXCLUDED_INTERFACES = {"lo"}


# ---------------------------------------------------------------------------
# 基础读取工具
# ---------------------------------------------------------------------------


def _read_file(path: str) -> str | None:
    """读取文本文件；不可读时返回 None（不抛异常）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _run(*args: str) -> str | None:
    """执行只读命令并返回 stdout；命令缺失或失败时返回 None。"""
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def normalize_hostname(value: str | None) -> str:
    """按 F023 §6 #2 归一化 hostname：trim → 去控制字符 → ASCII 大写折叠小写。"""
    if not value:
        return ""
    cleaned = "".join(ch for ch in value if ch >= " " and ch != "\x7f")
    return cleaned.strip().translate(_ASCII_LOWER)


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


# ---------------------------------------------------------------------------
# 各类信息采集（均可注入依赖以便测试）
# ---------------------------------------------------------------------------


def collect_hostname(read_file=_read_file, run=_run) -> str:
    raw = read_file("/proc/sys/kernel/hostname")
    if raw is None:
        raw = run("hostname")
    # 取第一行，避免末尾换行。
    first = (raw or "").splitlines()[0] if raw else ""
    return normalize_hostname(first)


def collect_memory_mb(read_file=_read_file) -> str:
    """返回整数 MiB 字符串；不可得则为空字符串。"""
    content = read_file("/proc/meminfo")
    if not content:
        return ""
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB", content, re.MULTILINE)
    if not match:
        return ""
    kib = int(match.group(1))
    return str(kib // 1024)


def collect_cpu(read_file=_read_file, run=_run) -> dict:
    """返回 {model, sockets, cores}，未知项为空字符串。

    cores 为整机物理核心总数（不含超线程，T39）：以 (physical id, core id)
    去重计数。无 physical id 时退化为唯一 core id 计数。
    """
    model = ""
    sockets = ""
    cores = ""

    lscpu = run("lscpu")
    if lscpu:
        for line in lscpu.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "model name" and not model:
                model = value
            elif key == "socket(s)":
                sockets = value
    if not model:
        cpuinfo = read_file("/proc/cpuinfo")
        if cpuinfo:
            match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
            if match:
                model = match.group(1).strip()

    cpuinfo = read_file("/proc/cpuinfo")
    if cpuinfo:
        physical: set[tuple[str, str]] = set()
        logical_cores: set[str] = set()
        current_phys = None
        current_core = None
        for line in cpuinfo.splitlines():
            if not line.strip():
                if current_core is not None:
                    physical.add((current_phys or "", current_core))
                    logical_cores.add(current_core)
                current_phys = current_core = None
                continue
            if line.startswith("physical id"):
                current_phys = line.split(":", 1)[1].strip()
            elif line.startswith("core id"):
                current_core = line.split(":", 1)[1].strip()
        if current_core is not None:
            physical.add((current_phys or "", current_core))
            logical_cores.add(current_core)
        if physical:
            cores = str(len(physical))
        elif logical_cores:
            cores = str(len(logical_cores))

    if sockets == "" and cpuinfo:
        phys_ids = set(re.findall(r"^physical id\s*:\s*(\S+)", cpuinfo, re.MULTILINE))
        if phys_ids:
            sockets = str(len(phys_ids))

    return {"model": model, "sockets": sockets, "cores": cores}


def collect_dmi(read_file=_read_file) -> dict:
    """从 /sys/class/dmi/id 读取厂商/型号/序列号（通常免 root）。"""
    base = "/sys/class/dmi/id"
    return {
        "manufacturer": (read_file(f"{base}/sys_vendor") or "").strip(),
        "model": (read_file(f"{base}/product_name") or "").strip(),
        "serial_number": (read_file(f"{base}/product_serial") or "").strip(),
    }


def collect_gpu(run=_run) -> dict:
    """读取 GPU 型号与数量；不可靠时数量留空（T-R6）。"""
    nvidia = run("nvidia-smi", "--query-gpu=name", "--format=csv,noheader")
    if nvidia:
        names = [line.strip() for line in nvidia.splitlines() if line.strip()]
        if names:
            unique = sorted(set(names))
            return {"model": unique[0], "count": str(len(names))}

    lspci = run("lspci")
    if lspci:
        vga = [line for line in lspci.splitlines() if re.search(r"(VGA compatible controller|3D controller)", line)]
        if vga:
            # lspci 无法可靠计数同型号 GPU，数量留空。
            text = vga[0].split(":", 2)[-1].strip()
            return {"model": text, "count": ""}

    return {"model": "", "count": ""}


def collect_vm(read_file=_read_file, run=_run) -> dict:
    """VM 适用字段：vcpu / disk_gb / hypervisor。"""
    vcpu = ""
    try:
        vcpu = str(os.cpu_count()) if os.cpu_count() else ""
    except (TypeError, NotImplementedError):
        vcpu = ""

    hypervisor = ""
    detected = run("systemd-detect-virt")
    if detected:
        value = detected.strip()
        if value and value != "none":
            hypervisor = value

    disk_gb = ""
    lsblk = run("lsblk", "-bdn", "-o", "SIZE")
    if lsblk:
        try:
            total_bytes = sum(int(line.strip()) for line in lsblk.splitlines() if line.strip())
        except ValueError:
            total_bytes = 0
        if total_bytes:
            disk_gb = str(total_bytes // (1024**3))

    return {"vcpu": vcpu, "disk_gb": disk_gb, "hypervisor": hypervisor}


def collect_interfaces(read_file=_read_file, run=_run, include_loopback: bool = False,
                       include_down: bool = False) -> list[dict]:
    """采集网卡与 IPv4 地址。

    每张有 IPv4 的网卡每个地址产生一条记录。默认排除 loopback 与 down 接口。
    interface_type 一律保持 OTHER，不按名称推断（F023 §6 #20）。
    """
    interfaces = _interfaces_from_ip_json(run) or _interfaces_from_ip_text(run)
    if not interfaces:
        interfaces = _interfaces_from_sysfs(read_file)

    results: list[dict] = []
    for iface in interfaces:
        name = iface.get("name", "")
        if not name:
            continue
        if name in DEFAULT_EXCLUDED_INTERFACES and not include_loopback:
            continue
        enabled = iface.get("enabled", "")
        if enabled == "false" and not include_down:
            continue
        ips = iface.get("ips", [])
        if not ips:
            # 无 IPv4 的接口默认跳过；导入模板以每行一个 IP 为单位。
            continue
        for address in ips:
            results.append({
                "name": name,
                "interface_type": "OTHER",
                "mac_address": iface.get("mac_address", ""),
                "speed_mbps": iface.get("speed_mbps", ""),
                "mtu": iface.get("mtu", ""),
                "enabled": enabled,
                "ip": address,
            })
    return results


def _interfaces_from_ip_json(run) -> list[dict]:
    raw = run("ip", "-j", "addr")
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, list):
        return []
    results = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        ips = []
        for info in entry.get("addr_info", []) or []:
            if info.get("family") == "inet" and info.get("local"):
                local = info["local"]
                prefix = info.get("prefixlen")
                ips.append(f"{local}/{prefix}" if prefix is not None else local)
        operstate = entry.get("operstate")
        results.append({
            "name": entry.get("ifname", ""),
            "mac_address": entry.get("address", "") or "",
            "mtu": str(entry.get("mtu", "")) if entry.get("mtu") is not None else "",
            "enabled": _enabled_from_operstate(operstate),
            "speed_mbps": _interface_speed(entry.get("ifname", ""), run),
            "ips": ips,
        })
    return results


def _enabled_from_operstate(operstate: object) -> str:
    """三态：up→true，down→false，其余（unknown/dormant/缺失）→空（不推断）。"""
    value = str(operstate).lower() if operstate is not None else ""
    if value == "up":
        return "true"
    if value == "down":
        return "false"
    return ""


def _interface_speed(name: str, run) -> str:
    raw = run("cat", f"/sys/class/net/{name}/speed")
    if raw:
        value = raw.strip()
        if value.lstrip("-").isdigit() and int(value) > 0:
            return value
    return ""


def _interfaces_from_ip_text(run) -> list[dict]:
    """回退：解析 `ip -o link` 与 `ip -o -4 addr`。"""
    links = run("ip", "-o", "link")
    addrs = run("ip", "-o", "-4", "addr")
    if not links:
        return []
    mac_by_name: dict[str, str] = {}
    mtu_by_name: dict[str, str] = {}
    state_by_name: dict[str, str] = {}
    for line in links.splitlines():
        match = re.match(r"\d+:\s+(\S+):\s+<[^>]*>\s+mtu\s+(\d+).*?state\s+(\S+)", line)
        if not match:
            continue
        name, mtu, state = match.group(1), match.group(2), match.group(3)
        mtu_by_name[name] = mtu
        state_by_name[name] = _enabled_from_operstate(state)
        mac_match = re.search(r"link/ether\s+(\S+)", line)
        if mac_match:
            mac_by_name[name] = mac_match.group(1)
    ips_by_name: dict[str, list[str]] = {}
    for line in (addrs or "").splitlines():
        match = re.match(r"\d+:\s+(\S+)\s+inet\s+(\S+)", line)
        if match:
            ips_by_name.setdefault(match.group(1), []).append(match.group(2))
    names = list(mac_by_name) + [n for n in mtu_by_name if n not in mac_by_name]
    return [{
        "name": name,
        "mac_address": mac_by_name.get(name, ""),
        "mtu": mtu_by_name.get(name, ""),
        "enabled": state_by_name.get(name, "true"),
        "speed_mbps": _interface_speed(name, run),
        "ips": ips_by_name.get(name, []),
    } for name in names]


def _interfaces_from_sysfs(read_file, listdir=os.listdir) -> list[dict]:
    """回退：仅从 /sys/class/net 读取名称/MAC/MTU，无地址信息。"""
    base = "/sys/class/net"
    try:
        names = sorted(listdir(base))
    except OSError:
        return []
    results = []
    for name in names:
        mac = (read_file(f"{base}/{name}/address") or "").strip()
        mtu = (read_file(f"{base}/{name}/mtu") or "").strip()
        operstate = (read_file(f"{base}/{name}/operstate") or "").strip()
        results.append({
            "name": name,
            "mac_address": mac,
            "mtu": mtu,
            "enabled": _enabled_from_operstate(operstate),
            "speed_mbps": "",
            "ips": [],
        })
    return results


# ---------------------------------------------------------------------------
# 行组装与输出
# ---------------------------------------------------------------------------


def build_rows(hostname: str, memory_mb: str, cpu: dict, dmi: dict, gpu: dict,
               vm: dict, interfaces: list[dict], resource_type: str | None,
               manual: dict | None = None) -> list[dict]:
    """把采集结果映射到模板列。

    ``resource_type`` 决定填充哪一组类型专属列，并在提供时写入
    ``resource_type`` 单元格（§24.3）。``manual`` 提供命令行补全的业务/归属
    字段（cluster/role/status/host/network），显式值覆盖默认空值；未提供时
    仍留空，不写占位或推断值。
    """
    manual = manual or {}
    rows: list[dict] = []
    for iface in interfaces:
        row = {column: "" for column in TEMPLATE_COLUMNS}
        row["hostname"] = hostname
        row["memory_mb"] = memory_mb
        if resource_type == "BARE_METAL":
            row["manufacturer"] = dmi.get("manufacturer", "")
            row["model"] = dmi.get("model", "")
            row["serial_number"] = dmi.get("serial_number", "")
            row["cpu_model"] = cpu.get("model", "")
            row["cpu_sockets"] = cpu.get("sockets", "")
            row["cpu_cores"] = cpu.get("cores", "")
            row["gpu_model"] = gpu.get("model", "")
            row["gpu_count"] = gpu.get("count", "")
        elif resource_type == "VIRTUAL_MACHINE":
            row["vcpu"] = vm.get("vcpu", "")
            row["disk_gb"] = vm.get("disk_gb", "")
            row["hypervisor"] = vm.get("hypervisor", "")
        if resource_type:
            row["resource_type"] = resource_type
        for column in ("cluster", "role", "status", "host", "network"):
            value = manual.get(column)
            if value not in (None, ""):
                row[column] = value
        row["name"] = iface.get("name", "")
        row["interface_type"] = iface.get("interface_type", "OTHER")
        row["mac_address"] = iface.get("mac_address", "")
        row["speed_mbps"] = iface.get("speed_mbps", "")
        row["mtu"] = iface.get("mtu", "")
        row["enabled"] = iface.get("enabled", "")
        row["ip"] = iface.get("ip", "")
        rows.append(row)
    return rows


def render_csv(rows: list[dict], include_header: bool = True) -> str:
    """渲染 CSV 文本（RFC 4180），可选是否包含表头。"""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TEMPLATE_COLUMNS, extrasaction="ignore")
    if include_header:
        writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def write_csv(rows: list[dict], output_path: str, include_header: bool = True) -> None:
    """写出 CSV 文件（UTF-8 兼容 BOM）。"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(render_csv(rows, include_header))


def collect(resource_type: str | None, include_loopback: bool, include_down: bool,
            manual: dict | None = None) -> list[dict]:
    """采集本机信息并按 ``resource_type`` 组装模板行。

    ``resource_type: str | None`` 的取值范围**仅供** ``build_rows`` 单测与防御
    边界使用（``None`` ⇒ 类型列留空，见 ``RowMappingTests``）；CLI 侧
    ``--resource-type`` 仍是 ``required=True``（F032 / DR-1007，T101 保证四种调用
    形式缺参均本地失败、零副作用），因此 ``main`` 不会传入 ``None``。
    ``_push`` 对 ``args.resource_type`` 的防御检查同样保留（F036 DR-F036-10 / 11b，
    属既有行为登记，无行为变更）。
    """
    hostname = collect_hostname()
    memory_mb = collect_memory_mb()
    cpu = collect_cpu()
    dmi = collect_dmi()
    gpu = collect_gpu()
    vm = collect_vm()
    interfaces = collect_interfaces(include_loopback=include_loopback, include_down=include_down)
    return build_rows(hostname, memory_mb, cpu, dmi, gpu, vm, interfaces, resource_type, manual)


# ---------------------------------------------------------------------------
# API 推送（消费 F023 导入端点；仅显式 --push 时启用）
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30.0
IMPORT_PATH = "/api/v1/imports/resource-interfaces-ips"


def _multipart_body(fields: dict, filename: str, content: bytes):
    """构造 multipart/form-data 请求体（仅标准库）。"""
    boundary = "----CSMHostInfo" + os.urandom(16).hex()
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(parts)


def post_import(api_url: str, api_key: str, endpoint: str, csv_bytes: bytes,
                timeout: float = DEFAULT_TIMEOUT):
    """向 F023 导入端点发送 multipart 请求，返回 (status, body_text)。

    认证使用 ``Authorization: Bearer <API Key>``（F017）。API Key **不会**出现在
    返回文本或异常信息中。
    """
    url = api_url.rstrip("/") + IMPORT_PATH + endpoint
    boundary, body = _multipart_body({"format": "csv"}, "csm_host_info.csv", csv_bytes)
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        return 0, f"网络错误：{error.reason}"


def _push(rows: list[dict], args) -> int:
    """先预校验展示，经 --yes 确认后写入（§24 两步流程）。"""
    if not args.api_url:
        print("错误：--push 需要 --api-url。", file=sys.stderr)
        return 2
    api_key = args.api_key or os.environ.get("CSM_API_KEY")
    if not api_key:
        print("错误：--push 需要 API Key；请设置环境变量 CSM_API_KEY 或使用 --api-key。", file=sys.stderr)
        return 2
    if not args.cluster or not args.resource_type:
        print("错误：--push 需要同时提供 --cluster 与 --resource-type。", file=sys.stderr)
        return 2
    csv_bytes = render_csv(rows, True).encode("utf-8")
    status, body = post_import(args.api_url, api_key, "/validate", csv_bytes, args.timeout)
    print(body)
    if status != 200:
        print(f"预校验失败（HTTP {status}）。", file=sys.stderr)
        return 1
    try:
        preview = json.loads(body)
    except json.JSONDecodeError:
        preview = {}
    if preview.get("error_count"):
        print("预校验存在错误，未写入。请修正后重试。", file=sys.stderr)
        return 1
    if not args.yes:
        print("预校验通过。加 --yes 以写入。", file=sys.stderr)
        return 0
    status, body = post_import(args.api_url, api_key, "", csv_bytes, args.timeout)
    print(body)
    if status not in (200, 201):
        print(f"写入失败（HTTP {status}）。", file=sys.stderr)
        return 1
    print("推送成功。", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI 表面：枚举、帮助、默认文件名与参数校验
# （F032 / DR-1001–DR-1009、DR-1014–DR-1016；帮助文本离线内嵌，不读取 CSM）
# ---------------------------------------------------------------------------

# §24.1 / §24.3 / §24.4 / F023 §6：枚举取值逐字匹配，不做大小写折叠或短名映射。
RESOURCE_TYPE_VALUES = ("BARE_METAL", "VIRTUAL_MACHINE")
ROLE_VALUES = ("COMPUTE", "LOGIN", "MANAGEMENT", "STORAGE", "SERVICE", "GPU", "OTHER")
STATUS_VALUES = ("IDLE", "ALLOC", "DOWN", "UNKNOWN")

# 未指定 -o/--output 时的默认文件名，按 --resource-type 区分（DR-1005）。
DEFAULT_OUTPUT_BY_TYPE = {
    "BARE_METAL": "csm_host_info_bare_metal.csv",
    "VIRTUAL_MACHINE": "csm_host_info_virtual_machine.csv",
}

# help 内嵌的模板必填列（与 F023 §6 / §6.1 逐行导入校验一致，DR-1003 / DR-1004 ①）。
TEMPLATE_REQUIRED_COLUMNS = ("cluster", "hostname", "resource_type", "name", "ip")
TEMPLATE_REQUIRED_VM_EXTRA = ("host",)

# --push 必填项（--resource-type 因全局必填自动满足，DR-1004 ②）。
PUSH_REQUIRED_ITEMS = (
    ("--api-url", "CSM 基础地址，例如 http://csm.example:8080"),
    ("API Key", "环境变量 CSM_API_KEY 或 --api-key（不落盘、不打印）"),
    ("--cluster", "Cluster code（大小写不敏感）或 UUID"),
)


def build_epilog() -> str:
    """生成 --help 的分区说明：模板必填、--push 必填、枚举值、引用语义、输出默认名。

    文本由本模块常量离线生成（DR-1003 / DR-1014），不请求 F023 模板端点，
    因此帮助内容与实际 ``choices`` / ``required`` 不会漂移。
    """
    template_required = "、".join(TEMPLATE_REQUIRED_COLUMNS)
    vm_extra = "、".join(TEMPLATE_REQUIRED_VM_EXTRA)
    push_items = "\n".join(f"       {name}：{desc}" for name, desc in PUSH_REQUIRED_ITEMS)
    default_names = "\n".join(f"       {value} → {name}" for value, name in DEFAULT_OUTPUT_BY_TYPE.items())
    return (
        "必填与取值说明（离线内嵌常量生成，与实际行为一致）：\n"
        "\n"
        "  ① 模板必填（每行 CSV 逐行校验要求有值，与导入预校验一致）\n"
        f"       {template_required}；VIRTUAL_MACHINE 行另需 {vm_extra}。\n"
        "       脚本可自动获得 hostname / name / ip，resource_type 由 --resource-type 自动写入；\n"
        "       脚本无法自动获得、须经参数或人工补全的模板必填项：cluster（及 VM 的 host）。\n"
        "\n"
        "  ② --push 必填（仅 --push 时要求；脚本必填 ≠ 模板必填）\n"
        f"{push_items}\n"
        "       --resource-type 因全局必填已自动满足。\n"
        "       未提供 --cluster 仍可离线生成 CSV，仅 --push 被拒绝。\n"
        "\n"
        "  ③ 枚举参数可填值（逐字匹配，不做大小写折叠或短名映射）\n"
        f"       --resource-type：{' / '.join(RESOURCE_TYPE_VALUES)}\n"
        f"       --role：{' / '.join(ROLE_VALUES)}\n"
        f"       --status：{' / '.join(STATUS_VALUES)}\n"
        "\n"
        "  ④ 引用型参数语义（脚本只引用、不创建；对象须已存在且未软删）\n"
        "       --cluster：Cluster code（大小写不敏感）或 UUID；须存在且未软删。\n"
        "       --host：同 cluster 内已存在、未软删的 BARE_METAL Host 的 hostname 或 UUID；\n"
        "               仅适用于 VIRTUAL_MACHINE；BARE_METAL 行 host 恒空；\n"
        "               BARE_METAL 与非空 --host 同时给出属非法用法，本地失败（退出码 2）。\n"
        "       --network：同 cluster Network 的 name 或 CIDR；留空时由 ip 的 /mask 解析。\n"
        "\n"
        "  ⑤ 输出与默认文件名\n"
        f"{default_names}\n"
        "       -o/--output 优先于类型默认名；--print 只输出标准输出、不写文件（即使给出 -o）。\n"
    )


def build_error_hint() -> str:
    """参数错误时追加到 argparse 原始错误之后的内容（DR-1007 / R-5）。

    **记载（F036 DR-F036-10 / 11a，F032-RV-05，不改行为）**：「任意 argparse
    错误统一追加三组枚举允许值（--resource-type / --role / --status）」是
    DR-1007 的既有取舍：触发点为 ``_ArgumentParser.error()``，所有参数错误
    （含与本提示无关的参数）都会附上这段文本。收窄为按错误参数精确追加需另立
    变更（涉及 ``error()`` 签名与既有 T101/T102 期望），不属本次范围。
    """
    return (
        "允许值：\n"
        f"  --resource-type: {', '.join(RESOURCE_TYPE_VALUES)}\n"
        f"  --role: {', '.join(ROLE_VALUES)}\n"
        f"  --status: {', '.join(STATUS_VALUES)}\n"
        "使用 --help 查看必填项、枚举值与引用语义。\n"
    )


class _ArgumentParser(argparse.ArgumentParser):
    """保留 argparse 原始错误行，追加允许值与 --help 提示，统一退出码 2（DR-1007）。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n{build_error_hint()}")


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI parser（供 --help、参数解析与 DR-1014 一致性守卫复用）。"""
    parser = _ArgumentParser(
        description="采集本机信息并生成 CSM「资源+网卡+IP」导入模板 CSV（默认离线、只读）。",
        epilog=build_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--resource-type",
        required=True,
        choices=RESOURCE_TYPE_VALUES,
        help="必填。写入 resource_type 列并决定填充硬件列（BARE_METAL）或 vCPU/磁盘/虚拟化列（VIRTUAL_MACHINE）。",
    )
    parser.add_argument(
        "--cluster",
        default=None,
        help="补全 cluster 列：Cluster code（大小写不敏感）或 UUID；--push 必填，离线可留空。",
    )
    parser.add_argument("--role", default=None, choices=ROLE_VALUES, help="补全 role 列；允许值见下方枚举说明。")
    parser.add_argument("--status", default=None, choices=STATUS_VALUES, help="补全 status 列；允许值见下方枚举说明。")
    parser.add_argument(
        "--host",
        default=None,
        help="补全 host 列：同 cluster 内已存在、未软删的 BARE_METAL Host 的 hostname 或 UUID；仅适用于 VIRTUAL_MACHINE。",
    )
    parser.add_argument("--network", default=None, help="补全 network 列：同 cluster Network 的 name 或 CIDR。")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出 CSV 路径；缺省按 --resource-type 使用类型默认文件名。",
    )
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="输出到标准输出（不写文件）。")
    parser.add_argument("--no-header", action="store_true", help="不输出表头。")
    parser.add_argument("--include-loopback", action="store_true", help="包含 loopback 接口（默认排除）。")
    parser.add_argument("--include-down", action="store_true", help="包含明确 down 的接口（默认排除）。")
    parser.add_argument("--push", action="store_true", help="经 API Key 推送到 CSM（默认离线，不联网）。")
    parser.add_argument("--api-url", default=None, help="CSM 基础地址，例如 http://csm.example:8080。")
    parser.add_argument("--api-key", default=None, help="API Key；建议改用环境变量 CSM_API_KEY。")
    parser.add_argument("--yes", action="store_true", help="预校验通过后确认写入。")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP 超时秒数（默认 30）。")
    return parser


def _text_or_none(value: str | None) -> str | None:
    """自由文本参数的「未提供」口径：None 或空白视为未提供（DR-1016）。"""
    if value is None:
        return None
    return value if value.strip() else None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """parse_args() 之后、采集之前的本地校验；任何错误以退出码 2 终止（DR-1008 / DR-1015）。

    argparse 的 ``choices`` / ``required`` 已覆盖枚举与必填；此处只处理跨参数组合：
    ``BARE_METAL`` 行的 ``host`` 恒空（F023 §6.1），因此与非空 ``--host`` 组合属非法用法。
    """
    if args.resource_type == "BARE_METAL" and _text_or_none(args.host) is not None:
        parser.error("argument --host: BARE_METAL 行的 host 恒空，--host 仅适用于 VIRTUAL_MACHINE")


def resolve_output_path(args: argparse.Namespace) -> str:
    """输出路径优先级：``-o/--output`` > 按类型默认名（DR-1005 / DR-1006）。

    ``--print`` 的更高优先级由 ``main()`` 处理（--print 时不写任何文件）。
    """
    explicit = _text_or_none(args.output)
    if explicit is not None:
        return explicit
    return DEFAULT_OUTPUT_BY_TYPE[args.resource_type]


def parse_args(argv: list[str] | None = None,
               parser: argparse.ArgumentParser | None = None) -> argparse.Namespace:
    return (parser or build_parser()).parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # DR-1008：参数解析与本地校验先于采集、写文件、stdout 与网络，任何参数错误零副作用。
    parser = build_parser()
    args = parse_args(argv, parser)
    _validate_args(parser, args)

    manual = {column: _text_or_none(getattr(args, column))
              for column in ("cluster", "role", "status", "host", "network")}
    rows = collect(args.resource_type, args.include_loopback, args.include_down, manual)
    include_header = not args.no_header

    if args.to_stdout:
        sys.stdout.write(render_csv(rows, include_header))
    else:
        output_path = resolve_output_path(args)
        write_csv(rows, output_path, include_header)
        print(f"已写出 {len(rows)} 行到 {output_path}", file=sys.stderr)
    print(f"模板列：{len(TEMPLATE_COLUMNS)} 列（F023 §6 冻结）", file=sys.stderr)

    if args.push:
        return _push(rows, args)

    if not args.to_stdout:
        print("可补全以下字段后再导入：cluster, role, status, host（仅 VM）, network", file=sys.stderr)
    if platform.system() != "Linux":
        print("警告：本脚本面向 Linux；非 Linux 环境下多数采集项将留空。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
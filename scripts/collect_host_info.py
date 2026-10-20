#!/usr/bin/env python3
"""CSM 离线主机信息采集脚本（F024）。

在目标 Linux 主机本地手工运行，读取本机可观测事实，生成符合
``docs/api/F023.md`` §6 冻结的「资源 + 网卡 + IP」26 列统一宽模板的 CSV，
供维护人员补全业务字段后经既有的两步导入流程导入 CSM。

定位与边界（requirements §24.2）：

* 离线、只读、手动：不连接 CSM、不调用平台 API、不上传、不写库；
* 只生成文件，唯一写入目标是 ``-o/--output`` 指定的文件；
* 无法可靠获得的业务/归属字段（cluster / resource_type / role / status /
  host / network）一律留空，由人工补全，不写占位或推断值；
* 无 root 时优先读取免特权来源（如 ``/sys/class/dmi/id``），其余特权字段
  留空且不报错，绝不自动提权；
* 不修改、不扩展 F014 / F023 已冻结模板与导入行为。

仅使用 Python 3 标准库，兼容 Python 3.8+。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys

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
               vm: dict, interfaces: list[dict], resource_type: str | None) -> list[dict]:
    """把采集结果映射到模板列。

    ``resource_type`` 仅用于决定填充哪一组类型专属列，**不写入**
    ``resource_type`` 单元格（该字段由人工补全，§24.2）。未指定时类型专属列
    全部留空，避免与 F023 §6.1 的逐行适用性冲突。
    """
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
        row["name"] = iface.get("name", "")
        row["interface_type"] = iface.get("interface_type", "OTHER")
        row["mac_address"] = iface.get("mac_address", "")
        row["speed_mbps"] = iface.get("speed_mbps", "")
        row["mtu"] = iface.get("mtu", "")
        row["enabled"] = iface.get("enabled", "")
        row["ip"] = iface.get("ip", "")
        rows.append(row)
    return rows


def write_csv(rows: list[dict], output_path: str) -> None:
    """写出 CSV（UTF-8 兼容 BOM，RFC 4180）。"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def collect(resource_type: str | None, include_loopback: bool, include_down: bool) -> list[dict]:
    hostname = collect_hostname()
    memory_mb = collect_memory_mb()
    cpu = collect_cpu()
    dmi = collect_dmi()
    gpu = collect_gpu()
    vm = collect_vm()
    interfaces = collect_interfaces(include_loopback=include_loopback, include_down=include_down)
    return build_rows(hostname, memory_mb, cpu, dmi, gpu, vm, interfaces, resource_type)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="采集本机信息并生成 CSM「资源+网卡+IP」导入模板 CSV（离线、只读）。",
    )
    parser.add_argument(
        "--resource-type",
        choices=["BARE_METAL", "VIRTUAL_MACHINE"],
        default=None,
        help="按类型填充 CPU/GPU/硬件或 vCPU/磁盘/虚拟化列；不写入 resource_type 单元格（由人工补全）。",
    )
    parser.add_argument("-o", "--output", default="csm_host_info.csv", help="输出 CSV 路径（默认 csm_host_info.csv）。")
    parser.add_argument("--include-loopback", action="store_true", help="包含 loopback 接口（默认排除）。")
    parser.add_argument("--include-down", action="store_true", help="包含非 up 状态接口（默认排除）。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect(args.resource_type, args.include_loopback, args.include_down)
    write_csv(rows, args.output)
    print(f"已写出 {len(rows)} 行到 {args.output}")
    print(f"模板列：{len(TEMPLATE_COLUMNS)} 列（F023 §6 冻结）")
    print("请人工补全以下字段后再导入：cluster, resource_type, role, status, host, network")
    if platform.system() != "Linux":
        print("警告：本脚本面向 Linux；非 Linux 环境下多数采集项将留空。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
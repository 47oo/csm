"""F024 / F025 / F032 离线主机信息采集脚本的单元测试。

覆盖 T73–T78（F024）、T79–T84（F025）、T100–T106 与 TD-2 R-1–R-5（F032）。
仅使用标准库与 unittest，可在无 root、无 CSM 网络、无真实硬件的环境中运行；
默认文件名用例在临时目录内运行，不在仓库留下 csm_host_info*.csv。
"""

import argparse
import contextlib
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request

import collect_host_info
from collect_host_info import (
    TEMPLATE_COLUMNS,
    _interfaces_from_sysfs,
    _multipart_body,
    _push,
    build_rows,
    collect_cpu,
    collect_dmi,
    collect_gpu,
    collect_hostname,
    collect_interfaces,
    collect_memory_mb,
    collect_vm,
    main,
    normalize_hostname,
    render_csv,
    write_csv,
)

# F023 §6 冻结的 26 列，逐字逐序。任何改动都必须同步 Contract 版本。
FROZEN_COLUMNS = [
    "cluster", "hostname", "resource_type", "role", "status", "host",
    "vcpu", "memory_mb", "disk_gb", "hypervisor", "manufacturer", "model",
    "serial_number", "cpu_model", "cpu_sockets", "cpu_cores", "gpu_model",
    "gpu_count", "name", "interface_type", "mac_address", "speed_mbps", "mtu",
    "enabled", "network", "ip",
]

CPUINFO_TWO_SOCKETS = """\
processor\t: 0
physical id\t: 0
core id\t\t: 0
model name\t: Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz

processor\t: 1
physical id\t: 0
core id\t\t: 1
model name\t: Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz

processor\t: 2
physical id\t: 1
core id\t\t: 0
model name\t: Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz
"""

IP_JSON = json.dumps([
    {"ifname": "lo", "address": "00:00:00:00:00:00", "mtu": 65536,
     "operstate": "unknown", "addr_info": [{"family": "inet", "local": "127.0.0.1", "prefixlen": 8}]},
    {"ifname": "eth0", "address": "aa:bb:cc:dd:ee:ff", "mtu": 1500,
     "operstate": "up", "addr_info": [
         {"family": "inet", "local": "10.0.0.5", "prefixlen": 24},
         {"family": "inet", "local": "10.0.1.5", "prefixlen": 24},
         {"family": "inet6", "local": "fe80::1", "prefixlen": 64},
     ]},
    {"ifname": "eth1", "address": "aa:bb:cc:dd:ee:01", "mtu": 9000,
     "operstate": "down", "addr_info": [{"family": "inet", "local": "192.168.1.9", "prefixlen": 24}]},
    {"ifname": "eth2", "address": "aa:bb:cc:dd:ee:02", "mtu": 1500,
     "operstate": "up", "addr_info": []},
    {"ifname": "bond0", "address": "aa:bb:cc:dd:ee:03", "mtu": 1500,
     "operstate": "unknown", "addr_info": [{"family": "inet", "local": "10.0.9.9", "prefixlen": 24}]},
])


def fake_run(*args):
    if args == ("ip", "-j", "addr"):
        return IP_JSON
    if args[:2] == ("cat", "/sys/class/net/eth0/speed"):
        return "10000\n"
    if args[:2] == ("cat", "/sys/class/net/eth1/speed"):
        return "-1\n"
    return None


class TemplateDriftTests(unittest.TestCase):
    def test_template_columns_match_f023_frozen(self):
        # T78：内嵌模板必须与 F023 §6 冻结列集一致。
        self.assertEqual(TEMPLATE_COLUMNS, FROZEN_COLUMNS)


class NormalizationTests(unittest.TestCase):
    def test_hostname_trim_and_ascii_lowercase(self):
        self.assertEqual(normalize_hostname("  Node-A1  \n"), "node-a1")

    def test_hostname_removes_control_characters(self):
        self.assertEqual(normalize_hostname("node\x00a1"), "nodea1")

    def test_hostname_missing_is_empty(self):
        self.assertEqual(normalize_hostname(None), "")
        self.assertEqual(normalize_hostname(""), "")

    def test_collect_hostname_uses_proc(self):
        self.assertEqual(collect_hostname(read_file=lambda p: "CN001\n", run=lambda *a: None), "cn001")


class MemoryTests(unittest.TestCase):
    def test_memory_mb_conversion(self):
        meminfo = "MemTotal:       32768000 kB\nMemFree:  1 kB\n"
        self.assertEqual(collect_memory_mb(read_file=lambda p: meminfo), "32000")

    def test_memory_missing_is_empty(self):
        self.assertEqual(collect_memory_mb(read_file=lambda p: None), "")


class CpuTests(unittest.TestCase):
    def test_physical_cores_no_hyperthread(self):
        cpu = collect_cpu(read_file=lambda p: CPUINFO_TWO_SOCKETS, run=lambda *a: None)
        self.assertEqual(cpu["cores"], "3")
        self.assertEqual(cpu["sockets"], "2")
        self.assertEqual(cpu["model"], "Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz")

    def test_cpu_missing_is_empty(self):
        cpu = collect_cpu(read_file=lambda p: None, run=lambda *a: None)
        self.assertEqual(cpu, {"model": "", "sockets": "", "cores": ""})


class DmiTests(unittest.TestCase):
    def test_dmi_reads_sysfs(self):
        files = {
            "/sys/class/dmi/id/sys_vendor": "Dell Inc.\n",
            "/sys/class/dmi/id/product_name": "PowerEdge R740\n",
            "/sys/class/dmi/id/product_serial": "ABC123\n",
        }
        dmi = collect_dmi(read_file=lambda p: files.get(p))
        self.assertEqual(dmi["manufacturer"], "Dell Inc.")
        self.assertEqual(dmi["model"], "PowerEdge R740")
        self.assertEqual(dmi["serial_number"], "ABC123")

    def test_dmi_missing_is_empty(self):
        dmi = collect_dmi(read_file=lambda p: None)
        self.assertEqual(dmi, {"manufacturer": "", "model": "", "serial_number": ""})


class GpuTests(unittest.TestCase):
    def test_nvidia_smi_model_and_count(self):
        def run(*args):
            if args[0] == "nvidia-smi":
                return "A100\nA100\n"
            return None
        gpu = collect_gpu(run=run)
        self.assertEqual(gpu["model"], "A100")
        self.assertEqual(gpu["count"], "2")

    def test_lspci_fallback_count_empty(self):
        def run(*args):
            if args == ("nvidia-smi", "--query-gpu=name", "--format=csv,noheader"):
                return None
            if args == ("lspci",):
                return "01:00.0 VGA compatible controller: NVIDIA Corporation GA100 [A100]\n"
            return None
        gpu = collect_gpu(run=run)
        self.assertIn("NVIDIA", gpu["model"])
        self.assertEqual(gpu["count"], "")

    def test_gpu_missing_is_empty(self):
        self.assertEqual(collect_gpu(run=lambda *a: None), {"model": "", "count": ""})


class VmTests(unittest.TestCase):
    def test_vm_fields(self):
        def run(*args):
            if args == ("systemd-detect-virt",):
                return "kvm\n"
            if args and args[0] == "lsblk":
                return "500000000000\n100000000000\n"
            return None
        vm = collect_vm(run=run, read_file=lambda p: None)
        self.assertEqual(vm["hypervisor"], "kvm")
        self.assertEqual(vm["disk_gb"], str(600_000_000_000 // (1024 ** 3)))
        self.assertTrue(vm["vcpu"] == "" or vm["vcpu"].isdigit())

    def test_vm_missing_is_empty(self):
        vm = collect_vm(run=lambda *a: None, read_file=lambda p: None)
        self.assertEqual(vm["hypervisor"], "")
        self.assertEqual(vm["disk_gb"], "")


class InterfaceTests(unittest.TestCase):
    def test_lo_down_and_no_ip_excluded(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        names = sorted({i["name"] for i in ifaces})
        # eth1 down、eth2 无 IP、lo 均排除；unknown 状态的 bond0 带 IP 应保留（RV-01）。
        self.assertEqual(names, ["bond0", "eth0"])

    def test_ipv4_includes_mask(self):
        # RV-02 / T74：采集 IPv4 掩码（F023 允许 ip 列携带 /mask）。
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        ips = sorted(i["ip"] for i in ifaces)
        self.assertEqual(ips, ["10.0.0.5/24", "10.0.1.5/24", "10.0.9.9/24"])

    def test_unknown_operstate_kept_and_enabled_empty(self):
        # RV-01：unknown 不应被判为 false 并丢弃；enabled 留空（不推断）。
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        bond = [i for i in ifaces if i["name"] == "bond0"]
        self.assertEqual(len(bond), 1)
        self.assertEqual(bond[0]["enabled"], "")

    def test_interface_fields(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        eth0 = [i for i in ifaces if i["name"] == "eth0"]
        self.assertEqual(len(eth0), 2)
        self.assertEqual(eth0[0]["interface_type"], "OTHER")  # 不按名称推断
        self.assertEqual(eth0[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(eth0[0]["mtu"], "1500")
        self.assertEqual(eth0[0]["enabled"], "true")
        self.assertEqual(eth0[0]["speed_mbps"], "10000")

    def test_negative_speed_is_empty(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run, include_loopback=True,
                                    include_down=True)
        eth1 = [i for i in ifaces if i["name"] == "eth1"]
        self.assertEqual(eth1[0]["speed_mbps"], "")

    def test_include_loopback_and_down(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run,
                                    include_loopback=True, include_down=True)
        names = sorted({i["name"] for i in ifaces})
        self.assertEqual(names, ["bond0", "eth0", "eth1", "lo"])

    def test_ip_o_text_fallback(self):
        def run(*args):
            if args == ("ip", "-j", "addr"):
                return None
            if args == ("ip", "-o", "link"):
                return (
                    "1: lo: <LOOPBACK,UP> mtu 65536 state UNKNOWN\n"
                    "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP link/ether aa:bb:cc:dd:ee:ff\n"
                    "3: eth1: <BROADCAST,MULTICAST> mtu 1500 state DOWN link/ether 11:22:33:44:55:66\n"
                )
            if args == ("ip", "-o", "-4", "addr"):
                return "2: eth0    inet 10.0.0.5/24 brd 10.0.0.255 scope global eth0\n"
            return None
        ifaces = collect_interfaces(read_file=lambda p: None, run=run)
        self.assertEqual([i["name"] for i in ifaces], ["eth0"])
        self.assertEqual(ifaces[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(ifaces[0]["mtu"], "1500")
        self.assertEqual(ifaces[0]["enabled"], "true")
        self.assertEqual(ifaces[0]["ip"], "10.0.0.5/24")


class SysfsFallbackTests(unittest.TestCase):
    def test_sysfs_reads_fields_and_tristate(self):
        files = {
            "/sys/class/net/eth0/address": "aa:00:00:00:00:01\n",
            "/sys/class/net/eth0/mtu": "1500\n",
            "/sys/class/net/eth0/operstate": "up\n",
            "/sys/class/net/eth1/address": "aa:00:00:00:00:02\n",
            "/sys/class/net/eth1/mtu": "1500\n",
            "/sys/class/net/eth1/operstate": "unknown\n",
        }
        ifaces = _interfaces_from_sysfs(
            read_file=lambda p: files.get(p),
            listdir=lambda p: ["eth1", "eth0"],
        )
        by_name = {i["name"]: i for i in ifaces}
        self.assertEqual(by_name["eth0"]["enabled"], "true")
        self.assertEqual(by_name["eth1"]["enabled"], "")
        self.assertEqual(by_name["eth0"]["mac_address"], "aa:00:00:00:00:01")


class RowMappingTests(unittest.TestCase):
    def _interfaces(self):
        return [{"name": "eth0", "interface_type": "OTHER", "mac_address": "aa:bb:cc:dd:ee:ff",
                 "speed_mbps": "10000", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5/24"}]

    def test_business_fields_always_empty(self):
        rows = build_rows("node-a1", "32000",
                          {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "ABC"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          self._interfaces(), "BARE_METAL")
        row = rows[0]
        for column in ("cluster", "role", "status", "host", "network"):
            self.assertEqual(row[column], "", f"{column} must be left for manual completion")
        # §24.3：显式提供的 resource_type 会写入该列。
        self.assertEqual(row["resource_type"], "BARE_METAL")
        self.assertEqual(set(row), set(TEMPLATE_COLUMNS))

    def test_bare_metal_fills_hardware_not_vm(self):
        rows = build_rows("n1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          self._interfaces(), "BARE_METAL")
        row = rows[0]
        self.assertEqual(row["manufacturer"], "Dell")
        self.assertEqual(row["cpu_cores"], "40")
        self.assertEqual(row["gpu_model"], "A100")
        for column in ("host", "vcpu", "disk_gb", "hypervisor"):
            self.assertEqual(row[column], "")

    def test_virtual_machine_fills_vm_not_hardware(self):
        rows = build_rows("n1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          self._interfaces(), "VIRTUAL_MACHINE")
        row = rows[0]
        self.assertEqual(row["vcpu"], "8")
        self.assertEqual(row["disk_gb"], "100")
        self.assertEqual(row["hypervisor"], "kvm")
        for column in ("manufacturer", "model", "serial_number", "cpu_model",
                       "cpu_sockets", "cpu_cores", "gpu_model", "gpu_count"):
            self.assertEqual(row[column], "")

    def test_unknown_type_leaves_type_columns_empty(self):
        rows = build_rows("n1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          self._interfaces(), None)
        row = rows[0]
        self.assertEqual(row["memory_mb"], "32000")
        for column in ("manufacturer", "cpu_cores", "vcpu", "hypervisor"):
            self.assertEqual(row[column], "")

    def test_rows_are_deterministic(self):
        # T75：同一输入重复构建产出逐字一致。
        args = ("n1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                {"model": "A100", "count": "2"},
                {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                self._interfaces(), "BARE_METAL")
        self.assertEqual(build_rows(*args), build_rows(*args))


class CsvOutputTests(unittest.TestCase):
    def test_header_order_and_bom(self):
        rows = build_rows("n1", "32000", {}, {}, {}, {},
                          [{"name": "eth0", "interface_type": "OTHER", "mac_address": "m",
                            "speed_mbps": "", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5/24"}],
                          None)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            write_csv(rows, path)
            with open(path, "rb") as handle:
                self.assertTrue(handle.read(3) == b"\xef\xbb\xbf")  # UTF-8 BOM
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader)
                data = next(reader)
        self.assertEqual(header, FROZEN_COLUMNS)
        self.assertEqual(len(data), len(FROZEN_COLUMNS))
        self.assertEqual(data[FROZEN_COLUMNS.index("ip")], "10.0.0.5/24")


def _sample_rows(manual=None, resource_type=None):
    iface = {"name": "eth0", "interface_type": "OTHER", "mac_address": "aa:bb:cc:dd:ee:ff",
             "speed_mbps": "10000", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5/24"}
    return build_rows("node-a1", "32000", {}, {}, {}, {}, [iface], resource_type, manual)


def _push_args(**overrides):
    base = {"api_url": "http://csm.test", "api_key": "supersecretkey",
            "cluster": "C1", "resource_type": "BARE_METAL", "yes": False, "timeout": 30.0}
    base.update(overrides)
    return argparse.Namespace(**base)


class EnhancementTests(unittest.TestCase):
    def test_manual_params_fill_columns(self):
        # T79：参数补全写入对应列；未提供字段仍留空。
        rows = _sample_rows({"cluster": "N96P", "role": "COMPUTE", "status": "IDLE",
                             "network": "mgmt"}, "BARE_METAL")
        row = rows[0]
        self.assertEqual(row["cluster"], "N96P")
        self.assertEqual(row["role"], "COMPUTE")
        self.assertEqual(row["status"], "IDLE")
        self.assertEqual(row["network"], "mgmt")
        self.assertEqual(row["host"], "")

    def test_resource_type_column_written_and_type_columns(self):
        # T80：--resource-type 写入该列并仅填对应类型列。
        bm = _sample_rows({"cluster": "C1"}, "BARE_METAL")[0]
        self.assertEqual(bm["resource_type"], "BARE_METAL")
        self.assertEqual(bm["vcpu"], "")
        vm = build_rows("n1", "1", {}, {}, {}, {"vcpu": "8"},
                        [{"name": "eth0", "interface_type": "OTHER", "mac_address": "",
                          "speed_mbps": "", "mtu": "", "enabled": "", "ip": "10.0.0.5/24"}],
                        "VIRTUAL_MACHINE", {"cluster": "C1", "host": "bm1"})
        self.assertEqual(vm[0]["resource_type"], "VIRTUAL_MACHINE")
        self.assertEqual(vm[0]["host"], "bm1")
        self.assertEqual(vm[0]["manufacturer"], "")

    def test_manual_absent_leaves_columns_empty(self):
        row = _sample_rows(None, None)[0]
        for column in ("cluster", "resource_type", "role", "status", "host", "network"):
            self.assertEqual(row[column], "")

    def test_render_csv_header_toggle(self):
        # T81：带/不带表头。
        rows = _sample_rows()
        with_header = render_csv(rows, True)
        without_header = render_csv(rows, False)
        self.assertEqual(with_header.splitlines()[0], ",".join(FROZEN_COLUMNS))
        self.assertFalse(without_header.startswith("cluster,"))
        self.assertEqual(len(with_header.splitlines()), len(without_header.splitlines()) + 1)

    def test_main_print_writes_stdout_not_file(self):
        original = collect_host_info.collect
        collect_host_info.collect = lambda *a, **k: _sample_rows()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "out.csv")
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    rc = main(["--print", "--resource-type", "BARE_METAL", "-o", path])
                self.assertEqual(rc, 0)
                self.assertFalse(os.path.exists(path))
                self.assertTrue(buffer.getvalue().startswith("cluster,"))
        finally:
            collect_host_info.collect = original

    def test_main_output_file_with_bom(self):
        original = collect_host_info.collect
        collect_host_info.collect = lambda *a, **k: _sample_rows()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "out.csv")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    rc = main(["--resource-type", "BARE_METAL", "-o", path])
                self.assertEqual(rc, 0)
                with open(path, "rb") as handle:
                    self.assertEqual(handle.read(3), b"\xef\xbb\xbf")
        finally:
            collect_host_info.collect = original

    def test_multipart_body_contains_fields(self):
        boundary, body = _multipart_body({"format": "csv"}, "x.csv", b"a,b\n")
        self.assertIn(b"name=\"format\"", body)
        self.assertIn(b"csv", body)
        self.assertIn(b"name=\"file\"; filename=\"x.csv\"", body)
        self.assertTrue(boundary.encode() in body)

    def test_push_validate_then_confirm(self):
        # T82：先 validate，--yes 后写入。
        calls = []
        original = collect_host_info.post_import

        def fake_post(api_url, api_key, endpoint, csv_bytes, timeout=30.0):
            calls.append(endpoint)
            if endpoint == "/validate":
                return 200, '{"error_count": 0, "total_rows": 1}'
            return 201, '{"created": 1}'

        collect_host_info.post_import = fake_post
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = _push(_sample_rows(), _push_args(yes=True))
        finally:
            collect_host_info.post_import = original
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["/validate", ""])

    def test_push_without_yes_does_not_write(self):
        calls = []
        original = collect_host_info.post_import
        collect_host_info.post_import = lambda *a, **k: (calls.append(a[2]), (200, '{"error_count": 0}'))[1]
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = _push(_sample_rows(), _push_args(yes=False))
        finally:
            collect_host_info.post_import = original
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["/validate"])

    def test_push_validation_errors_block_write(self):
        calls = []
        original = collect_host_info.post_import

        def fake_post(*a):
            calls.append(a[2])
            return 200, '{"error_count": 2}'

        collect_host_info.post_import = fake_post
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = _push(_sample_rows(), _push_args(yes=True))
        finally:
            collect_host_info.post_import = original
        self.assertEqual(rc, 1)
        self.assertEqual(calls, ["/validate"])

    def test_push_requires_url_key_and_fields(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(_push(_sample_rows(), _push_args(api_url=None)), 2)
            os.environ.pop("CSM_API_KEY", None)
            self.assertEqual(_push(_sample_rows(), _push_args(api_key=None)), 2)
            self.assertEqual(_push(_sample_rows(), _push_args(cluster=None)), 2)
            self.assertEqual(_push(_sample_rows(), _push_args(resource_type=None)), 2)

    def test_push_api_key_not_leaked(self):
        # T83：Key 不出现在输出。
        original = collect_host_info.post_import
        collect_host_info.post_import = lambda *a: (401, '{"error":{"code":"AUTH_REQUIRED"}}')
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = _push(_sample_rows(), _push_args())
        finally:
            collect_host_info.post_import = original
        self.assertEqual(rc, 1)
        self.assertNotIn("supersecretkey", out.getvalue() + err.getvalue())

    def test_default_mode_does_not_call_network(self):
        # T84：默认（无 --push）不联网。
        original_collect = collect_host_info.collect
        original_post = collect_host_info.post_import
        collect_host_info.collect = lambda *a, **k: _sample_rows()

        def boom(*a, **k):
            raise AssertionError("network call in offline mode")

        collect_host_info.post_import = boom
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "out.csv")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    rc = main(["--resource-type", "BARE_METAL", "-o", path])
            self.assertEqual(rc, 0)
        finally:
            collect_host_info.collect = original_collect
            collect_host_info.post_import = original_post


# ---------------------------------------------------------------------------
# F032：–resource-type 必填、帮助分区、按类型默认文件名、非法枚举 fail-fast
# （T100–T106、TD-2 R-1–R-5；见 docs/features/F032/architecture.md）
# ---------------------------------------------------------------------------

SAMPLE_IFACE = {"name": "eth0", "interface_type": "OTHER", "mac_address": "aa:bb:cc:dd:ee:ff",
                "speed_mbps": "10000", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5/24"}


def _parse_csv(text):
    """将 CSV 文本解析为 list[list[str]]（首行为表头）。"""
    return list(csv.reader(io.StringIO(text)))


def _column_values(rows, column):
    """返回数据行（不含表头）在指定列上的取值列表。"""
    index = rows[0].index(column)
    return [row[index] for row in rows[1:]]


class _CliTestCase(unittest.TestCase):
    """CLI 用例基类：临时工作目录隔离 + 采集/网络探针（默认禁止真实副作用）。"""

    def setUp(self):
        self._saved_cwd = os.getcwd()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.chdir(self._tmpdir.name)
        self.addCleanup(os.chdir, self._saved_cwd)
        self.collect_calls = 0
        self.network_calls = 0
        self._patch(collect_host_info, "collect", self._fake_collect)
        self._patch(collect_host_info, "post_import", self._fake_post)
        self._patch(urllib.request, "urlopen", self._fake_urlopen)

    # -- 测试基础设施 ---------------------------------------------------

    def _patch(self, target, attr, value):
        original = getattr(target, attr)
        setattr(target, attr, value)
        self.addCleanup(setattr, target, attr, original)

    def _fake_collect(self, resource_type=None, include_loopback=False, include_down=False, manual=None):
        self.collect_calls += 1
        return _sample_rows(manual, resource_type)

    def _fake_post(self, *args, **kwargs):
        self.network_calls += 1
        raise AssertionError("post_import must not be called")

    def _fake_urlopen(self, *args, **kwargs):
        self.network_calls += 1
        raise AssertionError("urlopen must not be called")

    def _run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _run_main_expect_exit(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                main(argv)
        return raised.exception.code, out.getvalue(), err.getvalue()

    def _assert_no_local_side_effect(self, out):
        self.assertEqual(self.collect_calls, 0, "参数错误必须在采集前终止（DR-1008）")
        self.assertEqual(self.network_calls, 0, "参数错误不得发起网络请求")
        self.assertFalse(out.strip(), "参数错误不得向 stdout 输出 CSV 行")
        self.assertEqual(os.listdir(self._tmpdir.name), [], "参数错误不得创建文件")


class CliHelpTests(unittest.TestCase):
    """T100 / R-1 / R-5：--help 分区说明与真实 choices 一致，且离线生成。"""

    def setUp(self):
        self.parser = collect_host_info.build_parser()
        self.help_text = self.parser.format_help()
        self.epilog = collect_host_info.build_epilog()

    def test_help_marks_type_required_with_both_values(self):
        self.assertIn("--resource-type", self.help_text)
        self.assertIn("必填", self.help_text)
        for value in collect_host_info.RESOURCE_TYPE_VALUES:
            self.assertIn(value, self.help_text)

    def test_help_lists_all_role_values(self):
        self.assertIn("--role", self.epilog)
        for value in collect_host_info.ROLE_VALUES:
            self.assertIn(value, self.epilog)

    def test_help_lists_all_status_values(self):
        self.assertIn("--status", self.epilog)
        for value in collect_host_info.STATUS_VALUES:
            self.assertIn(value, self.epilog)

    def test_help_has_template_required_section(self):
        # DR-1004 ①：模板必填列与 VM 额外的 host。
        self.assertIn("模板必填", self.epilog)
        for column in collect_host_info.TEMPLATE_REQUIRED_COLUMNS:
            self.assertIn(column, self.epilog)
        self.assertIn("VIRTUAL_MACHINE 行另需 host", self.epilog)

    def test_help_has_push_required_section(self):
        # DR-1004 ②：--push 必填与「脚本必填 ≠ 模板必填」。
        self.assertIn("--push 必填", self.epilog)
        self.assertIn("--api-url", self.epilog)
        self.assertIn("CSM_API_KEY", self.epilog)
        self.assertIn("脚本必填 ≠ 模板必填", self.epilog)
        self.assertIn("未提供 --cluster 仍可离线生成 CSV", self.epilog)

    def test_help_reference_semantics(self):
        # DR-1004 ④：引用型参数的寻址与「须已存在且未软删」语义。
        self.assertIn("Cluster code", self.epilog)
        self.assertIn("UUID", self.epilog)
        self.assertIn("hostname 或 UUID", self.epilog)
        self.assertIn("CIDR", self.epilog)
        self.assertIn("须存在且未软删", self.epilog)
        self.assertIn("/mask", self.epilog)

    def test_help_states_host_applicability(self):
        # TD-2 R-1：--host 仅适用于 VM，BM 行 host 恒空。
        self.assertIn("仅适用于 VIRTUAL_MACHINE", self.epilog)
        self.assertIn("BARE_METAL 行 host 恒空", self.epilog)

    def test_epilog_values_equal_parser_choices(self):
        # DR-1014 / B-19：帮助文本与真实 choices/required 不得漂移。
        actions = {action.dest: action for action in self.parser._actions}
        self.assertEqual(tuple(actions["resource_type"].choices), collect_host_info.RESOURCE_TYPE_VALUES)
        self.assertEqual(tuple(actions["role"].choices), collect_host_info.ROLE_VALUES)
        self.assertEqual(tuple(actions["status"].choices), collect_host_info.STATUS_VALUES)
        self.assertTrue(actions["resource_type"].required)
        for value in collect_host_info.ROLE_VALUES:
            self.assertIn(value, self.epilog)
        for value in collect_host_info.STATUS_VALUES:
            self.assertIn(value, self.epilog)

    def test_help_makes_no_network_call(self):
        # B-18：help/epilog 离线生成，不请求 F023 模板端点。
        original_post = collect_host_info.post_import
        original_open = urllib.request.urlopen

        def boom(*args, **kwargs):
            raise AssertionError("help must not call network")

        collect_host_info.post_import = boom
        urllib.request.urlopen = boom
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(["--help"])
        finally:
            collect_host_info.post_import = original_post
            urllib.request.urlopen = original_open
        self.assertEqual(raised.exception.code, 0)


class RequiredResourceTypeTests(_CliTestCase):
    """T101：任调用形式缺 --resource-type 均本地失败，且零副作用。"""

    def _assert_fail(self, argv):
        code, out, err = self._run_main_expect_exit(argv)
        self.assertEqual(code, 2)
        self.assertIn("--resource-type", err)
        for value in collect_host_info.RESOURCE_TYPE_VALUES:
            self.assertIn(value, err)
        self.assertIn("--help", err)
        self._assert_no_local_side_effect(out)

    def test_missing_type_no_args(self):
        self._assert_fail([])

    def test_missing_type_only_print(self):
        self._assert_fail(["--print"])

    def test_missing_type_only_output(self):
        sentinel = os.path.join(self._tmpdir.name, "sentinel.csv")
        with open(sentinel, "wb") as handle:
            handle.write(b"sentinel-bytes")
        code, out, err = self._run_main_expect_exit(["-o", sentinel])
        self.assertEqual(code, 2)
        self.assertIn("--resource-type", err)
        with open(sentinel, "rb") as handle:
            self.assertEqual(handle.read(), b"sentinel-bytes", "已存在文件不得被覆盖")
        self.assertEqual(self.collect_calls, 0)
        self.assertEqual(self.network_calls, 0)
        self.assertFalse(out.strip())

    def test_missing_type_only_push(self):
        self._assert_fail(["--push", "--api-url", "http://localhost:18080",
                           "--api-key", "f032-key", "--cluster", "F032CHK", "--yes"])

    def test_missing_type_subprocess_rc(self):
        script = os.path.abspath(collect_host_info.__file__)
        completed = subprocess.run([sys.executable, script, "--print"],
                                   cwd=self._tmpdir.name, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--resource-type", completed.stderr)
        self.assertEqual(sorted(os.listdir(self._tmpdir.name)), [])


class BmOutputTests(_CliTestCase):
    """T102 / R-2：BM 行内容、冻结 26 列表头与 BM + --host 反例。"""

    def test_bm_row_type_and_hardware_columns(self):
        rows = build_rows("node-a1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          [dict(SAMPLE_IFACE)], "BARE_METAL")
        row = rows[0]
        self.assertEqual(row["resource_type"], "BARE_METAL")
        self.assertEqual(row["manufacturer"], "Dell")
        self.assertEqual(row["gpu_count"], "2")
        for column in ("host", "vcpu", "disk_gb", "hypervisor"):
            self.assertEqual(row[column], "")

    def test_bm_header_is_frozen_26_columns(self):
        rc, out, _ = self._run_main(["--print", "--resource-type", "BARE_METAL"])
        self.assertEqual(rc, 0)
        rows = _parse_csv(out)
        self.assertEqual(rows[0], FROZEN_COLUMNS)
        self.assertEqual(sorted({value for value in _column_values(rows, "resource_type")}), ["BARE_METAL"])

    def test_bm_cli_print_rows(self):
        rc, out, _ = self._run_main(["--print", "--resource-type", "BARE_METAL"])
        self.assertEqual(rc, 0)
        rows = _parse_csv(out)
        for column in ("host", "vcpu", "disk_gb", "hypervisor"):
            self.assertEqual(set(_column_values(rows, column)), {""})

    def test_bm_with_host_rejected(self):
        # DR-1015 / R-2：BM + 非空 --host 属非法用法。
        code, out, err = self._run_main_expect_exit(
            ["--print", "--resource-type", "BARE_METAL", "--host", "f032host"])
        self.assertEqual(code, 2)
        self.assertIn("--host", err)
        self.assertIn("VIRTUAL_MACHINE", err)
        self._assert_no_local_side_effect(out)

    def test_bm_with_host_rejected_does_not_touch_output(self):
        sentinel = "sentinel.csv"
        with open(sentinel, "wb") as handle:
            handle.write(b"sentinel-bytes")
        code, out, _ = self._run_main_expect_exit(
            ["--resource-type", "BARE_METAL", "--host", "f032host", "-o", sentinel])
        self.assertEqual(code, 2)
        with open(sentinel, "rb") as handle:
            self.assertEqual(handle.read(), b"sentinel-bytes")
        self.assertFalse(os.path.exists("csm_host_info_bare_metal.csv"))
        self.assertEqual(self.collect_calls, 0)
        self.assertEqual(self.network_calls, 0)
        self.assertFalse(out.strip())

    def test_bm_host_empty_string_is_unset(self):
        # DR-1015 / R-2：--host "" 视为未提供。
        rc, out, _ = self._run_main(["--print", "--resource-type", "BARE_METAL", "--host", ""])
        self.assertEqual(rc, 0)
        self.assertEqual(set(_column_values(_parse_csv(out), "host")), {""})

    def test_vm_host_still_accepted(self):
        # 防误伤 T103：VM + --host 仍写入。
        rc, out, _ = self._run_main(["--print", "--resource-type", "VIRTUAL_MACHINE",
                                     "--host", "f032host"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(_column_values(_parse_csv(out), "host")), {"f032host"})

    def test_bm_with_host_subprocess_rc(self):
        script = os.path.abspath(collect_host_info.__file__)
        completed = subprocess.run(
            [sys.executable, script, "--print", "--resource-type", "BARE_METAL", "--host", "f032host"],
            cwd=self._tmpdir.name, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout.strip())
        self.assertIn("--host", completed.stderr)


class VmOutputTests(_CliTestCase):
    """T103：VM 行内容与 host 可选用法。"""

    def test_vm_row_type_and_vm_columns(self):
        rows = build_rows("node-a1", "32000", {"model": "Xeon", "sockets": "2", "cores": "40"},
                          {"manufacturer": "Dell", "model": "R740", "serial_number": "S"},
                          {"model": "A100", "count": "2"},
                          {"vcpu": "8", "disk_gb": "100", "hypervisor": "kvm"},
                          [dict(SAMPLE_IFACE)], "VIRTUAL_MACHINE")
        row = rows[0]
        self.assertEqual(row["resource_type"], "VIRTUAL_MACHINE")
        self.assertEqual(row["vcpu"], "8")
        self.assertEqual(row["disk_gb"], "100")
        self.assertEqual(row["hypervisor"], "kvm")
        for column in ("manufacturer", "model", "serial_number", "cpu_model",
                       "cpu_sockets", "cpu_cores", "gpu_model", "gpu_count"):
            self.assertEqual(row[column], "")

    def test_vm_host_absent_is_empty(self):
        rc, out, _ = self._run_main(["--print", "--resource-type", "VIRTUAL_MACHINE"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(_column_values(_parse_csv(out), "host")), {""})

    def test_vm_header_is_frozen_26_columns(self):
        rc, out, _ = self._run_main(["--print", "--resource-type", "VIRTUAL_MACHINE"])
        self.assertEqual(rc, 0)
        rows = _parse_csv(out)
        self.assertEqual(rows[0], FROZEN_COLUMNS)
        self.assertEqual(sorted({value for value in _column_values(rows, "resource_type")}),
                         ["VIRTUAL_MACHINE"])


class DefaultOutputNameTests(_CliTestCase):
    """T104 / DR-1005 / DR-1006：类型化默认名与输出优先级。"""

    def test_bm_default_filename(self):
        rc, out, _ = self._run_main(["--resource-type", "BARE_METAL"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertTrue(os.path.exists("csm_host_info_bare_metal.csv"))
        self.assertFalse(os.path.exists("csm_host_info_virtual_machine.csv"))

    def test_vm_default_filename(self):
        rc, _, _ = self._run_main(["--resource-type", "VIRTUAL_MACHINE"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists("csm_host_info_virtual_machine.csv"))
        self.assertFalse(os.path.exists("csm_host_info_bare_metal.csv"))

    def test_two_runs_do_not_overwrite(self):
        self._run_main(["--resource-type", "BARE_METAL"])
        with open("csm_host_info_bare_metal.csv", "rb") as handle:
            bm_bytes = handle.read()
        self._run_main(["--resource-type", "VIRTUAL_MACHINE"])
        with open("csm_host_info_bare_metal.csv", "rb") as handle:
            self.assertEqual(handle.read(), bm_bytes)
        with open("csm_host_info_virtual_machine.csv", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(set(_column_values(rows, "resource_type")), {"VIRTUAL_MACHINE"})

    def test_output_flag_overrides_default(self):
        rc, _, _ = self._run_main(["--resource-type", "BARE_METAL", "-o", "custom.csv"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists("custom.csv"))
        self.assertFalse(os.path.exists("csm_host_info_bare_metal.csv"))

    def test_print_with_output_writes_nothing(self):
        rc, out, _ = self._run_main(["--print", "--resource-type", "BARE_METAL", "-o", "p.csv"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("cluster,"))
        self.assertFalse(os.path.exists("p.csv"))
        self.assertFalse(os.path.exists("csm_host_info_bare_metal.csv"))

    def test_legacy_default_name_not_used(self):
        self._run_main(["--resource-type", "BARE_METAL"])
        self.assertFalse(os.path.exists("csm_host_info.csv"))


class InvalidEnumTests(_CliTestCase):
    """T105 / R-3：非法枚举与空串枚举本地 fail-fast，无大小写折叠/短名映射。"""

    def _assert_enum_failure(self, argv, expected_values):
        code, out, err = self._run_main_expect_exit(argv)
        self.assertEqual(code, 2)
        for value in expected_values:
            self.assertIn(value, err)
        self.assertIn("--help", err)
        self._assert_no_local_side_effect(out)

    def test_invalid_resource_type_values(self):
        for value in ("bare_metal", "Bare_Metal", "bm", "", "PHYSICAL", "bare metal"):
            with self.subTest(value=value):
                self._assert_enum_failure(["--print", "--resource-type", value],
                                          collect_host_info.RESOURCE_TYPE_VALUES)

    def test_invalid_role_values(self):
        for value in ("compute", "ADMIN"):
            with self.subTest(value=value):
                self._assert_enum_failure(
                    ["--print", "--resource-type", "BARE_METAL", "--role", value],
                    collect_host_info.ROLE_VALUES)

    def test_invalid_status_values(self):
        self._assert_enum_failure(
            ["--print", "--resource-type", "BARE_METAL", "--status", "running"],
            collect_host_info.STATUS_VALUES)

    def test_empty_string_enum_rejected(self):
        # DR-1016 / R-3：--role "" / --status "" 必为 rc=2（不回退为「未提供」）。
        for option, values in (("--role", collect_host_info.ROLE_VALUES),
                               ("--status", collect_host_info.STATUS_VALUES)):
            with self.subTest(option=option, mode="print"):
                self._assert_enum_failure(
                    ["--print", "--resource-type", "BARE_METAL", option, ""], values)
        sentinel = os.path.join(self._tmpdir.name, "sentinel.csv")
        with open(sentinel, "wb") as handle:
            handle.write(b"sentinel-bytes")
        code, out, err = self._run_main_expect_exit(
            ["--resource-type", "BARE_METAL", "--role", "", "-o", sentinel])
        self.assertEqual(code, 2)
        self.assertIn("LOGIN", err)
        with open(sentinel, "rb") as handle:
            self.assertEqual(handle.read(), b"sentinel-bytes")
        self.assertEqual(self.collect_calls, 0)
        self.assertEqual(self.network_calls, 0)
        self.assertFalse(out.strip())

    def test_no_case_folding_no_alias(self):
        # T105：小写与短名均不得被接受为 BARE_METAL。
        for value in ("bare_metal", "bm", "BAREMETAL"):
            with self.subTest(value=value):
                code, _, _ = self._run_main_expect_exit(
                    ["--print", "--resource-type", value])
                self.assertEqual(code, 2)


class FreeTextEmptyStringTests(_CliTestCase):
    """DR-1016 / R-4：自由文本空串视为未提供；--push --cluster "" 行为不变。"""

    def test_empty_free_text_is_unset(self):
        rc, out, _ = self._run_main(
            ["--print", "--resource-type", "BARE_METAL", "--cluster", "", "--network", ""])
        self.assertEqual(rc, 0)
        rows = _parse_csv(out)
        self.assertEqual(set(_column_values(rows, "cluster")), {""})
        self.assertEqual(set(_column_values(rows, "network")), {""})

    def test_push_empty_cluster_behaviour_unchanged(self):
        # 沿用 F025 `_push()` 前置校验：空 --cluster 仍拒绝推送（rc=2），且不发起请求。
        rc, _, err = self._run_main(
            ["--print", "--resource-type", "BARE_METAL", "--push",
             "--api-url", "http://localhost:18080", "--api-key", "f032-key", "--cluster", ""])
        self.assertEqual(rc, 2)
        self.assertIn("--cluster", err)
        self.assertEqual(self.network_calls, 0)


class ContractMultipartTests(unittest.TestCase):
    """T106 / DR-1009：端点与 multipart 上传文件名不变。"""

    def test_multipart_filename_unchanged(self):
        # DR-1009：上传文件名仍为 csm_host_info.csv，不随本地默认名变化。
        captured = {}

        class _FakeResponse:
            status = 200

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        def fake_urlopen(request, timeout=None):
            captured["body"] = request.data
            captured["url"] = request.get_full_url()
            return _FakeResponse()

        original = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            status, _body = collect_host_info.post_import(
                "http://localhost:18080", "f032-key", "/validate", b"cluster,hostname\n")
        finally:
            urllib.request.urlopen = original
        self.assertEqual(status, 200)
        self.assertIn(b'filename="csm_host_info.csv"', captured["body"])
        self.assertTrue(captured["url"].endswith("/api/v1/imports/resource-interfaces-ips/validate"))


class ContractGuardTests(_CliTestCase):
    """T106：离线默认行为与 Key 不外泄不变。"""

    def test_offline_run_has_no_network_and_no_api_key_write(self):
        saved = os.environ.get("CSM_API_KEY")
        os.environ["CSM_API_KEY"] = "f032-offline-secret"
        try:
            rc, out, err = self._run_main(["--print", "--resource-type", "BARE_METAL"])
        finally:
            if saved is None:
                os.environ.pop("CSM_API_KEY", None)
            else:
                os.environ["CSM_API_KEY"] = saved
        self.assertEqual(rc, 0)
        self.assertEqual(self.network_calls, 0)
        self.assertNotIn("f032-offline-secret", out + err)
        self.assertEqual(os.listdir(self._tmpdir.name), [], "--print 不写任何文件")


if __name__ == "__main__":
    unittest.main()
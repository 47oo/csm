"""F024 离线主机信息采集脚本的单元测试（T73–T78 的自动化部分）。

仅使用标准库与 unittest，可在无 root、无 CSM 网络、无真实硬件的环境中运行。
"""

import csv
import json
import os
import tempfile
import unittest

from collect_host_info import (
    TEMPLATE_COLUMNS,
    _interfaces_from_sysfs,
    build_rows,
    collect_cpu,
    collect_dmi,
    collect_gpu,
    collect_hostname,
    collect_interfaces,
    collect_memory_mb,
    collect_vm,
    normalize_hostname,
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
        for column in ("cluster", "resource_type", "role", "status", "host", "network"):
            self.assertEqual(row[column], "", f"{column} must be left for manual completion")
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


if __name__ == "__main__":
    unittest.main()
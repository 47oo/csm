"""F024 离线主机信息采集脚本的单元测试（T73–T78 的自动化部分）。

仅使用标准库与 unittest，可在无 root、无 CSM 网络、无真实硬件的环境中运行。
"""

import csv
import io
import json
import os
import tempfile
import unittest

from collect_host_info import (
    TEMPLATE_COLUMNS,
    build_rows,
    collect_cpu,
    collect_dmi,
    collect_hostname,
    collect_interfaces,
    collect_memory_mb,
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
    def test_hostname_trim_and_lowercase(self):
        self.assertEqual(normalize_hostname("  Node-A1  \n"), "node-a1")

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


class InterfaceTests(unittest.TestCase):
    def test_lo_and_down_excluded_by_default(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        names = {i["name"] for i in ifaces}
        self.assertEqual(names, {"eth0"})  # eth1 down、eth2 无 IP、lo 均排除
        ips = sorted(i["ip"] for i in ifaces)
        self.assertEqual(ips, ["10.0.0.5", "10.0.1.5"])

    def test_interface_fields(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run)
        eth0 = [i for i in ifaces if i["name"] == "eth0"]
        self.assertEqual(len(eth0), 2)
        self.assertEqual(eth0[0]["interface_type"], "OTHER")  # 不按名称推断
        self.assertEqual(eth0[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(eth0[0]["mtu"], "1500")
        self.assertEqual(eth0[0]["enabled"], "true")
        self.assertEqual(eth0[0]["speed_mbps"], "10000")

    def test_include_loopback_and_down(self):
        ifaces = collect_interfaces(read_file=lambda p: None, run=fake_run,
                                    include_loopback=True, include_down=True)
        names = sorted({i["name"] for i in ifaces})
        self.assertEqual(names, ["eth0", "eth1", "lo"])


class RowMappingTests(unittest.TestCase):
    def _interfaces(self):
        return [{"name": "eth0", "interface_type": "OTHER", "mac_address": "aa:bb:cc:dd:ee:ff",
                 "speed_mbps": "10000", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5"}]

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


class CsvOutputTests(unittest.TestCase):
    def test_header_order_and_bom(self):
        rows = build_rows("n1", "32000", {}, {}, {}, {},
                          [{"name": "eth0", "interface_type": "OTHER", "mac_address": "m",
                            "speed_mbps": "", "mtu": "1500", "enabled": "true", "ip": "10.0.0.5"}],
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
        self.assertEqual(data[FROZEN_COLUMNS.index("ip")], "10.0.0.5")


if __name__ == "__main__":
    unittest.main()
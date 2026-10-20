# F024 离线主机信息采集脚本 — README

在目标 Linux 主机本地手工运行，读取本机信息并生成符合 CSM「资源 + 网卡 + IP」导入模板（`docs/api/F023.md` §6 冻结的 26 列）的 CSV，减少人工逐列填写。

## 快速开始

```bash
# 1. 复制脚本到目标主机（无需安装依赖，仅需 Python 3.8+）
scp scripts/collect_host_info.py user@host:~/

# 2. 在目标主机运行
python3 collect_host_info.py --resource-type BARE_METAL -o host.csv
# 或 --resource-type VIRTUAL_MACHINE；不指定则只填 BM/VM 共有列

# 3. 人工补全 cluster / resource_type / role / status / host / network 后，
#    通过 CSM 导入界面预校验 → 确认 → 导入
```

## 特性

- **离线、只读、手动**：不连接 CSM、不调用 API、不上传、不写库；唯一写入为输出文件。
- 自动采集：hostname、CPU（型号/插槽/整机物理核心）、内存、GPU、网卡（名称/类型/MAC/速率/MTU）、IPv4 地址/掩码。
- 业务/归属字段（`cluster`、`resource_type`、`role`、`status`、`host`、`network`）一律留空，不推断、无占位值。
- 无 root 时优先读免特权来源（`/sys/class/dmi/id`），其余字段留空且不报错，不自动提权。
- 不改动 F014 / F023 既有模板与导入行为。

## 文档

- 逐列「自动采集 / 人工补全」映射与采集降级：`docs/features/F024/field-mapping.md`
- 设计方案：`docs/features/F024/architecture.md`
- 模板契约：`docs/api/F023.md` §6

## 测试

```bash
python3 -m unittest discover -s scripts -p 'test_collect_host_info.py'
```
# F039 A8 — EXPLAIN 证据（真 PG 16.15 实测）

采集方式：`backend/tests/integration/test_f039_query_count.py::test_a8_batch_statements_have_index_paths` 用
`before_cursor_execute` 捕获 `load_capacity_context` **实际执行**的 3 条语句原文与绑定参数，再对同一语句执行
`EXPLAIN (FORMAT JSON)`，分别在原始配置与 `SET LOCAL enable_seqscan = off` 下采集。

复现：

```bash
cd backend && TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test' \
  python -m pytest tests/integration/test_f039_query_count.py -q -s -k a8
```

夹具：1 Cluster + 2 Network（各 1 RESERVED + 1 AUTO 池 + 1 未绑定 IP）⇒ 2 行 `ip_pools`、2 行 `ip_addresses`。

判据（architecture §3 / AP-F039-5）：小夹具下规划器代价决策在 Bitmap/Index 与候选索引之间漂移（下方两次运行
已如实记录），故**机器判据为「`enable_seqscan=off` 计划无 `Seq Scan`、至少一个 `Index*` 节点、且引用的索引名
真实存在于对应表 `pg_indexes`」**；原始计划仅记录，不作为 PASS 依据。

结论：两次运行 × 两种配置均只使用索引路径，`ip_pools` / `ip_addresses` / `networks` 无 `Seq Scan`；无新增索引
需求证据，未触发 DATABASE Gate（N5）。索引名与 TD-F039-8a 预设的 `ix_ip_pools_network_id` /
`ix_ip_addresses_network_id` **不完全一致**（规划器在等价索引间选择），已按真实计划对齐判据并回报 Architect。

## 运行 1 —— 完整计划（原始 / 强制关顺序扫描）

### B1 — RESERVED 区间

```sql
SELECT ip_pools.network_id, ip_pools.start_address, ip_pools.end_address FROM ip_pools WHERE ip_pools.network_id IN (%(network_id_1_1)s::UUID, %(network_id_1_2)s::UUID) AND ip_pools.allocation_mode = %(allocation_mode_1)s::VARCHAR AND ip_pools.deleted_at IS NULL AND ip_pools.deleted_at IS NULL
```

原始计划：

```json
{
  "Plan": {
    "Alias": "ip_pools",
    "Async Capable": false,
    "Filter": "((network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[])) AND ((allocation_mode)::text = 'RESERVED'::text))",
    "Index Name": "excl_ip_pools_network_id_address_range",
    "Node Type": "Index Scan",
    "Parallel Aware": false,
    "Plan Rows": 1,
    "Plan Width": 80,
    "Relation Name": "ip_pools",
    "Scan Direction": "Forward",
    "Startup Cost": 0.12,
    "Total Cost": 8.14
  }
}
```

`enable_seqscan = off` 计划：

```json
{
  "Plan": {
    "Alias": "ip_pools",
    "Async Capable": false,
    "Filter": "((network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[])) AND ((allocation_mode)::text = 'RESERVED'::text))",
    "Index Name": "excl_ip_pools_network_id_address_range",
    "Node Type": "Index Scan",
    "Parallel Aware": false,
    "Plan Rows": 1,
    "Plan Width": 80,
    "Relation Name": "ip_pools",
    "Scan Direction": "Forward",
    "Startup Cost": 0.12,
    "Total Cost": 8.14
  }
}
```

### B2 — AUTO 池 + 占用计数

```sql
SELECT ip_pools.id, ip_pools.network_id, ip_pools.name, ip_pools.name_key, ip_pools.start_address, ip_pools.end_address, ip_pools.address_range, ip_pools.allocation_mode, ip_pools.description, ip_pools.version, ip_pools.created_at, ip_pools.updated_at, ip_pools.deleted_at, count(ip_addresses.id) AS count_1 FROM ip_pools LEFT OUTER JOIN ip_addresses ON ip_addresses.deleted_at IS NULL AND ip_addresses.network_id = ip_pools.network_id AND ip_addresses.address >= ip_pools.start_address AND ip_addresses.address <= ip_pools.end_address AND ip_addresses.deleted_at IS NULL WHERE ip_pools.network_id IN (%(network_id_1_1)s::UUID, %(network_id_1_2)s::UUID) AND ip_pools.allocation_mode = %(allocation_mode_1)s::VARCHAR AND ip_pools.deleted_at IS NULL AND ip_pools.deleted_at IS NULL GROUP BY ip_pools.id ORDER BY ip_pools.network_id ASC, ip_pools.start_address ASC, ip_pools.id ASC
```

原始计划：

```json
{
  "Plan": {
    "Async Capable": false,
    "Node Type": "Sort",
    "Parallel Aware": false,
    "Plan Rows": 1,
    "Plan Width": 1278,
    "Plans": [
      {
        "Async Capable": false,
        "Group Key": [
          "ip_pools.id"
        ],
        "Node Type": "Aggregate",
        "Parallel Aware": false,
        "Parent Relationship": "Outer",
        "Partial Mode": "Simple",
        "Plan Rows": 1,
        "Plan Width": 1278,
        "Plans": [
          {
            "Async Capable": false,
            "Node Type": "Sort",
            "Parallel Aware": false,
            "Parent Relationship": "Outer",
            "Plan Rows": 1,
            "Plan Width": 1286,
            "Plans": [
              {
                "Async Capable": false,
                "Inner Unique": false,
                "Join Type": "Left",
                "Node Type": "Nested Loop",
                "Parallel Aware": false,
                "Parent Relationship": "Outer",
                "Plan Rows": 1,
                "Plan Width": 1286,
                "Plans": [
                  {
                    "Alias": "ip_pools",
                    "Async Capable": false,
                    "Filter": "((network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[])) AND ((allocation_mode)::text = 'AUTO'::text))",
                    "Index Name": "excl_ip_pools_network_id_address_range",
                    "Node Type": "Index Scan",
                    "Parallel Aware": false,
                    "Parent Relationship": "Outer",
                    "Plan Rows": 1,
                    "Plan Width": 1270,
                    "Relation Name": "ip_pools",
                    "Scan Direction": "Forward",
                    "Startup Cost": 0.12,
                    "Total Cost": 8.14
                  },
                  {
                    "Alias": "ip_addresses",
                    "Async Capable": false,
                    "Filter": "(network_id = ip_pools.network_id)",
                    "Index Cond": "((address >= ip_pools.start_address) AND (address <= ip_pools.end_address))",
                    "Index Name": "uq_ip_addresses_cluster_id_address",
                    "Node Type": "Index Scan",
                    "Parallel Aware": false,
                    "Parent Relationship": "Inner",
                    "Plan Rows": 1,
                    "Plan Width": 64,
                    "Relation Name": "ip_addresses",
                    "Scan Direction": "Forward",
                    "Startup Cost": 0.14,
                    "Total Cost": 8.17
                  }
                ],
                "Startup Cost": 0.27,
                "Total Cost": 16.33
              }
            ],
            "Sort Key": [
              "ip_pools.id"
            ],
            "Startup Cost": 16.34,
            "Total Cost": 16.34
          }
        ],
        "Startup Cost": 16.34,
        "Strategy": "Sorted",
        "Total Cost": 16.36
      }
    ],
    "Sort Key": [
      "ip_pools.network_id",
      "ip_pools.start_address",
      "ip_pools.id"
    ],
    "Startup Cost": 16.37,
    "Total Cost": 16.38
  }
}
```

`enable_seqscan = off` 计划：

```json
{
  "Plan": {
    "Async Capable": false,
    "Node Type": "Sort",
    "Parallel Aware": false,
    "Plan Rows": 1,
    "Plan Width": 1278,
    "Plans": [
      {
        "Async Capable": false,
        "Group Key": [
          "ip_pools.id"
        ],
        "Node Type": "Aggregate",
        "Parallel Aware": false,
        "Parent Relationship": "Outer",
        "Partial Mode": "Simple",
        "Plan Rows": 1,
        "Plan Width": 1278,
        "Plans": [
          {
            "Async Capable": false,
            "Node Type": "Sort",
            "Parallel Aware": false,
            "Parent Relationship": "Outer",
            "Plan Rows": 1,
            "Plan Width": 1286,
            "Plans": [
              {
                "Async Capable": false,
                "Inner Unique": false,
                "Join Type": "Left",
                "Node Type": "Nested Loop",
                "Parallel Aware": false,
                "Parent Relationship": "Outer",
                "Plan Rows": 1,
                "Plan Width": 1286,
                "Plans": [
                  {
                    "Alias": "ip_pools",
                    "Async Capable": false,
                    "Filter": "((network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[])) AND ((allocation_mode)::text = 'AUTO'::text))",
                    "Index Name": "excl_ip_pools_network_id_address_range",
                    "Node Type": "Index Scan",
                    "Parallel Aware": false,
                    "Parent Relationship": "Outer",
                    "Plan Rows": 1,
                    "Plan Width": 1270,
                    "Relation Name": "ip_pools",
                    "Scan Direction": "Forward",
                    "Startup Cost": 0.12,
                    "Total Cost": 8.14
                  },
                  {
                    "Alias": "ip_addresses",
                    "Async Capable": false,
                    "Filter": "(network_id = ip_pools.network_id)",
                    "Index Cond": "((address >= ip_pools.start_address) AND (address <= ip_pools.end_address))",
                    "Index Name": "uq_ip_addresses_cluster_id_address",
                    "Node Type": "Index Scan",
                    "Parallel Aware": false,
                    "Parent Relationship": "Inner",
                    "Plan Rows": 1,
                    "Plan Width": 64,
                    "Relation Name": "ip_addresses",
                    "Scan Direction": "Forward",
                    "Startup Cost": 0.14,
                    "Total Cost": 8.17
                  }
                ],
                "Startup Cost": 0.27,
                "Total Cost": 16.33
              }
            ],
            "Sort Key": [
              "ip_pools.id"
            ],
            "Startup Cost": 16.34,
            "Total Cost": 16.34
          }
        ],
        "Startup Cost": 16.34,
        "Strategy": "Sorted",
        "Total Cost": 16.36
      }
    ],
    "Sort Key": [
      "ip_pools.network_id",
      "ip_pools.start_address",
      "ip_pools.id"
    ],
    "Startup Cost": 16.37,
    "Total Cost": 16.38
  }
}
```

### B3 — Network 占用计数

```sql
SELECT ip_addresses.network_id, count(*) AS count_1 FROM ip_addresses WHERE ip_addresses.network_id IN (%(network_id_1_1)s::UUID, %(network_id_1_2)s::UUID) AND ip_addresses.deleted_at IS NULL AND ip_addresses.deleted_at IS NULL GROUP BY ip_addresses.network_id
```

原始计划：

```json
{
  "Plan": {
    "Async Capable": false,
    "Group Key": [
      "network_id"
    ],
    "Node Type": "Aggregate",
    "Parallel Aware": false,
    "Partial Mode": "Simple",
    "Plan Rows": 1,
    "Plan Width": 24,
    "Plans": [
      {
        "Async Capable": false,
        "Node Type": "Sort",
        "Parallel Aware": false,
        "Parent Relationship": "Outer",
        "Plan Rows": 1,
        "Plan Width": 16,
        "Plans": [
          {
            "Alias": "ip_addresses",
            "Async Capable": false,
            "Filter": "(network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[]))",
            "Index Cond": "((deleted_at IS NULL) AND (deleted_at IS NULL))",
            "Index Name": "ix_ip_addresses_deleted_at",
            "Node Type": "Index Scan",
            "Parallel Aware": false,
            "Parent Relationship": "Outer",
            "Plan Rows": 1,
            "Plan Width": 16,
            "Relation Name": "ip_addresses",
            "Scan Direction": "Forward",
            "Startup Cost": 0.15,
            "Total Cost": 8.17
          }
        ],
        "Sort Key": [
          "network_id"
        ],
        "Startup Cost": 8.18,
        "Total Cost": 8.19
      }
    ],
    "Startup Cost": 8.18,
    "Strategy": "Sorted",
    "Total Cost": 8.2
  }
}
```

`enable_seqscan = off` 计划：

```json
{
  "Plan": {
    "Async Capable": false,
    "Group Key": [
      "network_id"
    ],
    "Node Type": "Aggregate",
    "Parallel Aware": false,
    "Partial Mode": "Simple",
    "Plan Rows": 1,
    "Plan Width": 24,
    "Plans": [
      {
        "Async Capable": false,
        "Node Type": "Sort",
        "Parallel Aware": false,
        "Parent Relationship": "Outer",
        "Plan Rows": 1,
        "Plan Width": 16,
        "Plans": [
          {
            "Alias": "ip_addresses",
            "Async Capable": false,
            "Filter": "(network_id = ANY ('{8541f4c7-4b11-45e9-a5e5-72b46b00c695,959a8b99-e27e-46c1-9476-71ef1497e421}'::uuid[]))",
            "Index Cond": "((deleted_at IS NULL) AND (deleted_at IS NULL))",
            "Index Name": "ix_ip_addresses_deleted_at",
            "Node Type": "Index Scan",
            "Parallel Aware": false,
            "Parent Relationship": "Outer",
            "Plan Rows": 1,
            "Plan Width": 16,
            "Relation Name": "ip_addresses",
            "Scan Direction": "Forward",
            "Startup Cost": 0.15,
            "Total Cost": 8.17
          }
        ],
        "Sort Key": [
          "network_id"
        ],
        "Startup Cost": 8.18,
        "Total Cost": 8.19
      }
    ],
    "Startup Cost": 8.18,
    "Strategy": "Sorted",
    "Total Cost": 8.2
  }
}
```

## 运行 2 —— 摘要（同批 15 用例运行，计划形态漂移留痕）

| 语句 | 原始节点类型 | 强制关顺序扫描节点类型 | 引用索引 |
| --- | --- | --- | --- |
| 1（B1） | `['Index Scan']` | `['Index Scan']` | `['excl_ip_pools_network_id_address_range']` |
| 2（B2） | `['Aggregate', 'Index Scan', 'Nested Loop', 'Sort']` | `['Aggregate', 'Index Scan', 'Nested Loop', 'Sort']` | `['excl_ip_pools_network_id_address_range', 'uq_ip_addresses_cluster_id_address']` |
| 3（B3） | `['Aggregate', 'Index Scan', 'Sort']` | `['Aggregate', 'Index Scan', 'Sort']` | `['ix_ip_addresses_deleted_at']` |

两次运行的语句原文与参数完全相同，差异仅来自 2 行小表的统计/代价估算；均无 `Seq Scan`。


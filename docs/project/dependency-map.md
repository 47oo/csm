# CSM Feature Dependency Map

> Status: DRAFT（待用户确认）
> Source of Truth: `docs/project/project-plan.yaml`
> 依赖仅表示真正的实施依赖（B 无法在 A 未 DONE 时正确实现）。依赖为 DAG，无循环。
> Last updated: 2026-09-16（OPEN-004 / OPEN-001 / DEC-004 / OPEN-002 / DEC-005 已裁定；F002 → READY，F006 / F007 → BLOCKED）
>
> 依赖结构未因已完成 Feature 而变化；仅状态变化：F012 / F001 / F013 / F014 / F015 → DONE；
> F002 因 OPEN-004 关闭且 F001 DONE 而 READY；F006、F007 因产品问题关闭而解除 DRAFT，
> 但依赖未 DONE，故为 BLOCKED。
> 其余因依赖未 DONE（BLOCKED）或 Feature 级产品问题（DRAFT）尚未 READY。
> 注意：F009 仍为 BLOCKED，因为它同时依赖 F002，而 F002 尚未 DONE。

图例：`A --> B` 表示 **B depends_on A**（A 是 B 的前置）。

---

## 1. 全量依赖 DAG

```text
F012 项目基础框架与运行环境 (ENABLER, P0)
 ├──> F001 Cluster 登记与管理 (P0)
 │      └──> F002 BareMetal 登记与管理 (P0)
 │             ├──> F004 NetworkInterface 管理 (P1)
 │             │      └──> F005 IPAddress 管理 (P1)
 │             ├──> F006 VirtualMachine 登记与管理 (P1)
 │             │      └──> F007 Container 资源模型与登记 (P1)
 │             └──> F009 Cluster 视角资源查询 (P0)
 ├──> F013 本地账号认证与会话 (ENABLER, P0)
 │      └──> F015 内网部署与运行环境 (ENABLER, P0)
 ├──> F014 逻辑删除与数据一致性治理 (ENABLER, P0)
 └──> F015 内网部署与运行环境 (ENABLER, P0)

F008 Service 资源管理与 Cluster 共享关联 (P1)  depends_on F001, F002, F006, F007

F010 资源详情与关联查询 (P1)  depends_on F001, F002, F004, F005, F006, F007, F008
F011 Excel 模板与批量导入 (P1)  depends_on F001, F002, F004, F005, F006, F007, F008
```

等价的边列表：

| Feature | depends_on |
|---|---|
| F001 | F012 |
| F002 | F001 |
| F004 | F002 |
| F005 | F004 |
| F006 | F002 |
| F007 | F006, F002 |
| F008 | F001, F002, F006, F007 |
| F009 | F001, F002 |
| F010 | F001, F002, F004, F005, F006, F007, F008 |
| F011 | F001, F002, F004, F005, F006, F007, F008 |
| F012 | — |
| F013 | F012 |
| F014 | F012 |
| F015 | F012, F013 |

F003 已删除（Rack / U 位从 V1 移除），不再出现在依赖图中。

无循环（拓扑排序存在，见第 4 节）。

> 说明：F008 的依赖已按 DEC-003 方案 C 更新。Service 必选绑定运行载体（BareMetal / VM / Container），
> 因此 F008 强依赖 F002（BareMetal）、F006（VirtualMachine）、F007（Container），另依赖 F001（Cluster 归属推导）。

---

## 2. 可并行执行的 Feature 分组

以下分组表示：在同一批次内，各 Feature 之间**没有互相依赖**，可以在其共同前置 DONE 后并行实施。
（实际并行仍须遵守 `docs/project/git-workflow.md`：并行前划定文件所有权。）

- **Batch 0（根）**：F012（ENABLER，已 DONE）。
- **Batch 1**：F001（Cluster，已 DONE）。F013（已 DONE）、F014（已 DONE）也可与资源线并行（均只依赖 F012）。
- **Batch 2**：
  - 资源线：F002（BareMetal）
  - 并行基础线：F015（部署，需 F013，已 DONE）
- **Batch 3**（F002 完成后，彼此独立）：
  - F004（NetworkInterface）
  - F006（VirtualMachine）
  - F009（Cluster 视角查询，另需 F001 DONE）
- **Batch 4**：
  - F005（IPAddress，依赖 F004）
  - F007（Container，依赖 F006/F002）
- **Batch 5**（服务线，需全部载体 Feature）：
  - F008（Service，依赖 F001/F002/F006/F007）
- **Batch 6**（收敛，必须最后）：
  - F010（资源详情与关联查询）
  - F011（Excel 批量导入）
  F010 与 F011 彼此无依赖，可并行，但都需全部资源 Feature（含 F008）DONE。

> F013、F014 与资源主线无相互依赖，可穿插在任意批次实施；是否并行由协调器按文件所有权决定。

---

## 3. 关键路径（Critical Path）

```text
F012 --> F001 --> F002 --> F006 --> F007 --> F008 --> F010
                  │
                  └--> F004 --> F005
```

其中由交付收敛决定的**最长关键链**为：

```text
F012 (框架)
  --> F001 (Cluster)
  --> F002 (BareMetal)
  --> F006 (VirtualMachine)
  --> F007 (Container)
  --> F008 (Service)
  --> F010 (资源详情与关联查询)
```

说明：F008 因新增对 F006/F007 的强依赖而进入关键路径；F010 依赖全部资源 Feature，是关键路径终点。
若以 F011 为终点：

```text
F012 --> F001 --> F002 --> F006 --> F007 --> F008 --> F011
```

结论：**关键路径经过 F012 → F001 → F002 → F006 → F007 → F008，再收敛到 F010 / F011**；
F012、F001、F002 是全局瓶颈。F012 的架构阻塞决策（DEC-009/010/011，以及 DEC-014）已全部 RESOLVED
（ADR-0001 ~ ADR-0003 `ACCEPTED`），F012 已 READY；后续瓶颈来自依赖链本身。

---

## 4. 拓扑序（建议实施顺序）

```text
1.  F012
2.  F001, F013, F014
3.  F002, F015
4.  F004, F006, F009
5.  F005, F007
6.  F008
7.  F010, F011
```

该顺序与 `docs/project/milestones.md` 的 M1 ~ M5 对应。

---

## 5. 依赖与优先级的关系

优先级（P0/P1/P2）不代表执行顺序。例如 F009（P0）依赖 F001、F002（P0），必须先完成前置；
F007（P1）在 F006 完成后即可执行，不必等待所有 P0 完成。执行顺序以本依赖图的拓扑序为准。
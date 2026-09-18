# CSM Feature Dependency Map

> Status: 由 `docs/project/project-plan.yaml` **生成**（人类可读视图，不构成机器状态的唯一来源）
> Source of Truth: `docs/project/project-plan.yaml`
> Generated: 2026-09-18（**本文件为重建版**——此前正文自 M1 时期起严重漂移，经用户决定按计划重新生成）
> 生成依据：`project.status = IN_PROGRESS`；计数 `{'READY': 0, 'IN_PROGRESS': 0, 'BLOCKED': 1, 'DRAFT': 0, 'DONE': 15, 'CANCELLED': 1}`

**重建说明**：本文件由 `project-plan.yaml` 重新生成，取代此前陈旧的正文（旧版仍写「Feature 总数 14 / DONE 10 / F007 READY / M4 进行中」等）。
历史结论（F011 取消、M5 的实际结局、各 Feature 的 merge SHA、各条 follow-up）均按计划原样保留，未因重建而丢失。

依赖仅表示**真正的实施依赖**（B 无法在 A 未 DONE 时正确实现）。依赖为 DAG，无循环。
图例：`A --> B` 表示 **B depends_on A**（A 是 B 的前置）。

## 依赖表（权威：计划 `features[].depends_on`）

| Feature | 状态 | depends_on | 层 |
|---|---|---|---|
| F012 项目基础框架与运行环境 | DONE | — | database, backend, frontend |
| F013 本地账号认证与会话 | DONE | F012 | database, backend, frontend |
| F014 逻辑删除与数据一致性治理 | DONE | F012 | backend, frontend |
| F015 内网部署与运行环境 | DONE | F012, F013 | backend, deployment |
| F001 Cluster 登记与管理 | DONE | F012 | backend, frontend |
| F002 BareMetal 登记与管理 | DONE | F001 | database, backend, frontend |
| F004 NetworkInterface 管理 | DONE | F002 | database, backend, frontend |
| F005 IPAddress 管理 | DONE | F004 | database, backend, frontend |
| F006 VirtualMachine 登记与管理 | DONE | F002 | database, backend, frontend |
| F007 Container 资源模型与登记 | DONE | F006, F002 | database, backend, frontend |
| F008 Service 资源管理与 Cluster 共享关联 | DONE | F001, F002, F006, F007 | database, backend, frontend |
| F009 Cluster 视角资源查询 | DONE | F001, F002 | backend |
| F010 资源详情与关联查询 | DONE | F001, F002, F004, F005, F006, F007, F008 | backend, frontend |
| F011 Excel 模板与批量导入 | CANCELLED | F001, F002, F004, F005, F006, F007, F008 | — |
| F016 Cluster 登记与改名 UI | DONE | F001, F013, F014 | frontend |
| F017 应用外壳侧边栏导航 | DONE | F012, F013, F001, F002, F004, F005, F006, F007, F008, F010 | frontend |
| F018 集群内资源关键字搜索 | BLOCKED | F001, F002, F004, F005, F006, F007, F008 | backend, frontend |

## 全量依赖 DAG

```text
F012 项目基础框架与运行环境 (P0, DONE)
   └──> F013 本地账号认证与会话 (P0, DONE)
   └──> F014 逻辑删除与数据一致性治理 (P0, DONE)
   └──> F015 内网部署与运行环境 (P0, DONE)
   └──> F001 Cluster 登记与管理 (P0, DONE)
   └──> F017 应用外壳侧边栏导航 (P2, DONE)
```

## 拓扑序（实施顺序参考）

```text
 1. F012  DONE
 2. F013  DONE
 3. F014  DONE
 4. F015  DONE
 5. F001  DONE
 6. F002  DONE
 7. F004  DONE
 8. F005  DONE
 9. F006  DONE
10. F007  DONE
11. F008  DONE
12. F009  DONE
13. F010  DONE
14. F011  CANCELLED
15. F016  DONE
16. F017  DONE
17. F018  BLOCKED
```

## 说明

- `F018` 是当前唯一未处置 Feature，状态 `BLOCKED`——**产品行为未决**（NQ-A 与 PROPOSED-1），**不是**依赖、架构或环境阻塞；其 `depends_on` 的 F001 / F002 / F004–F008 全部已 DONE。
- `F017`（侧边栏）与 `F018`（搜索）**无依赖边**；两者都要改 `frontend/src/App.vue`，故需**串行**——`F017` 已完成并 merge，该文件所有权冲突已解除。
- `F011` 为 `CANCELLED`（用户 2026-09-18 决定），不在实施顺序中。
- 优先级（P0 / P1 / P2）不代表执行顺序；执行顺序以上方拓扑序为准。

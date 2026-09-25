# CSM V2 Backlog（派生视图）

> 本文件由 `docs/project/project-plan.yaml` 派生，不独立保存事实。若与计划冲突，以计划为准。
> 计划状态：**IN_PROGRESS — revision 9（2026-09-25，已批准）**；F013 已启动实施（分支 `feature/F013-user-role-management`）；产品需求整体仍为 DRAFT，实施门禁独立适用。全部 Feature 为 P0。

## 概览

| 计数 | 值 |
| --- | --- |
| Feature 总数 | 13 |
| READY | 0 |
| BLOCKED | 12 |
| DRAFT | 0 |
| IN_PROGRESS | 1 |
| IN_REVIEW | 0 |
| DONE | 0 |

F013 当前为 `IN_PROGRESS`（已启动，分支 `feature/F013-user-role-management`），其余 Feature 仍为 `BLOCKED`：`depends_on` 尚未 DONE，或仍存在 OPEN 决策。计划批准与启动均不等于需求最终签核或 Feature DONE；门禁满足后由协调器核对证据并重算状态。
需求覆盖：requirements-v2.md §10 全部 81 条验收场景（BQ-M–BQ-W），`requirement_coverage.gaps` 为空；每条场景均有 `closure_owner`（闭环归属）。

## Backlog

> “主要验收（闭环）”列出本 Feature DONE 时闭环归属它的 §10 场景；联验与拆分部分见计划中对应 `acceptance_note` 与 `requirement_coverage.scenarios.*.parts`。

| ID | 能力 | Epic | 优先级 | 状态 | 依赖 | 阻塞决策 | 需求来源 | 主要验收（闭环） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F013 | 用户与角色管理 | E8 | P0 | IN_PROGRESS | — | — | §2.1（认证源＝平台自建；统一三角色）；§3.1（用户与角色管理模块）；§4.9（用户与角色管理）；§9.1（登录/会话/口令与用户管理审计） | 72、73、74、75、76、77、78、79、80、81 |
| F001 | 集群登记、身份、真实删除保护与集群本体权限审计 | E1 | P0 | BLOCKED | F013 | D-CODE-FORMAT、D-DELETE-CONFIRMATION、D-DELETE-DEPENDENCIES | §4.1.1、§4.1.6–4.1.9；§6.1（集群编号/名称/用途/选择记忆）；§4.4（集群真实删除与资源历史保留）；§2.1、§9.1（集群本体三角色服务端鉴权与操作审计） | 71 |
| F002 | 计算资源登记、无 IP 网卡与一次原子提交基础 | E2 | P0 | BLOCKED | F001、F005 | D-STATUS-SOURCE、D-IP-SEMANTICS、D-DELETE-DEPENDENCIES、D-DELETE-CONFIRMATION | §2.2（已登记资源补充/新增网卡路径）；§4.1.2–4.1.5、§4.1.8、§4.1.10；§4.2.4、§4.2.5；§4.4（计算资源真实删除与网卡/IP 子项先删）；§4.5（公共信息与网卡的整单原子）；§6.4（表单结构、网卡卡片与网段选择）；§7.2、§7.3、§7.4（公共/网卡部分）；§2.1、§9.1（本对象服务端三角色鉴权与操作审计） | 28、29、34、47、50 |
| F003 | 计算资源统一列表、详情与服务端分页 | E2 | P0 | BLOCKED | F002、F006 | D-STATUS-SOURCE | §4.3（状态展示）；§6.2（列表公共列、类型切换、筛选、分页、当前集群作用域与 IP 搜索）；§6.3（公共详情）；§9.2、§9.4 | 8、32 |
| F004 | 类型详情、列表/详情类型摘要与宿主关系 | E3 | P0 | BLOCKED | F002、F003、F008 | D-Q3、D-RESOURCE-REASSIGN、D-DELETE-DEPENDENCIES | §1.3（类型详情抽象）；§4.7；§4.4（删宿主前逐项真删 VM、不自动改挂）；§6.2（CPU/vCPU/内存摘要）；§6.3（类型详情）；§7.5 | 1、2、13、14、15、33、35、36 |
| F005 | 网段、保留地址与网段历史写入 | E4 | P0 | BLOCKED | F001 | D-DELETE-DEPENDENCIES、D-DELETE-CONFIRMATION | §4.6；§5（网段约束、保留地址与网关、删除前置）；§6.5；§4.4（网段真实删除与历史写入）；§2.1、§9.1（本对象服务端三角色鉴权与操作审计） | 10、12、53 |
| F006 | IPv4 分配与同一表单 IP 集成 | E4 | P0 | BLOCKED | F002、F005 | D-IP-SEMANTICS、D-DELETE-DEPENDENCIES、D-DELETE-CONFIRMATION | §4.2.1–4.2.3、§4.2.6–4.2.11；§4.4（IP 真实删除释放与历史）；§4.5（含 IP 的整单原子与并发编辑冲突）；§5（IPv4 分配规则）；§6.4（IP 分配部分）；§7.1、§7.3、§7.4（IP 部分）；§9.3；§2.1、§9.1（本对象服务端三角色鉴权与操作审计） | 3、4、9、11、19、20、21、24、25、26、27、30、31、43、44、45、52、60、62、65 |
| F007 | 服务、部署实例、访问入口与服务历史 | E5 | P0 | BLOCKED | F001、F002、F004、F012 | D-BQ-E、D-SERVICE-DETAILS、D-RESOURCE-REASSIGN、D-DELETE-DEPENDENCIES、D-DELETE-CONFIRMATION | §4.8；§6.6；§4.4（服务/入口真实删除与历史写入）；§2.1、§9.1（本对象服务端三角色鉴权与操作审计）；§8（服务/服务实例适配） | 5、6、16、17、18、42、46、49、51、54、58、59、63、67、68、69、70 |
| F008 | 统一模糊搜索与下拉交互 | E6 | P0 | BLOCKED | F002、F003 | — | §8；§7.5（搜索下拉部分） | 41 |
| F009 | 跨对象权限审计一致性复核与集群切换验收 | E7 | P0 | BLOCKED | F013、F001、F002、F004、F005、F006、F007 | — | §2.1、§9.1（跨对象一致性复核侧） | 40 |
| F010 | 集群聚合概览、查询作用域与全局 IP 查询 | E1 | P0 | BLOCKED | F002、F003、F004、F005、F007、F008 | — | §6.1（聚合计数与口径）；§6.2（作用域展示与全局 IP 查询入口）；§0.4（BQ-D） | 55、56、66 |
| F011 | 非功能、可用性基线与全平台权限复核 | E7 | P0 | BLOCKED | F013、F001、F002、F003、F004、F005、F006、F007、F008、F009、F010、F012 | — | §9.2、§9.3、§9.4；§8（全量覆盖复核）；§2.1、§9.1（全平台终局复核） | 7、22、23、37、38、39、57 |
| F012 | 资源历史保留与管理员查询 | E7 | P0 | BLOCKED | F013、F001、F002、F005、F006 | — | §4.4（资源历史保留与查询）；§2.1、§9.1（仅管理员可查） | 48、61、64 |

## 阻塞决策索引

| 决策 ID | 类型 | 状态 | 问题 | 受影响 Feature |
| --- | --- | --- | --- | --- |
| D-ARCH-STACK | ARCHITECTURE | RESOLVED | 后端/前端技术栈、语言、框架与运行时版本。 | ALL |
| D-ARCH-DB | ARCHITECTURE | RESOLVED | 数据库选型、约束与 Migration 策略；展示口径与存储口径一致性策略。 | ALL |
| D-ARCH-API | ARCHITECTURE | RESOLVED | API 风格、契约规范与错误语义约定（含整单原子提交与并发冲突的表达）。 | ALL |
| D-ARCH-DEPLOY | ARCHITECTURE | RESOLVED | 部署架构、内网访问与环境拓扑。 | ALL |
| D-Q3 | PRODUCT | OPEN | 裸金属 CPU/内存/GPU/SN、VM vCPU/内存等专有属性的必填范围、表示含义与单位。 | F004 |
| D-STATUS-SOURCE | PRODUCT | OPEN | 计算资源“状态来源”的具体语义——记录操作者还是来源系统；状态更新时间与一般资源更新时间的区分。 | F002、F003 |
| D-NAME-COMPARISON | PRODUCT | RESOLVED | 资源名、接口名、网段名、服务编号、用户名的比较口径（大小写/首尾空格）；集群名称已允许字符的具体范围与长度。 | F001、F002、F005、F007、F013 |
| D-CODE-FORMAT | PRODUCT | OPEN | 集群 code 是否另设字符集/长度约束（本次仅确认去首尾空格+统一大写的判重与永不复用口径）。 | F001 |
| D-IP-SEMANTICS | PRODUCT | OPEN | 网卡/IP 单独真实删除后的历史表达（无业务恢复入口）。 | F002、F006 |
| D-BQ-E | PRODUCT | OPEN | “服务类型”“节点角色”是否为受控枚举及其取值集。 | F007 |
| D-SERVICE-DETAILS | PRODUCT | OPEN | 入口字段与监听端口必填/具体校验（零关联、最后一条关联解除与入口逐条真实删除已裁定）。 | F007 |
| D-DELETE-DEPENDENCIES | PRODUCT | OPEN | 其它受管对象依赖的具体合法处理（逐项先删、网段清地址/网关、服务入口/关联、宿主删 VM、资源删实例均已裁定）。 | F001、F002、F004、F005、F006、F007 |
| D-RESOURCE-REASSIGN | PRODUCT | OPEN | 日常单独手工更换 VM 宿主/实例目标是否属 P0 及约束（删除上级不自动改挂已裁定）。 | F004、F007 |
| D-RESOURCE-HISTORY | PRODUCT | RESOLVED | 资源历史与审计的载体边界；审计保留周期。 | F001、F002、F005、F006、F007、F012、F013 |
| D-DELETE-CONFIRMATION | PRODUCT | OPEN | 真实删除是否需额外确认及交互方式。 | F001、F002、F005、F006、F007 |
| D-BQ-F | PRODUCT | RESOLVED | 认证源、审计保留周期、备份与恢复演练、正式延迟目标（随 BQ-V 关闭）。 | F001、F002、F005、F006、F007、F009、F011、F012 |
| D-Q5 | PRODUCT | RESOLVED | 同集群网段重叠仅提示风险还是禁止写入。 | F005、F006 |
| D-SEGMENT-RETENTION | PRODUCT | RESOLVED | 已真实删除网段的保留地址/网关是否继续排除分配；重叠网段可自动分配数量口径。 | F005、F006 |

> D-ARCH-* 为项目级门禁（affects=ALL），不逐 Feature 重复；D-ARCH-*、D-BQ-F、D-NAME-COMPARISON 与 D-RESOURCE-HISTORY 已 RESOLVED，但架构/契约文档尚未产出。

> 场景 closure 分布（revision 9，与 revision 8 相同）：M1 44 条、M2 9 条、M3 21 条、M4 7 条，合计 81 条；无 closure_owner 早于其参与 Feature。明细见计划 `requirement_coverage.closure_audit`。

> P1/P2 未登记：requirements-v2.md 未确认任何非 P0 范围，§3.2 的排除项（导入导出、批量更新、告警等）不属于已确认 P1/P2 需求。

> BQ-M–BQ-V（2026-09-24 至 2026-09-25）为已裁定需求（§11.1），非阻塞决策；本次核对未新增 `decisions_required` 以外的业务规则。
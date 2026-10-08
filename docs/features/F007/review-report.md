# F007 Interface 接口管理 — REVIEW 报告

- **Task**：F007（FEATURE，P0，M3，deps [F004]）— Reviewer 独立复核
- **Status**：`APPROVED WITH FOLLOW-UP`
- **日期**：2026-10-09
- **角色**：Reviewer（只读；协调器持久化本报告）

## Basis
- requirements-v3.md revision 3（§4.1、§10、§13、§18、§21–§23、§27、§31 T12/T20/T23/T24/T25/T37/T39/T40/T41）
- docs/api/F007.md v1（READY，Architect）；docs/database/f007-interface.md v1（DB-D64–D79）；d01-conventions.md v6（§3/§5.2/§5.6）
- docs/features/F007/{product,architecture,implementation,test-report(TD-2/TE-1)}
- 批准核验：plan_revision 4 覆盖 F007；pending_changes 空；execution.authorization 覆盖 F007；validate_project_state.py VALID。

## Scope Reviewed
| 项 | 值 |
| --- | --- |
| Branch | feature/F007-interface-management |
| start_commit | e11fb74476d159e8905ca11fc158df2044303c22（=v3） |
| HEAD（候选） | f3c8ef560fbb4f61ae99ab250b03c9ad2acafd6b（实现提交 b1c1949） |
| merge-base | e11fb74 |
| 范围 | e11fb74..f3c8ef5，8 提交；backend 13 文件 + frontend 7 文件 |
| 完整性 | 工作区 clean；无暂存/未跟踪交付物 |

## 适用层结论
- 产品与领域：符合 A1–A19；未扩张范围；名称区分大小写/保留/禁内部空白/同 Resource 未删唯一/软删可复用与 §4.1 一致。
- 架构与契约：与 F007 v1 一致——7 端点、字段契约、错误码、权限、分页排序过滤、软删可见性、Activity、审计白名单、校验顺序、并发；D01 v6 §5.6；DR-72–DR-88。
- 数据与 Migration：迁移 0007 与 DB v1 §2 逐项一致；单一 head、down_revision=0006、无回填、downgrade 逆序对称；部分唯一 (resource_id,name) WHERE deleted_at IS NULL；双 FK RESTRICT；双触发器；索引集合正确、无 GIN/pg_trgm/MAC 唯一。
- 功能与可维护性：PATCH exclude_unset、显式 null、不可变 resource、乐观锁、恢复重检顺序（name 复用优先）均正确；无 500 泄漏/静默忽略/过度抽象。
- 测试充分性：真实 PG 后端、迁移、约束/触发器/部分唯一/FK raw、DR-85 双会话并发、前端机制级用例齐备。
- 安全与范围：无未授权端点；改动聚焦；metadata 归 Interface 自有裁定与 §10 CONFIRMED 一致（覆盖 product I-5 PROPOSED），属 Architect 普通设计权限。

## Verification（独立执行）
| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | pytest F007 两文件 -q（真实 PG） | 34 passed |
| 2 | pytest tests -q | 217 passed, 1 skipped（skip 环境性） |
| 3 | npm run typecheck | 0 错误 |
| 4 | npm run build | 通过，53 modules |
| 5 | npm run smoke:client | 86 passed, 0 failed |
| 6 | validate_project_state.py | PROJECT STATE VALID |

## Findings

### F007-REV-01 | LOW | 数据完整性/并发 | `backend/app/services/interface.py::restore_interface`
- 证据：restore 重检所属 Resource 未软删，但未对 resources 行加锁；而 Resource 软删（引用检查前 FOR UPDATE）与 Interface 创建（_lock_resource）均对同一行加锁。
- 期望/实际：期望「未删 Interface 恒属未软删 Resource」；实际 restore 与 Resource 软删并发可各自基于 READ COMMITTED 快照提交，留下「已软删 Resource + 未删 Interface」。
- 影响：窄并发窗口破坏归属不变量。DB 设计 §7 已显式声明该类「Resource 归属在软删并发下即时一致性」为不保证，且 F004–F006 restore 同型，属已批准设计边界。**必须修复：否**。Owner：Backend/Architect。

### F007-REV-02 | NOTE | API/契约顺序 | `api/v1/interfaces.py::delete_interface`
- version: int = Query(ge=1) 先于 _parse_uuid；id 非 UUID 且 version 非法时返回 422 而非 Contract §6.5 的 404。仅双重非法请求次序差异，无后果。**必须修复：否**。

### F007-REV-03 | NOTE | 契约/实现一致性 | restore_interface
- Contract §6.6 列 parent 重检含「无环」，实现仅查 parent 存在/同 Resource/未软删；因触发器对任意 INSERT/UPDATE 阻止成环，该分支不可达。文档措辞差异，非功能缺陷。**必须修复：否**。

### F007-REV-04 | NOTE | 测试覆盖 | B51 反向竞态
- 覆盖「Resource 删除持锁→Interface 创建阻塞→422」方向；反向由行锁序 + 端到端引用检查间接覆盖；Tester 已自报 F007-TE-1-03。覆盖充分。**必须修复：否**。

### F007-REV-05 | NOTE | 文档一致性 | test-report §5 vs InterfacesPanel
- Test Report 将 Resource Detail Interfaces 展示区域归 F013；实现已在 ResourceDetailPage 挂载 InterfacesPanel（仅 Interface 字段 + CRUD，不含 IP/Network 聚合列），对应 A19 数据侧与 architecture §7，未侵入 F013。需协调器/F013 交接澄清文案。**必须修复：否**。

## 旧缺陷复核（TE-1）
- F007-TE-1-01（Cc/Cf 非 ASCII 仅应用层、DB ASCII backstop）：确认，与 D01 v6 §5.6/DB-D65 一致，接受。
- F007-TE-1-02（Nginx 无法 VIEWER/EDITOR 真实登录）：确认一期无用户管理端点，服务端强制已由 ASGI + 真实 PG 覆盖，接受。
- F007-TE-1-03（B51 方向性）：确认，见 REV-04。
- TE-1 无 BLOCKER/HIGH/MEDIUM，独立复现一致。

## Follow-ups
1. restore 路径复用 Resource 行 FOR UPDATE（或经 dependency checker 串行化）并补 restore × Resource 软删并发用例（F007-REV-01，Backend/Architect）。
2. 协调器澄清 test-report §5 与 InterfacesPanel 的 F013 边界文案（F007-REV-05）。
3. 如需严格契约顺序，评估 DELETE 的 id/version 校验顺序（F007-REV-02）。

## 未审查项
- Compose/Nginx 全链路 curl（TE 命令 10）未由 Reviewer 重跑；前端真实浏览器 DOM 未评审（非必要判据，同 F001–F006）。
- 跨 Feature：A16 interface←IPAddress 归 F010；A19 聚合展示/列表搜索/Dashboard 归 F013；导入口径复用归 F014；完整 Audit 查询页归 F015；跨 Feature 回归与 §32 上线验收归 F016。不声明上述条款完整通过。
- 批准仅对候选 HEAD f3c8ef5 与 Base e11fb74 有效；Merge/DONE 由协调器按 Git Workflow 判定。
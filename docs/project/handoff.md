# Agent 交接规范

所有角色先读取 `AGENTS.md`，只加载当前任务、其权威来源及明确依赖。首次项目规划做全项目盘点；其余任务不要求遍历所有目录。缺失文档按 `AGENTS.md` §1.1 处理。

V3 一期产品来源为 `docs/product/requirements-v3.md`，领域索引为 `docs/product/domain-model.md`。Basis 引用具体条款和 revision；Result 区分 CONFIRMED / PROPOSED / OPEN。需求 §35 的问题按本任务影响列入 Issues，不将全局未决项全部当作当前阻塞，也不把建议默认为已批准。声明“READY”前须核对本范围的阻塞问题已关闭。

## 公共格式

每次交接只输出一份报告，包含：

* Task：Feature / 任务 ID、角色和工作范围。
* Status：使用角色定义的结果；未知值不能通过 Gate。
* Basis：已确认需求、已批准决策、Contract、约束的路径及版本或提交依据。
  涉及批准或复用时附批准者、对象版本、覆盖范围及确认来源，按 `docs/project/change-control.md` 核验；不能仅引用 READY 标签。
* Result：本次结论、修改文件、产物链接；假设和建议明确标注。
* Verification：实际执行的命令、结果、验收标准映射或角色适用的文档检查；未验证项及原因。
* Issues / Next：未解决问题、责任角色、后续关注事项；没有写 None。
* Git 声明：按 `AGENTS.md` §9.1 放在末尾。

产品、API、Schema 正文只保存到各自权威文档。报告引用正文，不复制一套详细规则；单个角色的附加字段见其 Agent 定义。

只读角色返回内容与建议保存路径，由协调器持久化。实现、测试角色只写职责内文件；共享文档由协调器维护。Project Manager 可写计划的规划字段，派生视图由脚本生成；不能提交、批准或启动执行。

变更评估交接另列：基线与提案版本、受影响 Feature/文件、可复用与已失效成果、需暂停的工作和下一责任角色。评估报告不授予实现权限。普通设计的专业签核与用户批准的区别见 `change-control.md`。

每个 Feature 各阶段可以使用同一份阶段报告更新结果，保留所依据的版本及必要历史证据，不为每轮修复重复创建一套文档。Test Report 即测试交接，不另建 Test Handoff。

Test Report 分开记录 TEST_DESIGN 与 TEST 的版本、结论和证据；前者不填充执行 PASS。Plan 的 evidence 按阶段引用报告路径，可引用同一文件的不同锚点。Architect 定稿记录其核对的 Database / Test Design 版本。角色报告或进程正常退出不自动推进 Gate，由协调器核验后写状态。

## 缺陷格式与分级

Test / Review 的每个问题包含：ID、Severity、Layer、Location、证据或复现步骤、期望与实际、影响、Owner、是否必须修复。相同根因沿用 ID。

| Severity | 含义 |
| --- | --- |
| BLOCKER | 核心目标无法实现、重大安全或数据丢失风险，禁止合并 |
| HIGH | 重要正确性问题，必须修复 |
| MEDIUM | 实际缺陷或显著设计问题，明确是否阻塞及理由 |
| LOW | 可后续处理的小问题 |
| NOTE | 非缺陷观察或建议 |

产品歧义交 Product Manager / 用户；技术方案交 Architect；Schema 设计交 Database；实现缺陷交 Backend / Frontend；测试基础设施交协调器。业务和架构裁定不能当作实现修复自动通过。

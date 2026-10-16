# F020 二次确认统一为模态对话框 — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1
- **上游依据**：`docs/product/requirements-v3.md` **revision 7** §28（含 §35.1 revision 7 确认记录）、§21、§22、§23、§31（T59–T63）；`docs/project/project-plan.yaml` revision 8（F020）；用户 2026-10-15 对范围 S1/S2 的裁定「按推荐执行」（A2 含释放 IP、B2 含恢复）。
- **复用说明**：复用 product-manager 2026-10-15 的 F020 需求澄清报告（原结论 `NOT READY FOR ARCHITECT`，阻塞项 S1/S2）。协调器核验：① 确认证据覆盖范围与验收（§28 + T59–T63）；② Architect 轻量评估判定 database/backend/contract 均无变更；③ S1/S2 已 CONFIRMED。故产品阶段判为复用完成，不重复调用角色。

---

## 1. 目标与范围

将前端所有破坏性操作的**内联二次确认**（`WarningState` + `div.inline-confirm`，显示在操作区下方、易被忽略）统一改为**模态对话框**呈现。共 9 个文件 11 处：

| 文件 | 操作 |
| --- | --- |
| `NetworksPage.tsx` | Network 删除 + 恢复 |
| `IpPoolsPage.tsx` | IP Pool 删除 + 恢复 |
| `ResourceDetailPage.tsx` | Resource 删除 + 恢复 |
| `IpAddressesPage.tsx` | IP 释放（软删）+ 恢复 |
| `ServicesPage.tsx` | Service 删除 + 恢复 |
| `ClusterDetailPage.tsx` | Cluster 删除 + 恢复 |
| `DeletedObjectsPanel.tsx` | 恢复 |
| `InterfacesPanel.tsx` | Interface 删除 + 恢复 |
| `ServiceEndpointsPanel.tsx` | Service Endpoint 删除 + 恢复 |

以既有「吊销 API Key」Modal（`ApiKeyManagementPanel.tsx`，`okText=确认吊销`、危险按钮）为一致样式基准。

## 2. 明确不做

- 不改删除/释放/恢复的语义、权限门禁、引用检查、Audit、错误码。
- 不新增或移除需要二次确认的操作集合。
- 不改后端 / API / Schema / 契约。
- 不改用户停用（`AccountManagementPanel` 无删除端点）。
- 不新引入 DOM 测试框架（除非协调器另行裁定）。

## 3. 验收标准（映射 T59–T63）

| # | 用户可观察行为 | 映射 |
| --- | --- | --- |
| AC1 | 点击范围内删除/释放/恢复后出现带遮罩模态对话框，含操作与对象标识；页面操作区不再渲染内联二次确认 | T59 |
| AC2 | 对话框含对象标识、软删说明与引用检查提示；确认文案与操作对应，删除/释放为危险样式 | T59/T60 |
| AC3 | 点击确认发出与改版前完全相同请求并执行原操作（成功提示、列表刷新、错误处理不变） | T62/T63 |
| AC4 | 取消或非提交态关闭（Esc/遮罩）不发起请求、不改变对象状态 | T59/T61 |
| AC5 | 请求进行中确认按钮加载且不可重复提交（含双击、遮罩、Esc） | T61 |
| AC6 | 删除被引用/版本冲突等错误按既有方式在对话框内呈现，对象未被删除 | T62 |
| AC7 | 权限门禁不变（VIEWER/EDITOR 无删除入口，ADMIN 可见）；释放 IP 与恢复满足同等行为 | T63/T60 |

> 验收标准未执行；本报告仅定义可验证行为。

## 4. 领域与数据影响

无新增实体/关系/状态/唯一性/生命周期；仅前端确认呈现形态变化，删除/释放/恢复请求与响应不变。

## 5. Blocking Questions

无。S1（含释放 IP）、S2（含恢复）已由用户 CONFIRMED；S3（复用既有 Modal 样式）为设计细节。

## 6. 受影响 Feature 与承接

F003/F004/F007/F008/F009/F010/F011/F012/F015 为复用对象（其页面被改造），不改写交付历史；本变更由新 Feature **F020** 承接。
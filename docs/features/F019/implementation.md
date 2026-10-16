# F019 接口侧选择并绑定 IP — IMPLEMENTATION 报告

- **版本**：v1（2026-10-15）
- **结论**：`FRONTEND COMPLETE`；Backend / Database / Contract `NOT_REQUIRED`

## Backend
`NOT_REQUIRED`：无服务端改动，复用既有 `GET /api/v1/ip-addresses`（F010 §6.1）与 `PATCH /api/v1/ip-addresses/{id}`（F010 §6.5）。

## Database
`NOT_REQUIRED`：无 Schema/索引/迁移；绑定仅置既有可空列 `ip_addresses.interface_id`。

## Frontend

### 改动文件
| 文件 | 类型 | 内容 |
| --- | --- | --- |
| `frontend/src/components/interfaceIpSelection.ts` | 新增（纯逻辑） | 选择集合增删/跨页保留（id 为键，快照 {id,address,version}）、候选查询参数构造（恰 cluster_id/bound=false/deleted=exclude/q/page/page_size/sort=address/order=asc）、已绑定查询参数构造、逐条绑定请求构造（每项恰 {version,interface}，address 数值升序）、串行提交（单项失败不中止、每项恰一次不重试）、部分成功汇总（全成功才 allSucceeded）、total 边界、权限/软删门控 |
| `frontend/src/components/InterfaceIpBindingPanel.tsx` | 新增（Modal） | 候选列表（服务端分页 + q 搜索 + 多选跨页保留）、逐条提交与逐项结果呈现、空/加载/错误态显式区分且错误可重试、`total>items` 提示；提交后清空选择并在有成功项时重取候选页（DR-345）；无手动输入/自动分配/解绑/转移入口 |
| `frontend/src/components/InterfacesPanel.tsx` | 修改 | 未删接口行新增「绑定 IP」（`canWrite && deleted_at===null` 门控）；每行「已绑定 IP」懒加载展示（按 interface_id 缓存、绑定成功后失效、`total>items` 提示、错误可重试）；既有创建/编辑/删除/恢复不变 |
| `frontend/src/components/ui/controls.tsx` | 修改（1 行） | checkbox 分支透传 `aria-label`（行内选择复选框可访问名；不改变事件契约） |
| `frontend/scripts/smoke-client.mjs` | 修改 | 追加 F019 机制级冒烟小节（IP-F1–F8） |

### 交互
1. Resource Detail → Interfaces 区域，每行新增「已绑定 IP」（READ 全角色）与「绑定 IP」（WRITE 且接口未软删）；接口创建成功回列表后即可就地绑定。
2. 「绑定 IP」Modal：候选口径说明；q 搜索 + 服务端分页（20/50/100）+ 多选；翻页/搜索不清空已选；`total>items` 显式提示。
3. 提交：逐条串行 PATCH `{version, interface}`；逐条结果表 + 汇总（全成功 / 部分成功 / 全失败）；原因经 `describeIpAddressActionError`；无自动重试；409 提示刷新重选。
4. 「已绑定 IP」按需加载并缓存；Loading/Empty/Error 显式区分。

### Contract 符合性（复用，未改契约）
- 候选/已绑定展示：F010 §6.1/§4（`cluster_id+bound=false+deleted=exclude+q+page+sort=address&order=asc`；`interface_id+deleted=exclude`）。
- 绑定：F010 §6.5（载荷恰 `{version, interface}`，exclude_unset）。
- 错误：F010 §1.2（409 VERSION_CONFLICT / 422 field=interface / 404 / 403 / 401）；权限 F010 §1.3；软删 §5；并发 §7；Audit §8。
- 无 Mock/Fixture：组件直连真实 API client；smoke 为受控 fetch 的机制级断言。

### 验证
| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | 通过 |
| `cd frontend && npm run build` | 通过 |
| `cd frontend && npm run smoke:client` | 293 passed, 0 failed（含 F019 IP-F1–F8；既有用例无回归） |

### 未验证项
- 真实浏览器 DOM 交互/布局/可访问性（F019-UNV-1/2）：无 DOM/E2E 工具 → NOT TESTED；替代证据为机制级冒烟 + typecheck + build + 静态核对。
- 真实后端/真 PG 集成（候选过滤、绑定持久化、并发 409、Audit、VIEWER 403）：归 TEST 阶段 F019-T01–T13。
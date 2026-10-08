# F007 Interface 接口管理 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE + FRONTEND COMPLETE（2026-10-09）
- **Contract**：docs/api/F007.md v1（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f007-interface.md v1（DB-D64–D79）
- **D01**：docs/architecture/d01-conventions.md v6（§3/§5.2/§5.6）
- **角色**：Backend（backend/**）；Frontend（frontend/**）；协调器持久化本记录。

## 1. 改动文件清单

### Backend
新增：
- `backend/alembic/versions/0007_interfaces.py` — 建表 interfaces（列/PK/双 FK RESTRICT/全部 CHECK）+ 部分唯一 uq_interfaces_resource_id_name（postgresql_where deleted_at IS NULL）+ ix_interfaces_resource_id/ix_interfaces_parent_interface_id + fn/trg_interfaces_parent_valid（拒自引用/跨 Resource/软删父/递归 CTE 断环）+ fn/trg_interfaces_immutable_resource；down_revision=0006；down 逆序；单一 head；无回填。
- `backend/app/models/interface.py`；`backend/app/schemas/interface.py`；`backend/app/services/interface.py`；`backend/app/api/v1/interfaces.py`。
- `backend/tests/integration/test_interface_constraints.py`（13）、`test_interfaces.py`（21）。

修改：`models/__init__.py`、`api/v1/router.py`、`services/audit.py`（白名单扩 interface）、`services/normalization.py`、`services/resource.py`（导入 interface service 确保检查器注册）；回归适配 `test_bare_metal_constraints.py`/`test_virtual_machine_constraints.py` head 0006→0007。

### Frontend
新增：`frontend/src/api/interfaces.ts`、`frontend/src/components/interfaceForm.ts`、`frontend/src/components/InterfaceForm.tsx`、`frontend/src/components/InterfacesPanel.tsx`。
修改：`frontend/src/pages/ResourceDetailPage.tsx`（挂载 InterfacesPanel）、`frontend/src/index.css`、`frontend/scripts/smoke-client.mjs`（+33 F007 用例）。

## 2. Contract/设计符合性

- 7 端点；校验顺序 POST body→resource→parent→name 唯一，PATCH 可见性→parent→version→name 唯一；删除/恢复顺序；恢复 name 复用优先于依赖失效。
- 错误：409 unique_conflict{field:"name"} / not_deleted / dependency_deleted{conflicts} / reference_exists{references}；VERSION_CONFLICT；422 点路径。
- name 区分大小写保留、trim/禁内部空白/1–64；类型 7 值默认 OTHER 不推断；mac ≤64 无正则无唯一；speed_mbps/mtu 正整数或 null；parent 同 Resource/非自身/无环；enabled 默认 true；metadata Interface 自有；resource 创建必填不可改。
- 引用检查：resource←未删 Interface（收窄 F004 DELETE /resources）；interface←未删子 Interface；interface←未删 IPAddress 预留空集（F010）。
- 审计四 action 同事务 object_type="interface"。**DR-85**：创建/变更 parent 同事务先对目标 Resource 行 FOR UPDATE，再递归祖先校验；DB 触发器仅兜底。

## 3. 验证证据（实现自测）

- Backend：真实 PG（f002test-db:5432/csm_test），`docker run ... pytest -ra` → **217 passed, 1 skipped, 1 warning**（FS007 新增 34：constraints 13 + interfaces 21）。skip=test_migrations.py 非 superuser 环境性，与 F001–F006 同因。
- Frontend：`npm run typecheck` PASS（0 错误）；`npm run build` PASS（53 modules）；`npm run smoke:client` → **86 passed, 0 failed**（F007 新增 33）。

## 4. 未验证项与风险（交 TEST / Review）

- 真实前后端集成（入口 Nginx 往返）与 Compose：待 TEST 阶段。
- 真实浏览器 DOM/E2E 未做（F007 非必要判据）。
- DR-85 parent 环并发双向、Resource 软删 vs Interface 创建反向竞态（B51）当前为单方向/间接覆盖，建议 TEST 补双向真并发。
- Cc/Cf 仅应用层保证，DB 为 ASCII backstop。
- F010 interface←IPAddress、F013 聚合展示、F015 Activity UI 不在本 Feature。

## 5. 提交

- Feature 分支提交见 MERGE 前检查点；本记录由协调器写入。
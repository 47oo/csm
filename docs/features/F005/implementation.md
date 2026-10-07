# F005 BareMetal 硬件与容量 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE + FRONTEND COMPLETE（2026-10-09）
- **Contract**：docs/api/F004.md v2（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f005-bare-metal.md v1（DB-D45–D52）
- **D01**：docs/architecture/d01-conventions.md v4（§3/§5.2/§5.4）
- **角色**：Backend（backend/**）；Frontend（frontend/**）；协调器持久化本记录。

## 1. 改动文件清单

### Backend
新增：
- `backend/alembic/versions/0005_bare_metal_details.py` — 建表/CHECK/FK CASCADE/类型匹配触发器/回填；down_revision="0004_resources"；downgrade 逆序。
- `backend/app/models/bare_metal_detail.py` — BareMetalDetail（物理列 metadata、ORM 属性 meta）。
- `backend/tests/integration/test_bare_metal.py`、`test_bare_metal_constraints.py`。

修改：
- `backend/app/models/resource.py`（1:1 关系）、`models/__init__.py`（注册）。
- `backend/app/schemas/resource.py`（HardwareIn/HardwarePatch/HardwareOut、build_hardware_out；ResourceOut/Create/Update 增 hardware）。
- `backend/app/services/resource.py`（validate_hardware、_hardware_snapshot、resource_snapshot 增 hardware、details_for、_attach_hardware；create/update 同事务 upsert）。
- `backend/app/services/audit.py`（快照白名单扩 hardware）。
- `backend/app/services/normalization.py`（validate_hardware_string，D01 §5.4）。
- `backend/app/api/v1/resources.py`（create/patch 传 hardware、_build_out 组装 BARE_METAL 对象/VM null）。
- `backend/tests/integration/test_resources.py`（白名单期望加 hardware）、`test_resource_constraints.py`（head 断言放宽为 >=0004，随单一 head 前移）。

### Frontend
新增：
- `frontend/src/components/hardware.ts`（纯逻辑：表单值解析校验、buildHardwareCreateInput、buildHardwarePatch）。

修改：
- `frontend/src/api/resources.ts`（Hardware/HardwareInput/HardwarePatch 类型；Resource.hardware；payload）。
- `frontend/src/components/ResourceForm.tsx`（BARE_METAL hardware 输入；VM 不渲染；422 点路径映射）。
- `frontend/src/pages/ResourceDetailPage.tsx`（HardwarePanel 仅 BARE_METAL；未知「—」非 0；gpu_count=0「明确无 GPU」；MiB/GiB；PATCH 子字段级）。
- `frontend/src/pages/ResourceCreatePage.tsx`（仅 BARE_METAL 构造 hardware，全空省略键）。
- `frontend/scripts/smoke-client.mjs`（+9 F005 用例）。

## 2. Contract/设计符合性

- 9 硬件字段 + hardware.metadata；严格整数（拒 "192"/true/1.5）；cpu_sockets/cpu_cores/memory_mb 1..2147483647；gpu_count 0..2147483647；字符串 trim→非空→禁 Cc/Cf→≤255 code point，空/纯空白 422 不转 null。
- BARE_METAL 创建恒有 detail 行（子字段省略/null→null、metadata {}）；VM 请求含 hardware（含显式 null）→422；响应 BARE_METAL=对象、VM=null；PATCH 子字段 exclude_unset（省略保持、显式 null 清空），hardware 整体 null/非对象/未知键→422。
- 无 SN 唯一、无归一化键；无独立端点；软删/恢复随 Resource；乐观锁沿用 resources.version；detail 无 version/时间戳。
- 审计 CREATE/UPDATE/DELETE/RESTORE 快照同事务扩 hardware（VM=null），失败回滚不留痕。
- 错误 fields[].field 使用点路径。

## 3. 验证证据（实现自测）

- Backend：Docker `postgres:16`（宿主 55432，库名含 test），`csm-backend-test` 镜像 `pytest tests -q` → **151 passed, 1 skipped**（基线 119 passed；新增 32 F005 测试）。唯一 skip 为 `test_migrations.py` V3b 非 superuser 扩展假设（环境性，与 F004 基线相同）。`alembic heads` → `0005_bare_metal_details (head)` 单一 head。
- Frontend：`npm run typecheck` PASS（0 错误）；`npm run build` PASS（47 modules）；`npm run smoke:client` → **52 passed, 0 failed**（F002 10 + F003 16 + F004 17 + F005 新增 9）。

## 4. 未验证项与风险（交 TEST / Review）

- 未通过完整 Compose/Nginx 栈验证写端点同源 CSRF（承 F004 TE-1）。
- 物理 FK CASCADE 与触发器为 raw SQL 机制级证据（API 无物理删除入口）。
- 审计回滚用例以 monkeypatch 注入失败，非真实进程崩溃注入。
- 字符串 Cc/Cf 仅应用层保证，DB 为 ASCII backstop（DB I-3 已知差异）。
- 真实浏览器 DOM/E2E 未做（按 TD-1 以构建+机制级为准）；待 Backend 就绪后做经 Nginx 的真实前后端集成。
- `hardware.metadata` 表单支持（Backend/Frontend 均实现）为实现补全，请 Review 确认。
- 列表级 hardware 过滤/排序不在 F005（I-1）。

## 5. 提交

- Feature 分支提交见 MERGE 前检查点；本记录由协调器写入。
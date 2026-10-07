# F006 虚拟机登记 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE + FRONTEND COMPLETE（2026-10-09）
- **Contract**：docs/api/F004.md v3（READY，Architect 2026-10-09）
- **Database 设计**：docs/database/f006-virtual-machine.md v1（DB-D53–D63）
- **D01**：docs/architecture/d01-conventions.md v5（§3/§5.2/§5.5）
- **角色**：Backend（backend/**）；Frontend（frontend/**）；协调器持久化本记录。

## 1. 改动文件清单

### Backend
新增：
- `backend/alembic/versions/0006_virtual_machine_details.py` — 回填守卫 DO 块 + 建表（resource_id PK/FK CASCADE；host_resource_id NOT NULL/FK RESTRICT + 索引；vcpu/memory_mb CHECK 1..2147483647；disk_gb CHECK 0..2147483647；hypervisor varchar(255) trim/非空 CHECK）+ 双触发器（type_match/host_valid，restrict_violation）；down 逆序；down_revision=0005。
- `backend/app/models/virtual_machine_detail.py` — 1:1 从属 ORM（无 metadata/deleted_at/version/时间戳）。
- `backend/tests/integration/test_virtual_machine.py`（21 例）、`test_virtual_machine_constraints.py`（11 例）。

修改：
- `backend/app/models/resource.py`、`models/__init__.py`（virtual_machine_detail 关系，显式 foreign_keys）。
- `backend/app/schemas/resource.py`（VirtualMachineIn/Patch/Out、build_virtual_machine_out；ResourceOut.virtual_machine）。
- `backend/app/services/resource.py`（validate_virtual_machine_values、validate_virtual_machine 宿主四条件 + SELECT ... FOR UPDATE（DR-71）、_attach_virtual_machine、resource_snapshot 增 virtual_machine、resource←未删 VM 引用检查器、VM restore Host 依赖检查器、delete_resource 引用检查前锁行、list_resources host_resource_id 过滤）。
- `backend/app/services/audit.py`（白名单扩 virtual_machine）。
- `backend/app/api/v1/resources.py`（POST/PATCH 传/组装 virtual_machine；列表 host_resource_id query）。
- `backend/app/services/normalization.py`（抽 validate_descriptive_string 共用）。
- 回归适配：test_resources.py（白名单+VM 提供 Host）、test_bare_metal.py（VM 占位改 Host）、test_bare_metal_constraints.py（head 0005→0006；回填用例预置 VM 改软删；终态 0006）。

### Frontend
新增：
- `frontend/src/components/virtualMachine.ts`（纯逻辑：表单解析/校验、buildVirtualMachineCreateInput、buildVirtualMachinePatch）。
- `frontend/src/components/VirtualMachineFields.tsx`（VM 专属表单区；Host 选择器从同 Cluster 未删除 BARE_METAL 加载）。

修改：
- `frontend/src/api/resources.ts`（VirtualMachine/HostRef/Input/Patch 类型；Resource.virtual_machine；载荷；ListResourcesQuery.host_resource_id；describeResourceActionError 按 object_type 区分文案）。
- `frontend/src/components/ResourceForm.tsx`（virtual_machine 值/校验/互斥渲染/422 点路径）。
- `frontend/src/pages/ResourceCreatePage.tsx`（VM 必带 virtual_machine，BARE_METAL 不带）。
- `frontend/src/pages/ResourceDetailPage.tsx`（VirtualMachinePanel 展示 Host/单位/未知「—」/disk_gb=0「明确无磁盘」；HostVirtualMachinesPanel 经 host_resource_id 列 VM；409 文案）。
- `frontend/src/pages/HomePage.tsx`、`frontend/src/index.css`、`frontend/scripts/smoke-client.mjs`（+12 F006 用例）。

## 2. Contract/设计符合性

- 宿主四条件（存在/未软删/BARE_METAL/同 Cluster）统一 422 `virtual_machine.host_resource_id`；创建与换 Host 同一校验；无容量超额校验。
- 数值/字符串口径、disk_gb=0 与 null 区分、MiB/GiB 原样、未知存 null 不写 0；互斥 422；VM 对象不含 metadata 键。
- 响应 virtual_machine = VM 对象 / BARE_METAL null，含 host{id,hostname}（宿主软删后仍展开）。
- DELETE Host 引用保护 409 reference_exists + references；VM 软删后放行；恢复 VM 重检 Host 409 dependency_deleted + conflicts。
- 审计白名单扩 virtual_machine；换 Host 记 UPDATE before/after host_resource_id；同事务回滚不留痕。
- **DR-71**：创建/换 Host 读取宿主前对 Host 行 FOR UPDATE；Host 软删路径先锁 Host 行再跑引用检查（检查器仅普通 SELECT）。

## 3. 验证证据（实现自测）

- Backend：真实 postgres:16（csm_test，DB-D10 护栏），`python -m pytest tests -q` → **183 passed, 1 skipped**（skip=test_migrations.py 非 superuser 扩展假设，环境限制，与 F001–F005 基线同因）。F006 专属 32 passed。`alembic heads` → `0006_virtual_machine_details (head)`；真库 upgrade 0004→0005→0006 成功；up/down/up、回填守卫三例通过。
- Frontend：`npm run typecheck` PASS（0 错误）；`npm run build` PASS（49 modules）；`npm run smoke:client` → **64 passed, 0 failed**（F006 新增 12）。

## 4. 未验证项与风险（交 TEST / Review）

- 真实前后端集成（入口 Nginx 往返）：V20 集成半项，待 TEST 阶段 Compose 验证。
- 真实浏览器 DOM/E2E 未做（F006 测试设计已明确非必要判据）。
- Cc/Cf 仅应用层保证，DB 为 ASCII backstop（DB I-5 已知差异）。
- DB 层无 Host 软删守卫触发器（DB-D59）；并发窗口按 DR-71 应用层行锁关闭，运行时行为待独立并发测试。
- 容量超额校验明确不做（§9）；列表 >100 宿主/VM 仅截断提示。

## 5. 提交

- Feature 分支提交见 MERGE 前检查点；本记录由协调器写入。
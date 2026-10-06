# F001 工程与部署底座 — 正式 Review Report

- **Feature**：F001 工程与部署底座（ENABLER，P0，M1）
- **角色**：Reviewer（只读）
- **日期**：2026-10-06
- **Status**：`APPROVED WITH FOLLOW-UP`（协调器核验后持久化）

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F001-engineering-foundation` |
| Base branch / start_commit | `v3` = `77ad69e7b59a2f27d13c206438876bc7cbe73ee9` |
| merge-base | `77ad69e`（= Base，无分叉） |
| 候选 HEAD（批准对象） | `83998e35e621f7976a7fef97cfb9c1eb0c3f9aab` |
| 完整范围 | `77ad69e..83998e3`，9 提交，54 文件，+4268/−18；工作区 clean，无未提交/未跟踪交付物 |
| 测试证据 | `docs/features/F001/test-report.md` TE-1（READY FOR REVIEW，7/7 验收 PASS） |

**批准链核对**：plan_revision 4（用户 2026-10-06，F001 在批准范围）；D02 基础部分签核（Architect 最终设计定稿 + Database f001-baseline.md v1）；contract=NOT_REQUIRED 理由充分（api_required=false，健康检查为运维端点）；pending_changes 无命中；需求基线 revision 3 未被变更覆盖。

## 适用层结论

| 层 | 结论 |
| --- | --- |
| 产品与范围 | PASS（仅工程骨架，无业务对象/认证/业务 API，ENABLER 边界一致，无范围扩张） |
| 架构与依赖 | PASS（目录结构、五服务拓扑、DR-01–DR-06 落实） |
| 数据库与 Migration | PASS（DB-D1–D12 逐项落实；基线仅 pg_trgm；非对称 downgrade 有据；A2 命名约定） |
| Backend 实现 | PASS（健康检查语义 §1.4；get_db 不自动 commit；错误不吞） |
| Frontend 实现 | PASS（同源 /api/v1、无硬编码主机、三态显式、SPA fallback） |
| 安全 | PASS（.env 忽略未跟踪；无硬编码口令；无 §29 禁项；新增依赖均属批准栈） |
| 测试充分性 | PASS（独立复跑：smoke 4 passed；integration 非 superuser 10 passed；V4 重复无残留；护栏实测阻断） |
| 数据完整性 | PASS（F001 无业务写入；适用项对应表完整，证据可信） |

独立复跑摘要：`pytest tests/smoke`→4 passed；`pytest tests/integration`（非 superuser owner）→10 passed，二次重复后 public 残留表 0；DB-D10 护栏三项实测阻断；compileall OK；backend test 镜像构建 exit 0；`/healthz` 重复 Content-Type 独立复现。

## Findings（均非阻塞）

| ID | Severity | Layer | Location | 问题 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| F001-R-01 | NOTE | Docs/Schema | `docs/database/f001-baseline.md` §5 | pk 模板片段多右括号，与定稿 A2/实现不一致（实现正确） | Database/Architect | 否 |
| F001-R-02 | LOW | Backend/Build | `backend/pyproject.toml` | 有界区间但无 Python 锁文件，补丁版本可能漂移（架构 §2.1 称由锁文件固定） | Backend | 否 |
| F001-R-03 | NOTE | Frontend/Supply-chain | `frontend/package-lock.json` | resolved 全部指向 npmmirror 镜像；integrity 哈希齐全 | Frontend/协调器 | 否 |
| F001-R-04 | NOTE | Deploy | `deploy/nginx/nginx.conf` | `/healthz` 辅助探针未在架构列出；与 F001-T-DUP-CT 同位置 | Backend | 否 |

无 BLOCKER / HIGH / 必须修复 MEDIUM。

## 旧缺陷复核

- **F001-T-DUP-CT**（LOW）：确认，严重程度恰当，「不必修复」可接受——独立复现双重 Content-Type；非验收判据端点。
- **F001-T-TESTFIX-EXT**（NOTE）：确认，非产品缺陷——teardown 连带删扩展属测试库会话重建语义。

## Follow-ups（非阻塞，不自动成为产品/架构决定）

1. 修正 f001-baseline.md §5 pk 模板片段与 A2/实现对齐（Database/Architect）。
2. backend 增加锁文件固定补丁版本，或架构正文改记有界约束（Backend/Architect）。
3. 明确前端依赖镜像策略：归一官方源或记录 npmmirror 使用依据（Frontend/协调器）。
4. 择机修正 `/healthz` 单一 Content-Type 并补记部署说明（Backend，可与 F001-T-DUP-CT 一并处理）。

## 未审查项

V1 Compose 全链路采用 TE-1 E.1 证据（下层可分离验证已独立复跑）；V5 未重跑实际恢复（脚本与 DB-D12 判据一致性已审）；真实浏览器 DOM 渲染无环境；T01–T41/T36/§32 按 ENABLER 边界不适用。

## 总裁定

**`APPROVED WITH FOLLOW-UP`** — 核心验收 7/7 满足，必要验证可信且部分经独立复现；无 BLOCKER/HIGH/必须修复 MEDIUM；无未决产品问题。批准仅对候选 `83998e3` 与 Base `77ad69e` 有效；Merge/DONE 由协调器按 git-workflow.md §5 判定。

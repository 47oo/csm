# F027 正式 Review Report

- Feature Branch：feature/F027-scope-enforcement
- start_commit / Base / merge-base：dded9b660f50bec1fcee185147efad7b5baddd8e（v3.2）
- 首轮候选 HEAD：941065b；复审候选 HEAD：52b1af4fd6e3f33cf79fdc3c8b70f8052f02576d
- 审查范围：dded9b6..52b1af4（34 files，+2267/−200）；修复增量 941065b..52b1af4（4 files）
- 工作区：clean；计划校验 PROJECT STATE VALID

## 首轮结论（941065b）

**CHANGES REQUIRED**

- F027-R1（MEDIUM，must-fix）：未授权 Interface 的 422 文案与不存在 Interface 不同，泄露对象存在性（违反 A18/T85）。
- F027-R4（MEDIUM，DONE 前）：Plan 缺少 F027 git 基线字段。
- 非阻塞：F027-R2 部分高风险管理探针未入库；F027-R3 各域 Contract 未回写 F027 交叉引用；F027-R5 `normalize(None)` unrestricted 默认；F027-R6 测试覆盖按文件名放行；F027-R7 命名注释。

## 修复与复审（52b1af4）

- 修复 `app/services/ip_address.py::_validate_interface`：范围校验前移，隐藏 Interface 与不存在 Interface 使用同一 `field:"interface"` 文案；同 Cluster 校验保留其后。
- 新增回归测试 `test_hidden_interface_error_is_indistinguishable_from_missing`；Test Report Repair Verification 1：18 定向、93 相关、全量 718 passed / 2 skipped。
- 复审独立验证：隐藏 vs 不存在完整 JSON 相等；可见同 Cluster 仍 200；可见跨 Cluster 仍返回同 Cluster 文案；F023 导入路径由导入前置范围校验保护。

## 复审结论

**APPROVED WITH FOLLOW-UP**

- F027-R1：CLOSED。
- F027-R4：仍 OPEN，但属合并后 DONE 状态提交的协调器义务，不阻塞实现候选合并。
- 无 BLOCKER / HIGH / 必须修复 MEDIUM；无未决产品问题。
- 批准仅对候选 HEAD 52b1af4 与 Base dded9b6 有效。

## Follow-ups

1. 各域 Contract 回写 F027 范围交叉引用（Architect）。
2. 将高价值 `/tmp` 探针断言并入仓库测试（Tester/Backend，F028 前）。
3. 评估 `scope=None` 显式必填/sentinel 与 `auth_app` 覆盖改为 opt-in marker（Backend/Coordinator）。
4. 修正 Test Report RV-1 对 F023 调用点传 scope 的描述（协调器）。
5. F028 承接真实 Compose、T85–T99 端到端、T01–T84 关键回归、前端页面表现与整体验收。

# 实现公共规则

Backend / Frontend 开始前读取 `AGENTS.md`、`docs/project/handoff.md`、当前 Feature 的已确认需求和架构；有 API 时读取已批准 Contract。阶段放行由 `feature.md` 统一判断。

* 使用 V2 已批准技术栈；缺少必要技术决策时阻塞，不自行选型。
* 只实现已确认范围，保持简单、聚焦；不修改产品事实、领域规则、架构或 Contract。
* 有 API 时，字段、类型、nullable、错误与空结果语义必须符合 Contract。发现契约问题输出 `API CONTRACT CHANGE REQUIRED`，说明问题和双方影响，停止受影响部分。
* 只修改协调器分配的文件；共享文件冲突时停止并交协调器串行处理。并行安全遵循 `AGENTS.md` §9。
* 实现必要的验证和适用的回归测试；报告实际命令、结果、未验证项。修复不能仅通过放宽测试迎合实现。
* 调用方、输入边界、数据完整性和错误处理按实际风险检查，不为未来需求增加框架或基础设施。

交接采用公共格式，附实现范围、Contract 符合情况、数据库影响或 Mock 使用情况。完成只代表本角色交付，不代表 Feature DONE。

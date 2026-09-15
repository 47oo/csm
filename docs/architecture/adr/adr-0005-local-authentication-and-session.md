# ADR-0005: 本地账号认证与会话

## Status

`ACCEPTED`（2026-09-15 用户批准）

**决策记录**：用户于 2026-09-15 批准 DEC-013（方案 A：服务端会话 + HttpOnly Cookie + Argon2id）。

## Context

V1 使用系统本地账号认证（R-AUTH-001），不接入 LDAP / AD / OAuth / SSO（R-AUTH-002），且在无明确产品需求时**不得扩大为复杂 RBAC**（R-AUTH-003）。

部署形态为**内网 HTTP、无 HTTPS**（R-DEPLOY-003），因此凭证与会话 Cookie 在内网明文传输 —— 这是**已确认的产品取舍**，不是架构缺陷。

需要决定会话机制、口令存储与最小权限边界。

## Decision

1. **认证模型**：本地 `users` 表（`username` 唯一、`password_hash`、`active` 标志、时间戳）。账号由**管理员初始化 / 种子创建**，**不开放自助注册**（无产品需求）。
2. **口令存储**：**Argon2id** 哈希（若环境受限则经评估的 bcrypt），带可调参数。明文口令**不得落库、不得落日志、不得出现在错误信息中**。
3. **会话机制**：服务端会话表 + 随机不可预测的 session id；Cookie 设 `HttpOnly` + `SameSite=Lax`；因 V1 为 HTTP，**不设 `Secure`**（浏览器会丢弃该 Cookie）。此取舍必须记录在部署文档中。
4. **权限边界**：全项目**仅有两个状态** —— 已认证 / 未认证。所有 `/api/*`（登录端点除外）要求认证。**不引入角色、权限表或 RBAC**。
5. **登出**使服务端会话失效；会话过期时间与是否滑动续期由实现方案决定并记录。

## Consequences

- 会话可**即时作废**（登出、管理员禁用账号），符合内部运维平台的实际使用模式。
- `HttpOnly` 降低 XSS 造成的凭证泄露影响面；但 HTTP 明文传输风险仍然存在，必须在部署文档中明确「**仅限受控内网**」。
- 无 RBAC 使权限模型极简，与 R-AUTH-003 一致；未来如需 RBAC 必须**重新进入产品规划**。
- 会话状态使多进程横向扩展需要共享存储；V1 单进程不受影响。

## Alternatives Considered

- **JWT（Authorization 头 / localStorage）**：无状态、扩展性好；但难以即时作废（与「本地账号」语义冲突），存于 localStorage 易受 XSS；在 V1 单机场景下没有换回复杂度。
- **HTTP Basic**：实现最简单；但无会话 / 登出体验，每次请求携带口令，风险更高。不推荐。
- **引入 RBAC / 权限表**：无产品需求，违反 R-AUTH-003 与 §25 Simple First。
- **HTTPS / 域名 / 公网入口**：R-DEPLOY-003 明确不要求，且无需求支撑。

## Affected Features

F013 直接；F015 受影响。

Milestone: **M1**（DEC-013）。

## Reversibility

**中等**。会话机制可替换，但因涉及认证边界与部署配置，仍应尽早定型。
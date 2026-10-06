# CSM 数据库备份与恢复骨架（F001）

本目录提供一期数据库备份/恢复**骨架**（数据库设计 `docs/database/f001-baseline.md` DB-D12）。
F001 只交付脚本、恢复文档与冒烟判据，**不宣称覆盖 Audit 数据**（T36 由 F016 以真实证据闭合）。

## 前提

- PostgreSQL 16（含 contrib 扩展；`pg_trgm` 在 PG13+ 为 trusted，安装需目标库 CREATE 权限，不需 superuser）。
- 宿主机**不要求**安装 `pg_dump` / `pg_restore`：脚本会优先使用本机客户端，
  否则回退到在 Compose `db` 容器内执行（定稿 A3）。
- Compose 模式下需 `.env` 已配置 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
  且 `db` 服务已运行（`docker compose up -d db`）。凭据不在命令行回显。
- 本地客户端模式下需 `DATABASE_URL`（`postgresql+psycopg://...` 或 `postgresql://...`）。

## 备份步骤

```bash
# Compose 模式（无本机 pg_dump）
docker compose up -d db
deploy/backup/pg_dump.sh
# -> ./backups/csm-<db>-<UTC 时间戳>.dump

# 本地客户端模式
DATABASE_URL='postgresql+psycopg://user:pass@host:5432/csm' deploy/backup/pg_dump.sh
```

实现要点：`pg_dump -Fc --no-owner --no-privileges`；先写 `.tmp` 再原子 `mv`；失败非零退出；不回显凭据。

## 恢复步骤（默认全新库）

```bash
# 恢复到全新目标库（目标库必须不存在，否则中止）
deploy/backup/restore.sh ./backups/csm-csm-20261006T000000Z.dump csm_restore_test

# 覆盖已有库：仅在显式 --force 时追加 --clean --if-exists
deploy/backup/restore.sh ./backups/csm-csm-20261006T000000Z.dump csm_restore_test --force
```

目标库名只允许 `[A-Za-z0-9_]`；未提供目标库名或目标库已存在且未加 `--force` 时脚本中止。

## 恢复冒烟判据（DB-D12 / TD-2 V5，5 项）

1. 恢复库 `SELECT 1` 成功。
2. `pg_extension` 含 `pg_trgm`（基线扩展）。
3. `alembic_version` 与源库一致。
4. `alembic current` = head，且再次 `alembic upgrade head` 幂等。
5. 后端连恢复库 `/api/v1/health/ready` 返回 200。

## 范围声明

- F001 无业务表；冒烟以 `alembic_version` 与扩展为准，不以业务数据作恢复判据。
- `pg_dump` 默认覆盖全库（含未来 audit 表），但本 Feature **不验证/不宣称 Audit 数据备份覆盖**。
- RPO / RTO、加密、异地保留、定时调度不在 F001 范围，留待后续运维 Feature。
- 容器可启动 ≠ 生产上线验收（需求 §32 独立）。

## 回滚

- 恢复到全新库不影响源库；丢弃恢复库即可回滚（`DROP DATABASE <target>`）。
- `--force` 覆盖已有库属破坏性操作，执行前自行确认目标库可丢弃；本骨架不提供自动备份回滚点。
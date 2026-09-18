"""初始管理员初始化 CLI（F013，AC-11）。

用法::

    python -m app.auth.cli create-initial-admin --username <username>

口令从 **stdin** 读取，**不走 argv**（不进入 shell history）：

- TTY：无回显提示（``getpass``）；
- 非 TTY：读取一行。

命令**幂等**：用户名已存在则输出「已存在，未修改」并退出 0。口令经
``app.auth.policy.validate_password`` 校验（R-AUTH-004 的单一实现）；不足 8 位
退出 1 且不产生账号。

**不存在**任何未认证可达的注册端点 / 页面——这是唯一的账号建立路径。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.auth import policy, service
from app.common.errors import ApiError
from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory


def _read_password() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("口令：")
    return sys.stdin.readline().rstrip("\r\n")


def _create_initial_admin(username: str, settings: Settings) -> int:
    password = _read_password()
    try:
        policy.validate_password(password)
    except ApiError as exc:
        print(f"错误：{exc.message}", file=sys.stderr)
        return 1

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            result = service.create_initial_admin(session, username, password)
            session.commit()
    finally:
        engine.dispose()

    if result.created:
        print(f"已创建初始管理员账号：{result.username}（id={result.user_id}）")
    else:
        print(f"账号 {result.username} 已存在，未修改。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.auth.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-initial-admin", help="创建初始管理员账号（口令从 stdin 读取）"
    )
    create.add_argument("--username", required=True, help="登录名")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.command == "create-initial-admin":
        return _create_initial_admin(args.username, settings)
    raise SystemExit(2)  # pragma: no cover - argparse 已保证分支


if __name__ == "__main__":
    raise SystemExit(main())

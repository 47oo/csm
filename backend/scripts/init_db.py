"""幂等初始化脚本：建表 + 预置首个管理员。

用法（容器内）：python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import initialize  # noqa: E402


def main() -> int:
    initialize()
    print("[csm-init] 初始化完成", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
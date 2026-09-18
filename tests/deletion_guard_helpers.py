"""F014 静态 guard 共享扫描器：检测 ``deleted_at`` 写入 / 反删（undelete）形态。

G-3 与 A15 / G-E 的演进断言共用本扫描器，保证「写入路径 allow-list」只有一份
判定逻辑（``f014-soft-delete-handoff.md`` 问题 11）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "backend" / "app"

#: 唯一允许写入 ``deleted_at`` 的文件（allow-list）。
ALLOWED_DELETED_AT_WRITER = "backend/app/deletion/service.py"

# 写入形态：``obj.deleted_at = ...`` / ``values(deleted_at=...)`` /
# ``setattr(obj, "deleted_at", ...)`` / 裸 SQL ``SET deleted_at = ...``。
# 比较（``==`` / ``!=`` / ``is_(None)``）与 WHERE 过滤不算写入。
_WRITE_RE = re.compile(
    r"\bdeleted_at\s*=(?!=)"
    r"|values\s*\([^)]*\bdeleted_at\s*="
    r"|setattr\s*\([^,]+,\s*['\"]deleted_at['\"]"
)

# 把 ``deleted_at`` 回写为空 = undelete，V1 不允许（R-DELETE-003）。
_UNDELETE_RE = re.compile(r"\bdeleted_at\s*=\s*(?:None|null|NULL)\b")


def scan_deleted_at_writes(app_dir: Path = APP_DIR) -> dict[Path, list[tuple[int, str]]]:
    """返回 ``{文件: [(行号, 行内容), ...]}``，仅含出现 ``deleted_at`` 写入的文件。"""
    hits: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(app_dir.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _WRITE_RE.search(line):
                hits.setdefault(path, []).append((lineno, stripped))
    return hits


def scan_undelete_writes(app_dir: Path = APP_DIR) -> list[str]:
    """返回把 ``deleted_at`` 置回空值的所有位置（应为空）。"""
    offenders: list[str] = []
    for path, lines in scan_deleted_at_writes(app_dir).items():
        for lineno, line in lines:
            if _UNDELETE_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line}")
    return offenders

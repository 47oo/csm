"""T11 — 工程门禁：lint 可执行，且存在真实断言数据库约束的测试（AC-08）。

T11 的第二半（真实断言数据库约束）由 ``tests/database/test_constraints.py``
实现：它使用**原始 psycopg 连接绕开应用层**，断言 SQLSTATE ``23505`` / ``23514``。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_lint_is_executable_and_clean():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "backend", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ruff check 失败：\n{result.stdout}\n{result.stderr}"


def test_database_constraint_assertions_exist():
    constraint_tests = REPO_ROOT / "tests" / "database" / "test_constraints.py"
    assert constraint_tests.exists(), "缺少直接断言数据库约束的测试"
    content = constraint_tests.read_text(encoding="utf-8")
    assert "23505" in content, "缺少唯一性约束（23505）断言"
    assert "23514" in content, "缺少 CHECK 约束（23514）断言"

"""F030 ⑦ guard: ``real_scope`` convention for ``tests/integration``.

This module deliberately does **not** declare ``pytest.mark.real_scope``: it is
the canary proving the legacy default (unrestricted ``AccessScope`` override) is
a fact, and the AST guard that stops a future real-scope module from silently
running as legacy coverage (F030 product P7, architecture §9.2).

Rules (single authoritative statement lives in ``tests/conftest.py::auth_app``):
unmarked ``tests/integration`` modules run with a test-only unrestricted scope
override; any module touching ``AccessScope`` / ``resolve_access_scope`` /
``get_access_scope`` must declare the marker. The only exemption here is this
guard module itself — no wildcard or general allow-list exists on purpose.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parent
GUARD_MODULE = Path(__file__).name
SCOPE_SYMBOLS = frozenset({"AccessScope", "resolve_access_scope", "get_access_scope"})
KNOWN_MARKED = frozenset(
    {"test_cluster_authorizations.py", "test_f027_access_scope.py"}
)
MIN_SCANNED = 20


def _mentions_real_scope(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Attribute) and child.attr == "real_scope"
        for child in ast.walk(node)
    )


def _is_marked(tree: ast.Module) -> bool:
    """True when the module carries ``real_scope`` via pytestmark or decorator."""
    for node in tree.body:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            value = getattr(node, "value", None)
            if value is not None and _mentions_real_scope(value):
                return True
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if any(_mentions_real_scope(d) for d in node.decorator_list):
                return True
    return False


def _scope_symbols_used(tree: ast.Module) -> set[str]:
    """Symbols referenced by import or by name/attribute usage (not comments)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in SCOPE_SYMBOLS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in SCOPE_SYMBOLS:
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in SCOPE_SYMBOLS:
                    found.add(alias.name)
                if alias.asname in SCOPE_SYMBOLS:
                    found.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                tail = alias.name.split(".")[-1]
                if tail in SCOPE_SYMBOLS:
                    found.add(tail)
    return found


def _scan() -> tuple[list[str], set[str], list[str]]:
    """Return (scanned module names, marked module names, offenders)."""
    scanned: list[str] = []
    marked: set[str] = set()
    offenders: list[str] = []
    for path in sorted(INTEGRATION_DIR.glob("test_*.py")):
        if path.name == GUARD_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scanned.append(path.name)
        is_marked = _is_marked(tree)
        if is_marked:
            marked.add(path.name)
        if not is_marked and _scope_symbols_used(tree):
            offenders.append(path.name)
    return scanned, marked, offenders


def test_unmarked_module_gets_legacy_scope(auth_app):
    """Default is a fact: an unmarked module really does get the legacy shim."""
    from app.core.access_scope import AccessScope, get_access_scope

    override = auth_app.dependency_overrides.get(get_access_scope)
    assert override is not None, (
        "unmarked integration module must run with the legacy unrestricted scope"
    )
    scope = override()
    assert scope == AccessScope(unrestricted=True, cluster_ids=frozenset())
    assert scope.unrestricted is True
    assert scope.cluster_ids == frozenset()


def test_real_scope_usage_requires_marker():
    """Any module touching the scope symbols must be marked; no silent legacy."""
    _, _, offenders = _scan()
    assert offenders == [], (
        "these modules use AccessScope/resolve_access_scope/get_access_scope "
        f"without pytestmark = pytest.mark.real_scope: {offenders}"
    )


def test_scope_scan_is_not_vacuous():
    """Guard the guard: the glob and the marker detection must really work."""
    scanned, marked, offenders = _scan()
    assert len(scanned) >= MIN_SCANNED, len(scanned)
    assert KNOWN_MARKED <= marked, sorted(marked)
    assert offenders == []

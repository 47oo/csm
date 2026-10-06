#!/usr/bin/env python3
"""Read-only state/gate checks; approval truth and Git/test evidence still need review."""

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

import yaml


STATES = {"DRAFT", "BLOCKED", "READY", "IN_PROGRESS", "IN_REVIEW", "DONE", "CANCELLED"}
STAGES = {"PRODUCT", "ARCHITECTURE", "DATABASE", "TEST_DESIGN", "CONTRACT", "IMPLEMENTATION", "TEST", "REVIEW", "MERGE"}
RESULTS = {"PENDING", "COMPLETE", "BLOCKED", "NOT_REQUIRED"}
GATES = {"product", "architecture", "database", "test_design", "contract", "backend", "frontend", "test", "review"}
ROOT = Path(__file__).resolve().parents[1]


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently discarding a checkpoint."""


def unique_mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def derive_summary(plan):
    """Derive views only; never infer approval, completeness or Feature status."""
    counts = Counter(f["status"] for f in plan["features"])
    def ids(state):
        return sorted(f["id"] for f in plan["features"] if f["status"] == state)

    return {
        "status": plan["project"]["status"],
        "plan_completeness": plan["planning_status"]["plan_completeness"],
        "counts": {state: counts[state] for state in sorted(STATES)},
        "ready_features": ids("READY"),
        "blocked_draft_features": {state: ids(state) for state in ("BLOCKED", "DRAFT")},
    }


def gate_errors(feature, root=None):
    """Validate prerequisites and the evidence for claimed results, not report truth."""
    errors = []
    fid = feature["id"]
    impl = feature.get("implementation", {})
    layers = feature.get("layers", {})
    evidence = feature.get("evidence", {})
    reasons = feature.get("not_required", {})
    if not all(isinstance(x, dict) for x in (impl, layers, evidence, reasons)):
        return [f"{fid}: implementation/layers/evidence/not_required must be mappings"]

    def require(condition, message):
        if not condition:
            errors.append(f"{fid}: {message}")

    def references(refs, label):
        valid = isinstance(refs, list) and bool(refs) and all(isinstance(r, str) and r.strip() for r in refs)
        require(valid, f"{label} needs nonempty evidence paths")
        if valid and root is not None:
            for ref in refs:
                path = Path(ref.split('#', 1)[0])
                base = Path(root).resolve()
                resolved = (base / path).resolve()
                require(not path.is_absolute() and resolved.is_relative_to(base) and resolved.is_file(),
                        f"missing/invalid evidence file: {ref}")

    for key in impl:
        require(key in GATES, f"unknown implementation gate: {key}")
    for key, value in impl.items():
        if value == "COMPLETE":
            require(not (key in {"database", "backend", "frontend"} and layers.get(key) is False),
                    f"{key} COMPLETE conflicts with layers.{key}=false")
            require(not (key == "contract" and feature.get("api_required") is False),
                    "contract COMPLETE conflicts with api_required=false")
            references(evidence.get(key), key)
        elif value == "NOT_REQUIRED":
            permitted = (key in {"database", "backend", "frontend"} and layers.get(key) is False) or (
                key == "contract" and feature.get("api_required") is False)
            require(permitted, f"{key} cannot be NOT_REQUIRED for this scope")
            require(isinstance(reasons.get(key), str) and bool(reasons[key].strip()),
                    f"{key} NOT_REQUIRED needs reason")

    if "requirements" in feature:
        references(feature["requirements"], "requirements")
    if impl.get("architecture") == "COMPLETE":
        require(set(layers) == {"database", "backend", "frontend"}
                and all(type(v) is bool for v in layers.values()), "completed architecture needs all boolean layers")
        require(type(feature.get("api_required")) is bool, "completed architecture needs api_required boolean")
        require(not layers.get("database") or layers.get("backend") is True,
                "database changes require Backend implementation ownership")

    def passed(key):
        # NOT_REQUIRED validity is checked above.
        return impl.get(key) in {"COMPLETE", "NOT_REQUIRED"}

    prerequisites = {
        "architecture": ["product"],
        "database": ["product", "architecture"],
        "test_design": ["product", "architecture"],
        "contract": ["product", "architecture", "database", "test_design"],
        "backend": ["product", "architecture", "database", "test_design", "contract"],
        "frontend": ["product", "architecture", "database", "test_design", "contract"],
        "test": ["product", "architecture", "database", "test_design", "contract", "backend", "frontend"],
        "review": ["test"],
    }
    for key, dependencies in prerequisites.items():
        if impl.get(key) == "COMPLETE":
            require(all(passed(k) for k in dependencies), f"{key} COMPLETE has unfinished prerequisites")

    needed = {
        "PRODUCT": [], "ARCHITECTURE": ["product"],
        "DATABASE": ["product", "architecture"],
        "TEST_DESIGN": ["product", "architecture"],
        "CONTRACT": ["product", "architecture", "database", "test_design"],
        "IMPLEMENTATION": prerequisites["backend"],
        "TEST": prerequisites["test"],
        "REVIEW": prerequisites["test"] + ["test"],
        "MERGE": list(GATES),
    }
    if feature["status"] in {"IN_PROGRESS", "IN_REVIEW"}:
        stage = feature.get("current_stage")
        require(stage in STAGES, "active Feature needs current_stage")
        require(all(passed(k) for k in needed.get(stage, [])), f"{stage} has unfinished prerequisites")
    # BLOCKED checkpoints retain the failed stage even after invalidating its inputs.
    if feature["status"] == "IN_REVIEW":
        require(feature.get("current_stage") in {"REVIEW", "MERGE"}, "IN_REVIEW needs REVIEW or MERGE stage")
    if feature["status"] == "DONE":
        require(all(passed(k) for k in GATES), "DONE requires every applicable gate complete")
        require(all(impl.get(k) == "COMPLETE" for k in ("product", "architecture", "test_design", "test", "review")),
                "DONE requires Product/Architecture/Test Design/Test/Review COMPLETE")
    return errors


def transition_errors(previous, plan):
    """Compare explicitly supplied snapshots. Never read Git history implicitly."""
    allowed = {
        "DRAFT": {"DRAFT", "READY", "BLOCKED", "CANCELLED"},
        "READY": {"READY", "DRAFT", "BLOCKED", "IN_PROGRESS", "CANCELLED"},
        "IN_PROGRESS": {"IN_PROGRESS", "IN_REVIEW", "BLOCKED", "CANCELLED"},
        "IN_REVIEW": {"IN_REVIEW", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"},
        "BLOCKED": {"BLOCKED", "DRAFT", "READY", "IN_PROGRESS", "IN_REVIEW", "CANCELLED"},
        "DONE": {"DONE"}, "CANCELLED": {"CANCELLED"},
    }
    errors = []
    project_transitions = {
        "DRAFT": {"DRAFT", "ACCEPTED"}, "ACCEPTED": {"ACCEPTED", "IN_PROGRESS"},
        "IN_PROGRESS": {"IN_PROGRESS", "DONE"}, "DONE": {"DONE", "ACCEPTED"},
    }
    old_project, new_project = previous["project"], plan["project"]
    if new_project["status"] not in project_transitions.get(old_project["status"], set()):
        errors.append(f"illegal project transition {old_project['status']} -> {new_project['status']}")
    if old_project["status"] == "DONE" and new_project["status"] == "ACCEPTED":
        approval = new_project.get("approval", {})
        if (new_project.get("plan_revision") == old_project.get("plan_revision")
                or approval.get("plan_revision") != new_project.get("plan_revision")
                or not all(approval.get(k) for k in ("feature_ids", "approved_by", "approved_on", "basis"))):
            errors.append("reopening DONE project needs a new approved plan revision")
    current = {f["id"]: f for f in plan["features"]}
    for old in previous["features"]:
        fid = old["id"]
        new = current.get(fid)
        if new is None:
            errors.append(f"{fid}: cannot remove recorded Feature; use CANCELLED with basis")
            continue
        merge_recovery = old["status"] == "BLOCKED" and old.get("current_stage") == "MERGE" and new["status"] == "DONE"
        if new["status"] not in allowed.get(old["status"], set()) and not merge_recovery:
            errors.append(f"{fid}: illegal transition {old['status']} -> {new['status']}")
        if old["status"] == "DONE" and any(old.get(k) != new.get(k) for k in (
                "git", "requirements", "scope", "acceptance", "implementation", "evidence")):
            errors.append(f"{fid}: cannot rewrite DONE delivery history")
    before, after = previous["execution"], plan["execution"]
    if (before.get("current_feature") is not None and before.get("current_feature") == after.get("current_feature")
            and after.get("repair_rounds", 0) < before.get("repair_rounds", 0)
            and before.get("authorization") == after.get("authorization")):
        errors.append("repair rounds cannot reset without new explicit authorization")
    return errors


def validate(plan, feature_id=None, root=None, previous=None):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    try:
        project = plan["project"]
        entries = plan["features"]
        execution = plan["execution"]
        summary = plan["planning_status"]
        require(isinstance(entries, list), "features must be a list")
        require(summary["plan_completeness"] in {"complete", "incomplete"}, "invalid plan completeness")
        require(summary["plan_completeness"] != "complete" or bool(entries), "empty plan cannot be complete")
        require(project["status"] in {"DRAFT", "ACCEPTED", "IN_PROGRESS", "DONE"}, "invalid project status")
        features = {}
        for feature in entries:
            fid = feature["id"]
            require(isinstance(fid, str) and bool(re.fullmatch(r"F[0-9]+", fid)), "Feature ID must match F + digits")
            require(fid not in features, f"duplicate Feature ID: {fid}")
            features[fid] = feature

        for fid, feature in features.items():
            status = feature["status"]
            if summary["plan_completeness"] == "complete":
                for key in ("title", "kind", "priority", "milestone", "scope", "acceptance", "requirements"):
                    require(bool(feature.get(key)), f"{fid}: complete plan needs {key}")
                require(feature.get("kind") in {"FEATURE", "ENABLER"}, f"{fid}: invalid kind")
                require(feature.get("priority") in {"P0", "P1", "P2"}, f"{fid}: invalid priority")
            require(status in STATES, f"{fid}: invalid status {status}")
            require(feature.get("current_stage") in STAGES | {None}, f"{fid}: invalid stage")
            for key, value in feature.get("layers", {}).items():
                require(key in {"database", "backend", "frontend"} and type(value) is bool,
                        f"{fid}: layers.{key} must be boolean")
            for key, value in feature.get("implementation", {}).items():
                require(value in RESULTS, f"{fid}: invalid implementation.{key}")
            for key in ("current_stage", "next_action"):
                value = feature.get(key)
                require(not (isinstance(value, str) and value.lower().startswith("null")),
                        f"{fid}: {key} must use YAML null, not a null-like string")
            deps = feature["depends_on"]
            require(isinstance(deps, list), f"{fid}: depends_on must be a list")
            for dep in deps:
                require(dep in features, f"{fid}: unknown dependency {dep}")
            if status in {"READY", "DONE"}:
                require(not feature.get("blocking_decisions"), f"{fid}: {status} has blocking decisions")
                require(all(features.get(dep, {}).get("status") == "DONE" for dep in deps),
                        f"{fid}: {status} requires DONE dependencies")
            if status == "DONE":
                require(feature.get("current_stage") is None, f"{fid}: DONE stage must be null")
                require(feature.get("next_action") is None, f"{fid}: DONE next_action must be null")
                require(bool(feature.get("evidence")), f"{fid}: DONE needs evidence references")
                for key in ("base_branch", "branch", "start_commit", "head_commit", "merge_commit"):
                    require(bool(feature.get("git", {}).get(key)), f"{fid}: DONE needs git.{key}")
            if status == "CANCELLED":
                require(bool(feature.get("cancellation_basis")), f"{fid}: CANCELLED needs cancellation_basis")
            if status in {"DRAFT", "READY", "CANCELLED"}:
                require(feature.get("current_stage") is None, f"{fid}: inactive Feature stage must be null")
            errors.extend(gate_errors(feature, root))

        visiting, visited = set(), set()

        def visit(fid):
            if fid in visiting:
                errors.append(f"dependency cycle at {fid}")
                return
            if fid in visited or fid not in features:
                return
            visiting.add(fid)
            for dep in features[fid]["depends_on"]:
                visit(dep)
            visiting.remove(fid)
            visited.add(fid)

        for fid in features:
            visit(fid)

        current = execution.get("current_feature")
        rounds = execution.get("repair_rounds")
        require(type(rounds) is int and 0 <= rounds <= 2, "repair_rounds must be integer 0..2")
        stage = execution.get("current_stage")
        active = [fid for fid, f in features.items() if f["status"] in {"IN_PROGRESS", "IN_REVIEW"}]
        require(len(active) <= 1, "multiple active Features")
        if current is None:
            require(stage is None, "execution stage without current_feature")
            # One active Feature without a checkpoint is a legitimate recovery candidate.
        else:
            require(current in features, "execution references unknown Feature")
            target = features.get(current, {})
            require(target.get("status") in {"IN_PROGRESS", "IN_REVIEW", "BLOCKED"},
                    "execution must reference an active or blocked Feature, not DONE")
            require(stage in STAGES and stage == target.get("current_stage"),
                    "execution/Feature stage mismatch")
            require(not active or active == [current], "active Feature differs from checkpoint")

        counts = Counter(f["status"] for f in features.values())
        for status in STATES:
            actual = summary["counts"].get(status, 0)
            require(type(actual) is int and actual == counts[status], f"count mismatch: {status}")
        require(summary["status"] == project["status"], "planning/project status mismatch")
        for status, recorded in (
            ("READY", summary["ready_features"]),
            ("BLOCKED", summary["blocked_draft_features"]["BLOCKED"]),
            ("DRAFT", summary["blocked_draft_features"]["DRAFT"]),
        ):
            require(sorted(recorded) == sorted(fid for fid, f in features.items() if f["status"] == status),
                    f"derived list mismatch: {status}")
        if project["status"] == "DONE":
            require(bool(features) and summary["plan_completeness"] == "complete", "empty/incomplete project cannot be DONE")
            require(all(f["status"] in {"DONE", "CANCELLED"} for f in features.values()), "project DONE has unfinished Features")
            require(current is None, "project DONE has checkpoint")
            acceptance = project.get("acceptance", {})
            refs = acceptance.get("evidence", [])
            require(acceptance.get("status") == "COMPLETE" and isinstance(refs, list) and bool(refs),
                    "project DONE needs overall acceptance COMPLETE and evidence")
            if root is not None:
                base = Path(root).resolve()
                for ref in refs:
                    path = Path(ref.split('#', 1)[0])
                    resolved = (base / path).resolve()
                    require(not path.is_absolute() and resolved.is_relative_to(base) and resolved.is_file(),
                            f"missing/invalid overall acceptance file: {ref}")

        # Authorization is required for active work and explicit dispatch, not idle planning.
        if active or current is not None or feature_id is not None:
            authorization = execution.get("authorization")
            valid = isinstance(authorization, dict) and all(authorization.get(k) for k in (
                "plan_revision", "feature_ids", "authorized_by", "authorized_on", "basis"))
            require(valid, "EXECUTION AUTHORIZATION REQUIRED: missing authorization metadata")
            require(execution.get("mode") in {"SINGLE", "CONTINUOUS"}, "execution needs SINGLE/CONTINUOUS mode")
            if valid:
                scope = authorization["feature_ids"]
                require(authorization["plan_revision"] == project.get("plan_revision"), "authorization revision mismatch")
                require(isinstance(scope, list) and all(fid in features for fid in scope), "invalid authorization scope")
                targets = set(active + ([current] if current else []) + ([feature_id] if feature_id else []))
                require(isinstance(scope, list) and targets.issubset(scope), "Feature outside execution authorization scope")
                require(execution.get("mode") != "SINGLE" or len(scope) == 1, "SINGLE requires exactly one authorized Feature")

        changes = plan.get("pending_changes", [])
        require(isinstance(changes, list), "pending_changes must be a list")
        change_ids = set()
        for change in changes:
            require(bool(change.get("id")) and change["id"] not in change_ids, "missing/duplicate pending change ID")
            change_ids.add(change["id"])
            require(bool(change.get("proposal")), "pending change needs proposal reference")
            affects = change["affects"]
            require(affects == "ALL" or (isinstance(affects, list) and bool(affects)
                    and all(fid in features for fid in affects)), "invalid pending change affects")

        if feature_id is not None:
            require(feature_id in features, f"unknown selected Feature: {feature_id}")
            require(project["status"] in {"ACCEPTED", "IN_PROGRESS"}
                    and summary["plan_completeness"] == "complete", "project not executable")
            selected = features.get(feature_id, {})
            recoverable = current == feature_id or (current is None and active == [feature_id])
            require(selected.get("status") == "READY" or recoverable, "selected Feature is neither READY nor recovery target")
            require(current in (None, feature_id) and (not active or active == [feature_id]), "selected Feature conflicts with recovery target")
            require(not selected.get("blocking_decisions"), "selected Feature has blocking decisions")
            require(all(features.get(dep, {}).get("status") == "DONE" for dep in selected.get("depends_on", [])),
                    "selected Feature requires DONE dependencies")
            approval = project.get("approval", {})
            complete = all(approval.get(k) for k in ("plan_revision", "feature_ids", "approved_by", "approved_on", "basis"))
            require(complete, "PROJECT APPROVAL RECONCILIATION REQUIRED: approval metadata incomplete")
            if complete:
                require(approval.get("plan_revision") == project.get("plan_revision"), "approval revision mismatch")
            scope = approval.get("feature_ids", [])
            if complete:
                require(isinstance(scope, list) and feature_id in scope and all(fid in features for fid in scope),
                        "selected Feature outside valid approval scope")
            for change in changes:
                require(change["affects"] != "ALL" and feature_id not in change["affects"],
                        f"selected Feature paused by {change['id']}")
        if previous is not None and not errors:
            errors.extend(transition_errors(previous, plan))
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        errors.append(f"invalid plan structure: {exc}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/project/project-plan.yaml")
    parser.add_argument("--feature", help="Also validate dispatch metadata for this Feature")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root for evidence paths")
    parser.add_argument("--previous", type=Path, help="Explicit earlier V3 plan snapshot for transition checks")
    args = parser.parse_args()
    try:
        plan = yaml.load(args.plan.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        previous = yaml.load(args.previous.read_text(encoding="utf-8"), Loader=UniqueKeyLoader) if args.previous else None
        errors = validate(plan, args.feature, root=args.root, previous=previous)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        errors = [str(exc)]
    if errors:
        print("PROJECT STATE INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PROJECT STATE VALID (structure/gates/files; verify approval truth and Git/test evidence separately)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

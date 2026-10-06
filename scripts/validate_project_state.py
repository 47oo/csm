#!/usr/bin/env python3
"""Read-only structural checks; approval provenance and Git evidence need human review."""

import argparse
from collections import Counter
from pathlib import Path
import sys

import yaml


STATES = {"DRAFT", "BLOCKED", "READY", "IN_PROGRESS", "IN_REVIEW", "DONE", "CANCELLED"}
STAGES = {"PRODUCT", "ARCHITECTURE", "CONTRACT", "DATABASE", "IMPLEMENTATION", "TEST", "REVIEW", "MERGE"}
RESULTS = {"PENDING", "COMPLETE", "BLOCKED", "NOT_REQUIRED"}
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


def validate(plan, feature_id=None):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    try:
        project = plan["project"]
        entries = plan["features"]
        execution = plan["execution"]
        summary = plan["planning_status"]
        require(project["status"] in {"DRAFT", "ACCEPTED", "IN_PROGRESS", "DONE"}, "invalid project status")
        features = {}
        for feature in entries:
            fid = feature["id"]
            require(isinstance(fid, str) and bool(fid), "Feature ID must be a nonempty string")
            require(fid not in features, f"duplicate Feature ID: {fid}")
            features[fid] = feature

        for fid, feature in features.items():
            status = feature["status"]
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
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        errors.append(f"invalid plan structure: {exc}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/project/project-plan.yaml")
    parser.add_argument("--feature", help="Also validate dispatch metadata for this Feature")
    args = parser.parse_args()
    try:
        plan = yaml.load(args.plan.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        errors = validate(plan, args.feature)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        errors = [str(exc)]
    if errors:
        print("PROJECT STATE INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PROJECT STATE VALID (structure only; verify approval sources, authorization and Git evidence separately)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

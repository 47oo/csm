"""Regression cases for scheduling invariants, independent of the live project plan."""

from copy import deepcopy
import unittest

import yaml

from validate_project_state import UniqueKeyLoader, validate


def baseline():
    return {
        "project": {"status": "IN_PROGRESS", "plan_revision": 2, "approval": {
            "plan_revision": 2, "feature_ids": ["F001", "F002"],
            "approved_by": "user", "approved_on": "2026-10-06", "basis": "test decision record",
        }},
        "features": [
            {"id": "F001", "status": "DONE", "depends_on": [], "current_stage": None,
             "next_action": None, "evidence": ["review.md"],
             "git": {key: "evidence" for key in ("base_branch", "branch", "start_commit", "head_commit", "merge_commit")}},
            {"id": "F002", "status": "READY", "depends_on": ["F001"], "blocking_decisions": []},
        ],
        "execution": {"current_feature": None, "current_stage": None},
        "planning_status": {"status": "IN_PROGRESS", "plan_completeness": "complete",
                            "counts": {"DONE": 1, "READY": 1}, "ready_features": ["F002"],
                            "blocked_draft_features": {"BLOCKED": [], "DRAFT": []}},
    }


class StateValidationTests(unittest.TestCase):
    def test_valid_plan_and_scoped_dispatch(self):
        plan = baseline()
        original = deepcopy(plan)
        self.assertEqual(validate(plan, "F002"), [])
        self.assertEqual(plan, original)

    def test_finished_feature_cannot_remain_checkpoint(self):
        plan = baseline()
        plan["execution"] = {"current_feature": "F001", "current_stage": "ARCHITECTURE"}
        self.assertTrue(any("not DONE" in e for e in validate(plan)))

    def test_null_like_string_is_not_null(self):
        plan = baseline()
        plan["features"][0]["next_action"] = "null（next task）"
        self.assertTrue(any("YAML null" in e for e in validate(plan)))

    def test_cycle_and_unfinished_dependency(self):
        plan = baseline()
        plan["features"][0]["depends_on"] = ["F002"]
        errors = validate(plan)
        self.assertTrue(any("cycle" in e for e in errors))
        self.assertTrue(any("requires DONE" in e for e in errors))

    def test_stale_counts_and_lists(self):
        plan = baseline()
        plan["planning_status"]["counts"]["READY"] = 0
        plan["planning_status"]["ready_features"] = []
        errors = validate(plan)
        self.assertTrue(any("count mismatch" in e for e in errors))
        self.assertTrue(any("derived list mismatch" in e for e in errors))

    def test_legacy_approval_is_not_invented(self):
        plan = baseline()
        del plan["project"]["approval"]
        self.assertEqual(validate(plan), [])
        self.assertTrue(any("RECONCILIATION REQUIRED" in e for e in validate(plan, "F002")))

    def test_stale_or_partial_approval_cannot_expand_scope(self):
        for update, message in [({"plan_revision": 1}, "revision mismatch"),
                                ({"feature_ids": ["F001"]}, "outside valid approval")]:
            with self.subTest(update=update):
                plan = baseline()
                plan["project"]["approval"].update(update)
                self.assertTrue(any(message in e for e in validate(plan, "F002")))

    def test_pending_change_pauses_only_affected_features(self):
        for affects, blocked in [(["F001"], False), (["F002"], True), ("ALL", True)]:
            with self.subTest(affects=affects):
                plan = baseline()
                plan["pending_changes"] = [{"id": "CR1", "proposal": "proposal.md", "affects": affects}]
                self.assertEqual(bool(validate(plan, "F002")), blocked)

    def test_unique_active_feature_is_recoverable_without_checkpoint(self):
        plan = baseline()
        plan["features"][1].update(status="IN_PROGRESS", current_stage="IMPLEMENTATION")
        plan["planning_status"].update(counts={"DONE": 1, "IN_PROGRESS": 1}, ready_features=[])
        self.assertEqual(validate(plan, "F002"), [])
        self.assertTrue(validate(plan, "F001"))
        plan["execution"] = {"current_feature": "F002", "current_stage": "TEST"}
        self.assertTrue(any("stage mismatch" in e for e in validate(plan)))

    def test_empty_done_project_is_rejected(self):
        plan = baseline()
        plan["features"] = []
        plan["project"]["status"] = "DONE"
        plan["planning_status"].update(status="DONE", counts={}, ready_features=[])
        self.assertTrue(any("empty/incomplete" in e for e in validate(plan)))

    def test_invalid_types_and_duplicate_keys_fail_closed(self):
        self.assertTrue(validate({}))
        plan = baseline()
        plan["features"][1]["layers"] = {"backend": "false"}
        self.assertTrue(any("boolean" in e for e in validate(plan)))
        with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
            yaml.load("execution: null\nexecution: {}\n", Loader=UniqueKeyLoader)


if __name__ == "__main__":
    unittest.main()

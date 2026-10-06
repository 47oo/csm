"""Regression cases for scheduling invariants, independent of the live project plan."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml

from validate_project_state import GATES, UniqueKeyLoader, derive_summary, validate


def baseline():
    plan = {
        "project": {"status": "IN_PROGRESS", "plan_revision": 2, "approval": {
            "plan_revision": 2, "feature_ids": ["F001", "F002"],
            "approved_by": "user", "approved_on": "2026-10-06", "basis": "test decision record",
        }},
        "features": [
            {"id": "F001", "status": "DONE", "depends_on": [], "current_stage": None,
             "next_action": None,
             "git": {key: "evidence" for key in ("base_branch", "branch", "start_commit", "head_commit", "merge_commit")}},
            {"id": "F002", "status": "READY", "depends_on": ["F001"], "blocking_decisions": []},
        ],
        "execution": {"current_feature": None, "current_stage": None, "repair_rounds": 0,
                      "mode": "CONTINUOUS", "authorization": {
                          "plan_revision": 2, "feature_ids": ["F002"], "authorized_by": "user",
                          "authorized_on": "2026-10-06", "basis": "test explicit execution request"}},
        "planning_status": {"status": "IN_PROGRESS", "plan_completeness": "complete",
                            "counts": {"DONE": 1, "READY": 1}, "ready_features": ["F002"],
                            "blocked_draft_features": {"BLOCKED": [], "DRAFT": []}},
    }
    for f in plan["features"]:
        f.update(title=f["id"], kind="FEATURE", priority="P0", milestone="M1", scope=["fixture scope"],
                 acceptance=["fixture acceptance"], requirements=["evidence.md"],
                 layers={"database": True, "backend": True, "frontend": True}, api_required=True)
        f["implementation"] = {k: "COMPLETE" for k in GATES}
        f["evidence"] = {k: ["evidence.md"] for k in GATES}
    plan["features"][1]["implementation"].update(backend="PENDING", frontend="PENDING", test="PENDING", review="PENDING")
    return plan


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

    def test_done_rejects_blocked_or_missing_required_results(self):
        for gate in GATES:
            for result in ("BLOCKED", "PENDING", None):
                with self.subTest(gate=gate, result=result):
                    plan = baseline()
                    if result is None:
                        del plan["features"][0]["implementation"][gate]
                    else:
                        plan["features"][0]["implementation"][gate] = result
                    self.assertTrue(validate(plan))

    def test_authorization_is_required_and_scoped(self):
        for auth in (None, {}, {"basis": "go"}):
            plan = baseline()
            plan["execution"]["authorization"] = auth
            self.assertTrue(any("AUTHORIZATION REQUIRED" in e for e in validate(plan, "F002")))
        for patch, message in (({"plan_revision": 1}, "authorization revision mismatch"),
                               ({"feature_ids": ["F001"]}, "outside execution authorization")):
            plan = baseline()
            plan["execution"]["authorization"].update(patch)
            self.assertTrue(any(message in e for e in validate(plan, "F002")))

    def test_frontend_cannot_start_before_database_and_test_design(self):
        for gate in ("database", "test_design", "contract"):
            plan = baseline()
            f = plan["features"][1]
            f.update(status="IN_PROGRESS", current_stage="IMPLEMENTATION")
            f["implementation"][gate] = "PENDING"
            plan["planning_status"] = derive_summary(plan)
            self.assertTrue(any("unfinished prerequisites" in e for e in validate(plan, "F002")))

    def test_parallel_database_and_test_design_do_not_wait_for_each_other(self):
        for stage in ("DATABASE", "TEST_DESIGN"):
            plan = baseline()
            f = plan["features"][1]
            f.update(status="IN_PROGRESS", current_stage=stage)
            f["implementation"].update(database="PENDING", test_design="PENDING", contract="PENDING")
            plan["planning_status"] = derive_summary(plan)
            self.assertEqual(validate(plan, "F002"), [])

    def test_design_ready_does_not_allow_review(self):
        plan = baseline()
        plan["features"][1].update(status="IN_REVIEW", current_stage="REVIEW")
        plan["planning_status"] = derive_summary(plan)
        self.assertTrue(any("unfinished prerequisites" in e for e in validate(plan)))

    def test_not_required_requires_scope_and_reason(self):
        plan = baseline()
        f = plan["features"][0]
        f["layers"]["database"] = False
        f["implementation"]["database"] = "NOT_REQUIRED"
        self.assertTrue(any("needs reason" in e for e in validate(plan)))
        f["not_required"] = {"database": "No persistence change"}
        self.assertEqual(validate(plan), [])
        f["layers"]["database"] = True
        self.assertTrue(any("cannot be NOT_REQUIRED" in e for e in validate(plan)))
        f["implementation"]["test"] = "NOT_REQUIRED"
        self.assertTrue(any("test cannot be NOT_REQUIRED" in e for e in validate(plan)))

    def test_evidence_must_exist_within_root(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            plan = baseline()
            self.assertTrue(any("evidence file" in e for e in validate(plan, root=root)))
            (root / "evidence.md").write_text("Test evidence fixture", encoding="utf-8")
            self.assertEqual(validate(plan, root=root), [])
            for ref in ("../outside.md", str(root / "evidence.md")):
                plan["features"][0]["evidence"]["review"] = [ref]
                self.assertTrue(any("evidence file" in e for e in validate(plan, root=root)))

    def test_unknown_gate_or_no_evidence_cannot_claim_complete(self):
        plan = baseline()
        plan["features"][0]["implementation"]["typo"] = "COMPLETE"
        self.assertTrue(any("unknown implementation" in e for e in validate(plan)))
        plan = baseline()
        del plan["features"][0]["evidence"]["review"]
        self.assertTrue(any("review needs" in e for e in validate(plan)))

    def test_repair_budget_and_reset(self):
        for value in (-1, 3, True, "1"):
            plan = baseline()
            plan["execution"]["repair_rounds"] = value
            self.assertTrue(any("repair_rounds" in e for e in validate(plan)))
        previous = baseline()
        previous["features"][1].update(status="IN_PROGRESS", current_stage="IMPLEMENTATION")
        previous["execution"].update(current_feature="F002", current_stage="IMPLEMENTATION", repair_rounds=1)
        previous["planning_status"] = derive_summary(previous)
        plan = deepcopy(previous)
        plan["execution"]["repair_rounds"] = 0
        self.assertTrue(any("cannot reset" in e for e in validate(plan, previous=previous)))
        plan["execution"]["authorization"]["basis"] = "new explicit resume request"
        self.assertEqual(validate(plan, previous=previous), [])

    def test_state_transition_cannot_skip_review_or_rewrite_history(self):
        previous = baseline()
        plan = deepcopy(previous)
        f = plan["features"][1]
        f.update(status="DONE", current_stage=None, next_action=None, git=deepcopy(plan["features"][0]["git"]))
        f["implementation"] = {k: "COMPLETE" for k in GATES}
        plan["planning_status"] = derive_summary(plan)
        self.assertTrue(any("illegal transition" in e for e in validate(plan, previous=previous)))
        previous["features"][1].update(status="IN_REVIEW", current_stage="REVIEW")
        self.assertEqual(validate(plan, previous=previous), [])
        plan["features"][0]["scope"] = ["silently changed"]
        self.assertTrue(any("DONE delivery history" in e for e in validate(plan, previous=previous)))

    def test_no_database_or_api_scope_can_complete_with_reasons(self):
        plan = baseline()
        f = plan["features"][0]
        f.update(api_required=False, layers={"database": False, "backend": False, "frontend": True})
        f["not_required"] = {key: "Not in this scope" for key in ("database", "backend", "contract")}
        for key in f["not_required"]:
            f["implementation"][key] = "NOT_REQUIRED"
        self.assertEqual(validate(plan), [])
        f["implementation"]["contract"] = "COMPLETE"
        self.assertTrue(any("api_required=false" in e for e in validate(plan)))

    def test_project_done_needs_overall_acceptance(self):
        plan = baseline()
        plan["features"] = plan["features"][:1]
        plan["project"]["status"] = "DONE"
        plan["planning_status"] = derive_summary(plan)
        self.assertTrue(any("overall acceptance" in e for e in validate(plan)))
        plan["project"]["acceptance"] = {"status": "COMPLETE", "evidence": ["acceptance.md"]}
        self.assertEqual(validate(plan), [])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "evidence.md").write_text("fixture", encoding="utf-8")
            self.assertTrue(any("overall acceptance file" in e for e in validate(plan, root=root)))
            (root / "acceptance.md").write_text("fixture", encoding="utf-8")
            self.assertEqual(validate(plan, root=root), [])

    def test_merge_recovery_and_feature_history_preservation(self):
        previous = baseline()
        previous["features"][0].update(status="BLOCKED", current_stage="MERGE")
        plan = baseline()
        self.assertEqual(validate(plan, previous=previous), [])
        plan["features"].pop()
        plan["planning_status"] = derive_summary(plan)
        self.assertTrue(any("cannot remove recorded Feature" in e for e in validate(plan, previous=previous)))


if __name__ == "__main__":
    unittest.main()

"""Behavior checks for deterministic, read-only checking and safe derived updates."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import yaml

from render_project_views import render
from test_validate_project_state import baseline
from validate_project_state import derive_summary


SCRIPT = Path(__file__).with_name("render_project_views.py")


class ProjectViewTests(unittest.TestCase):
    def test_render_is_deterministic_and_does_not_mutate_plan(self):
        plan = baseline()
        before = deepcopy(plan)
        views = render(plan)
        plan["features"].reverse()
        self.assertEqual(render(plan), views)
        plan["features"].reverse()
        self.assertEqual(plan, before)
        self.assertIn('n0 --> n1', views['dependency-map.md'])
        self.assertIn('1 / 2', views['milestones.md'])

    def test_titles_are_escaped_and_cannot_inject_mermaid(self):
        plan = baseline()
        plan["features"][0]["title"] = '<script>x</script>|x\ny'
        views = render(plan)
        self.assertNotIn('<script>', views['backlog.md'])
        self.assertIn('&#124;', views['backlog.md'])
        self.assertNotIn('<script>x</script>', views['dependency-map.md'])

    def test_empty_draft_is_not_invented_into_a_plan(self):
        plan = baseline()
        plan["features"] = []
        plan["project"]["status"] = 'DRAFT'
        plan["planning_status"]["plan_completeness"] = 'incomplete'
        for body in render(plan).values():
            self.assertIn('尚未规划', body)
            self.assertNotIn('F001', body)

    def test_cli_check_write_staleness_and_preservation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            plan_path = root / 'plan.yaml'
            (root / 'evidence.md').write_text('fixture evidence', encoding='utf-8')
            plan = baseline()
            plan['planning_status']['counts']['DONE'] = 99
            plan_path.write_text(yaml.safe_dump(plan), encoding='utf-8')
            original_text = plan_path.read_text()
            command = [sys.executable, str(SCRIPT), '--plan', str(plan_path), '--root', str(root)]
            check = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(check.returncode, 1)
            self.assertEqual(plan_path.read_text(), original_text)
            self.assertFalse((root / 'backlog.md').exists())

            write = subprocess.run(command + ['--write'], capture_output=True, text=True)
            self.assertEqual(write.returncode, 0, write.stderr)
            updated = yaml.safe_load(plan_path.read_text())
            expected = deepcopy(plan)
            expected['planning_status'] = derive_summary(plan)
            self.assertEqual(updated, expected)  # Includes unchanged authorization and approval.
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertEqual(subprocess.run(command + ['--write'], capture_output=True).returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

            (root / 'backlog.md').write_text('stale', encoding='utf-8')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)

    def test_invalid_gate_does_not_write_anything(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'evidence.md').write_text('fixture evidence', encoding='utf-8')
            plan = baseline()
            plan['features'][0]['implementation']['test'] = 'BLOCKED'
            path = root / 'plan.yaml'
            path.write_text(yaml.safe_dump(plan), encoding='utf-8')
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(SCRIPT), '--plan', str(path),
                                     '--root', str(root), '--write'], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, path.read_bytes())
            self.assertFalse((root / 'backlog.md').exists())


if __name__ == '__main__':
    unittest.main()

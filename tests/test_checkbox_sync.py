#!/usr/bin/env python3
"""Tests for checkbox-only Markdown synchronization."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_model import TodoList
from todo_render import render_document
from todo_sync import synchronize_views
from todo_validation import CanonicalTodoValidator


def document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [
            {
                "id": "aaaaaaaaaaaa",
                "name": "Parent",
                "priority": "must",
                "completed": False,
                "dependencies": ["bbbbbbbbbbbb"],
            },
            {
                "id": "bbbbbbbbbbbb",
                "name": "Repeated dependency",
                "priority": "should",
                "completed": False,
                "dependencies": [],
            },
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [
            {"category": "work", "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]}
        ],
    })


class CheckboxSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="todo-sync-")
        self.root = Path(self.temporary.name)
        self.validator = CanonicalTodoValidator(ROOT / "schema")
        self.document = document()
        self.rendered = render_document(
            self.document, list(self.validator.priority_policy.order)
        )
        for name, view in self.rendered.items():
            (self.root / name).write_text(view.content)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def views(self) -> dict[str, str]:
        return {path.name: path.read_text() for path in self.root.glob("*.md")}

    def test_synchronizes_consistent_repeated_checkboxes(self) -> None:
        path = self.root / "work.md"
        content = path.read_text().replace("[ ] Repeated dependency", "[x] Repeated dependency")
        path.write_text(content)
        result = synchronize_views(self.document, self.rendered, self.views(), str(self.root))
        self.assertEqual(result.issues, ())
        self.assertEqual(result.changed_task_ids, ("bbbbbbbbbbbb",))
        self.assertTrue(result.document["tasks"][1]["completed"])

    def test_conflicting_repeated_checkboxes_fail(self) -> None:
        path = self.root / "work.md"
        content = path.read_text().replace(
            "    - [ ] Repeated dependency — Should",
            "    - [x] Repeated dependency — Should",
        )
        path.write_text(content)
        result = synchronize_views(self.document, self.rendered, self.views(), str(self.root))
        self.assertTrue(any("conflicts" in issue.message for issue in result.issues))
        self.assertEqual(result.changed_task_ids, ())

    def test_structural_edits_fail(self) -> None:
        path = self.root / "work.md"
        path.write_text(path.read_text().replace("Repeated dependency", "Renamed", 1))
        result = synchronize_views(self.document, self.rendered, self.views(), str(self.root))
        self.assertTrue(any("differs" in issue.message for issue in result.issues))

    def test_invalid_completion_transition_does_not_write(self) -> None:
        todo_list = self.root / "todo.json"
        todo_list.write_text(json.dumps(self.document, indent=2) + "\n")
        path = self.root / "work.md"
        path.write_text(path.read_text().replace("- [ ] Parent", "- [x] Parent", 1))
        before = todo_list.read_text()
        result = subprocess.run(
            [str(ROOT / "bin" / "sync-todos"), str(todo_list)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("incomplete dependency", result.stderr)
        self.assertEqual(todo_list.read_text(), before)

    def test_cli_supports_output_stdout_and_dry_run(self) -> None:
        todo_list = self.root / "todo.json"
        todo_list.write_text(json.dumps(self.document, indent=2) + "\n")
        path = self.root / "work.md"
        path.write_text(
            path.read_text().replace("[ ] Repeated dependency", "[x] Repeated dependency")
        )
        alternate = self.root / "output" / "updated.json"
        written = subprocess.run(
            [
                str(ROOT / "bin" / "sync-todos"),
                "--output",
                str(alternate),
                str(todo_list),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        stdout = subprocess.run(
            [str(ROOT / "bin" / "sync-todos"), "--stdout", str(todo_list)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        dry_run = subprocess.run(
            [str(ROOT / "bin" / "sync-todos"), "--dry-run", str(todo_list)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertTrue(json.loads(alternate.read_text())["tasks"][1]["completed"])
        self.assertFalse(json.loads(todo_list.read_text())["tasks"][1]["completed"])
        self.assertEqual(stdout.returncode, 0, stdout.stderr)
        self.assertTrue(json.loads(stdout.stdout)["tasks"][1]["completed"])
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn("Would synchronize 1 task", dry_run.stdout)
        self.assertFalse(json.loads(todo_list.read_text())["tasks"][1]["completed"])


if __name__ == "__main__":
    unittest.main()

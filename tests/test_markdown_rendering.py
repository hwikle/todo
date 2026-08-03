#!/usr/bin/env python3
"""Tests for deterministic canonical-JSON-to-Markdown rendering."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_render import render_document
from todo_validation import CanonicalTodoValidator


def document() -> dict[str, object]:
    return {
        "date": "2042-01-02",
        "tasks": [
            {
                "id": "aaaaaaaaaaaa",
                "name": "Parent",
                "priority": "must",
                "completed": False,
                "dependencies": ["bbbbbbbbbbbb"],
                "description": "First line\nSecond line",
                "due": {"year": 2042, "month": 1, "day": 5, "time": "09:30"},
                "deadline_kind": "hard",
            },
            {
                "id": "bbbbbbbbbbbb",
                "name": "Shared dependency",
                "priority": "should",
                "completed": False,
                "dependencies": [],
            },
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [
            {"category": "work", "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]}
        ],
    }


class MarkdownRenderingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = CanonicalTodoValidator(ROOT / "schema")

    def test_renders_id_free_repeated_dependencies(self) -> None:
        rendered = render_document(document(), list(self.validator.priority_order))["work.md"]
        self.assertNotIn("task:", rendered.content)
        self.assertNotIn("aaaaaaaaaaaa", rendered.content)
        self.assertEqual(rendered.content.count("Shared dependency"), 2)
        self.assertIn("    - [ ] Shared dependency — Should", rendered.content)
        self.assertIn("## Should\n\n- [ ] Shared dependency", rendered.content)
        child_occurrences = [
            item for item in rendered.occurrences if item.task_id == "bbbbbbbbbbbb"
        ]
        self.assertEqual(len(child_occurrences), 2)

    def test_renders_due_metadata_without_task_ids(self) -> None:
        content = render_document(document(), list(self.validator.priority_order))["work.md"].content
        self.assertIn(
            "<!-- due:2042-01-05 time:09:30 due-kind:hard -->",
            content,
        )
        self.assertIn("Due: January 5, 2042 at 9:30 AM — Hard deadline.", content)

    def test_cli_requires_explicit_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-render-") as temporary:
            root = Path(temporary)
            source = root / "todo.json"
            source.write_text(json.dumps(document()))
            first = subprocess.run(
                [str(ROOT / "bin" / "render-todos"), str(source)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [str(ROOT / "bin" / "render-todos"), str(source)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            replaced = subprocess.run(
                [str(ROOT / "bin" / "render-todos"), "--replace", str(source)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(replaced.returncode, 0, replaced.stderr)


if __name__ == "__main__":
    unittest.main()

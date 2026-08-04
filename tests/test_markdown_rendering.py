#!/usr/bin/env python3
"""Tests for deterministic canonical-JSON-to-Markdown rendering."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar, cast


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_model import TodoList
from todo_render import combine_rendered, render_document
from todo_validation import CanonicalTodoValidator


def document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "name": "Parent",
                "priority": "should",
                "completed": False,
                "dependencies": ["00000000-0000-4000-8000-000000000002"],
                "description": "First line\nSecond line",
                "due": {"year": 2042, "month": 1, "day": 5, "time": "09:30"},
                "deadline_kind": "hard",
            },
            {
                "id": "00000000-0000-4000-8000-000000000002",
                "name": "Shared dependency",
                "priority": "should",
                "completed": False,
                "dependencies": [],
            },
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [
            {"category": "work", "tasks": ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]}
        ],
    })


class MarkdownRenderingTest(unittest.TestCase):
    validator: ClassVar[CanonicalTodoValidator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = CanonicalTodoValidator(ROOT / "schema")

    def test_renders_category_dependency_only_beneath_parent(self) -> None:
        rendered = render_document(
            document(), list(self.validator.priority_policy.order)
        )["work.md"]
        self.assertNotIn("task:", rendered.content)
        self.assertNotIn("00000000-0000-4000-8000-000000000001", rendered.content)
        self.assertEqual(rendered.content.count("Shared dependency"), 1)
        self.assertIn("    - [ ] Shared dependency", rendered.content)
        self.assertNotIn("## Should\n\n- [ ] Shared dependency", rendered.content)
        child_occurrences = [
            item for item in rendered.occurrences if item.task_id == "00000000-0000-4000-8000-000000000002"
        ]
        self.assertEqual(len(child_occurrences), 1)

    def test_shared_dependency_renders_under_each_category_parent(self) -> None:
        shared = document()
        shared["tasks"].insert(1, {
            "id": "00000000-0000-4000-8000-000000000003",
            "name": "Second parent",
            "priority": "should",
            "completed": False,
            "dependencies": ["00000000-0000-4000-8000-000000000002"],
        })
        shared["category_memberships"][0]["tasks"].insert(
            1, "00000000-0000-4000-8000-000000000003"
        )
        rendered = render_document(
            shared, list(self.validator.priority_policy.order)
        )["work.md"]
        self.assertEqual(rendered.content.count("Shared dependency"), 2)
        self.assertNotIn("## Should\n\n- [ ] Shared dependency", rendered.content)

    def test_dependency_is_root_in_category_without_its_parent(self) -> None:
        split = document()
        split["categories"].append({"id": "learning", "display_name": "Learning"})
        split["category_memberships"][0]["tasks"] = [
            "00000000-0000-4000-8000-000000000001"
        ]
        split["category_memberships"].append({
            "category": "learning",
            "tasks": ["00000000-0000-4000-8000-000000000002"],
        })
        rendered = render_document(
            split, list(self.validator.priority_policy.order)
        )
        self.assertIn("    - [ ] Shared dependency", rendered["work.md"].content)
        self.assertIn("## Should\n\n- [ ] Shared dependency", rendered["learning.md"].content)

    def test_renders_readable_due_date_without_metadata_comment(self) -> None:
        content = render_document(
            document(), list(self.validator.priority_policy.order)
        )["work.md"].content
        self.assertNotIn("<!--", content)
        self.assertNotIn("due-kind:", content)
        self.assertIn("Due: January 5, 2042 at 9:30 AM — Hard deadline.", content)

    def test_cli_requires_explicit_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-render-") as temporary:
            root = Path(temporary)
            source = root / "todo.json"
            source.write_text(json.dumps(document()))
            first = subprocess.run(
                [str(ROOT / "bin" / "todo"), "view", "render", str(source), "--output-dir", str(root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [str(ROOT / "bin" / "todo"), "view", "render", str(source), "--output-dir", str(root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            replaced = subprocess.run(
                [str(ROOT / "bin" / "todo"), "view", "render", str(source), "--output-dir", str(root), "--replace"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(replaced.returncode, 0, replaced.stderr)

    def test_combined_rendering_to_file_and_stdout(self) -> None:
        expanded = document()
        expanded["categories"].append({"id": "health", "display_name": "Health"})
        expanded["category_memberships"].append({"category": "health", "tasks": []})
        rendered = render_document(expanded, list(self.validator.priority_policy.order))
        combined = combine_rendered(rendered)
        self.assertIn("# Work — 2042-01-02", combined)
        self.assertIn("\n---\n\n# Health — 2042-01-02", combined)
        with tempfile.TemporaryDirectory(prefix="todo-render-combined-") as temporary:
            root = Path(temporary)
            source = root / "todo.json"
            output = root / "combined" / "todo.md"
            source.write_text(json.dumps(expanded))
            written = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "view", "render",
                    str(source),
                    "--output", str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            stdout = subprocess.run(
                [str(ROOT / "bin" / "todo"), "view", "render", str(source)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertEqual(output.read_text(), combined)
            self.assertEqual(stdout.returncode, 0, stdout.stderr)
            self.assertEqual(stdout.stdout, combined)


if __name__ == "__main__":
    unittest.main()

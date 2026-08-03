#!/usr/bin/env python3
"""Tests for incremental, atomic canonical task addition."""

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

from todo_add import add_task
from todo_ids import TaskIdSource, is_canonical_task_id
from todo_model import TodoList
from todo_schema import CanonicalSchemaBundle


DEPENDENCY_ID = "00000000-0000-4000-8000-000000000001"
ADDED_ID = "00000000-0000-4000-8000-000000000002"


def document() -> TodoList:
    return cast(
        TodoList,
        {
            "date": "2042-01-02",
            "tasks": [
                {
                    "id": DEPENDENCY_ID,
                    "name": "Existing dependency",
                    "priority": "should",
                    "completed": False,
                    "dependencies": [],
                }
            ],
            "categories": [{"id": "work", "display_name": "Work"}],
            "category_memberships": [
                {"category": "work", "tasks": [DEPENDENCY_ID]}
            ],
        },
    )


class AddTodoTest(unittest.TestCase):
    bundle: ClassVar[CanonicalSchemaBundle]

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = CanonicalSchemaBundle(ROOT / "schema")

    def test_core_retries_collision_and_adds_incrementally(self) -> None:
        values = iter([DEPENDENCY_ID, ADDED_ID])
        added = add_task(
            document(),
            name="New task",
            category_selectors=["work"],
            priority_policy=self.bundle.priority_policy,
            priority="must",
            dependency_selectors=["Existing dependency"],
            ids=TaskIdSource(lambda: next(values)),
        )
        self.assertEqual(added.task["id"], ADDED_ID)
        self.assertEqual(added.task["dependencies"], [DEPENDENCY_ID])
        self.assertEqual(
            added.document["category_memberships"][0]["tasks"],
            [DEPENDENCY_ID, ADDED_ID],
        )

    def test_cli_defaults_to_cwd_todo_and_does_not_render(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-add-") as temporary:
            root = Path(temporary)
            path = root / "todo.json"
            view = root / "work.md"
            path.write_text(json.dumps(document(), indent=2) + "\n")
            view.write_text("unchanged\n")
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "add-todo"),
                    "New task",
                    "--category",
                    "work",
                    "--priority",
                    "must",
                    "--depends-on",
                    "Existing dependency",
                    "--description",
                    "Details",
                    "--due",
                    "2042-02-03",
                    "--due-time",
                    "09:30",
                    "--deadline-kind",
                    "hard",
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(path.read_text())
            task = updated["tasks"][-1]
            self.assertTrue(is_canonical_task_id(task["id"]))
            self.assertEqual(task["dependencies"], [DEPENDENCY_ID])
            self.assertEqual(task["due"]["time"], "09:30")
            self.assertEqual(view.read_text(), "unchanged\n")
            self.assertEqual(result.stdout, "")

    def test_error_preserves_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-add-") as temporary:
            path = Path(temporary) / "todo.json"
            path.write_text(json.dumps(document(), separators=(",", ":")))
            before = path.read_bytes()
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "add-todo"),
                    "Invalid task",
                    "--output",
                    str(path),
                    "--category",
                    "work",
                    "--priority",
                    "could",
                    "--depends-on",
                    "Existing dependency",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("higher priority", result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_priority_help_comes_from_schema_policy(self) -> None:
        result = subprocess.run(
            [str(ROOT / "bin" / "add-todo"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        choices = "{" + ",".join(self.bundle.priority_policy.order) + "}"
        self.assertIn(choices, result.stdout)


if __name__ == "__main__":
    unittest.main()

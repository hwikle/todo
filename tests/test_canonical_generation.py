#!/usr/bin/env python3
"""Tests for scheduler-independent canonical daily generation."""

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

from todo_generation import generate_document
from todo_model import TodoList
from todo_validation import CanonicalTodoValidator


def previous_document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "name": "Incomplete parent",
                "priority": "must",
                "completed": False,
                "dependencies": ["00000000-0000-4000-8000-000000000002", "00000000-0000-4000-8000-000000000003"],
            },
            {
                "id": "00000000-0000-4000-8000-000000000002",
                "name": "Incomplete dependency",
                "priority": "should",
                "completed": False,
                "dependencies": [],
            },
            {
                "id": "00000000-0000-4000-8000-000000000003",
                "name": "Completed dependency",
                "priority": "could",
                "completed": True,
                "dependencies": [],
            },
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [
            {
                "category": "work",
                "tasks": ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002", "00000000-0000-4000-8000-000000000003"],
            }
        ],
    })


class CanonicalGenerationTest(unittest.TestCase):
    validator: ClassVar[CanonicalTodoValidator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = CanonicalTodoValidator(ROOT / "schema")

    def test_carries_only_incomplete_tasks_and_live_dependencies(self) -> None:
        generated = generate_document(
            "2042-01-03",
            previous_document(),
            [{"id": "health", "display_name": "Health"}],
        )
        self.assertEqual([task["id"] for task in generated["tasks"]], [
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
        ])
        self.assertEqual(generated["tasks"][0]["dependencies"], ["00000000-0000-4000-8000-000000000002"])
        self.assertEqual(
            generated["category_memberships"],
            [
                {"category": "work", "tasks": ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]},
                {"category": "health", "tasks": []},
            ],
        )
        self.assertFalse(any(issue.severity == "error" for issue in self.validator.validate(generated)))

    def test_empty_first_day_uses_explicit_categories(self) -> None:
        generated = generate_document(
            "2042-01-03",
            None,
            [{"id": "work", "display_name": "Work"}],
        )
        self.assertEqual(generated["tasks"], [])
        self.assertEqual(generated["categories"], [{"id": "work", "display_name": "Work"}])

    def test_cli_generation_defaults_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-") as temporary:
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "list", "create",
                    "--date",
                    "2042-01-03",
                    "--category", "work=Work",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["date"], "2042-01-03")
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_cli_accepts_explicit_previous_and_output_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-paths-") as temporary:
            root = Path(temporary)
            previous = root / "input" / "prior.json"
            output = root / "custom" / "generated.json"
            previous.parent.mkdir()
            previous.write_text(json.dumps(previous_document()))
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "list", "create",
                    "--date",
                    "2042-01-03",
                    "--previous",
                    str(previous),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["date"], "2042-01-03")
            self.assertEqual(list(output.parent.glob("*.md")), [])

    def test_explicit_previous_must_predate_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-date-") as temporary:
            root = Path(temporary)
            previous = root / "prior.json"
            previous.write_text(json.dumps(previous_document()))
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "list", "create",
                    "--date",
                    "2042-01-02",
                    "--previous",
                    str(previous),
                    "--output",
                    str(root / "generated.json"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("must predate", result.stderr)


if __name__ == "__main__":
    unittest.main()

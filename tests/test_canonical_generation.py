#!/usr/bin/env python3
"""Tests for scheduler-independent canonical daily generation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_generation import generate_document, latest_previous_list
from todo_validation import CanonicalTodoValidator


def previous_document() -> dict[str, object]:
    return {
        "date": "2042-01-02",
        "tasks": [
            {
                "id": "aaaaaaaaaaaa",
                "name": "Incomplete parent",
                "priority": "must",
                "completed": False,
                "dependencies": ["bbbbbbbbbbbb", "cccccccccccc"],
            },
            {
                "id": "bbbbbbbbbbbb",
                "name": "Incomplete dependency",
                "priority": "should",
                "completed": False,
                "dependencies": [],
            },
            {
                "id": "cccccccccccc",
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
                "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"],
            }
        ],
    }


class CanonicalGenerationTest(unittest.TestCase):
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
            "aaaaaaaaaaaa",
            "bbbbbbbbbbbb",
        ])
        self.assertEqual(generated["tasks"][0]["dependencies"], ["bbbbbbbbbbbb"])
        self.assertEqual(
            generated["category_memberships"],
            [
                {"category": "work", "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]},
                {"category": "health", "tasks": []},
            ],
        )
        self.assertFalse(any(issue.severity == "error" for issue in self.validator.validate(generated)))

    def test_empty_first_day_uses_configured_categories(self) -> None:
        generated = generate_document(
            "2042-01-03",
            None,
            [{"id": "work", "display_name": "Work"}],
        )
        self.assertEqual(generated["tasks"], [])
        self.assertEqual(generated["categories"], [{"id": "work", "display_name": "Work"}])

    def test_finds_latest_prior_canonical_list(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-") as temporary:
            root = Path(temporary)
            for date in ("2042-01-01", "2042-01-02"):
                path = root / date
                path.mkdir()
                (path / "todo.json").write_text("{}")
            self.assertEqual(
                latest_previous_list(root, "2042-01-03"),
                root / "2042-01-02" / "todo.json",
            )

    def test_cli_generation_is_independent_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-") as temporary:
            data_dir = Path(temporary) / "todos"
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "generate-todos"),
                    "--date",
                    "2042-01-03",
                    "--data-dir",
                    str(data_dir),
                    "--render",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            target = data_dir / "2042-01-03" / "todo.json"
            self.assertEqual(result.returncode, 0, result.stderr)
            before = target.read_text()
            second = subprocess.run(
                [
                    str(ROOT / "bin" / "generate-todos"),
                    "--date",
                    "2042-01-03",
                    "--data-dir",
                    str(data_dir),
                    "--render",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_text(), before)
            self.assertFalse((data_dir.parent / "launchd").exists())


if __name__ == "__main__":
    unittest.main()

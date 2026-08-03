#!/usr/bin/env python3
"""Tests for canonical UUIDv4 generation and atomic ID migration."""

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

from todo_ids import TaskIdSource, is_canonical_task_id, migrate_task_ids
from todo_model import TodoList
from todo_validation import CanonicalTodoValidator


def legacy_document() -> TodoList:
    return cast(
        TodoList,
        {
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
                    "name": "Dependency",
                    "priority": "should",
                    "completed": False,
                    "dependencies": [],
                },
            ],
            "categories": [{"id": "work", "display_name": "Work"}],
            "category_memberships": [
                {"category": "work", "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]}
            ],
        },
    )


class TaskIdTest(unittest.TestCase):
    def test_migrates_all_references(self) -> None:
        values = iter(
            [
                "00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-000000000002",
            ]
        )
        migrated = migrate_task_ids(legacy_document(), TaskIdSource(lambda: next(values)))
        parent, dependency = migrated["tasks"]
        self.assertEqual(parent["dependencies"], [dependency["id"]])
        self.assertEqual(
            migrated["category_memberships"][0]["tasks"],
            [parent["id"], dependency["id"]],
        )
        self.assertTrue(all(is_canonical_task_id(task["id"]) for task in migrated["tasks"]))
        self.assertEqual(CanonicalTodoValidator(ROOT / "schema").validate(migrated), [])

    def test_cli_error_preserves_original_bytes(self) -> None:
        document = legacy_document()
        document["tasks"][0]["dependencies"] = ["missing"]
        with tempfile.TemporaryDirectory(prefix="todo-id-migration-") as temporary:
            path = Path(temporary) / "todo.json"
            path.write_text(json.dumps(document, separators=(",", ":")))
            before = path.read_bytes()
            result = subprocess.run(
                [str(ROOT / "bin" / "migrate-task-ids"), str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

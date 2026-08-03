#!/usr/bin/env python3
"""Tests for canonical JSON schema and semantic validation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar, cast


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_model import Priority, Task, TodoList
from todo_validation import CanonicalTodoValidator, validate_completion_observations


def task(task_id: str, name: str, priority: Priority = "must", **overrides: object) -> Task:
    value = cast(Task, {
        "id": task_id,
        "name": name,
        "priority": priority,
        "completed": False,
        "dependencies": [],
    })
    cast(Any, value).update(overrides)
    return value


def valid_document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [
            task("aaaaaaaaaaaa", "Parent", dependencies=["bbbbbbbbbbbb"]),
            task("bbbbbbbbbbbb", "Dependency", priority="should"),
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [
            {"category": "work", "tasks": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]}
        ],
    })


class CanonicalValidationTest(unittest.TestCase):
    validator: ClassVar[CanonicalTodoValidator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = CanonicalTodoValidator(ROOT / "schema")

    def errors(self, document: TodoList) -> list[str]:
        return [issue.message for issue in self.validator.validate(document) if issue.severity == "error"]

    def warnings(self, document: TodoList) -> list[str]:
        return [issue.message for issue in self.validator.validate(document) if issue.severity == "warning"]

    def test_valid_document(self) -> None:
        self.assertEqual(self.validator.validate(valid_document()), [])

    def test_schema_and_calendar_errors(self) -> None:
        document = valid_document()
        document["tasks"][0]["due"] = {"year": 2042, "month": 2, "day": 30}
        document["tasks"][0]["deadline_kind"] = "hard"
        self.assertTrue(any("invalid calendar date" in item for item in self.errors(document)))

    def test_duplicate_and_ambiguous_task_ids(self) -> None:
        document = valid_document()
        document["tasks"].append(task("bbbbbbbbbbbb", "Duplicate"))
        messages = self.errors(document)
        self.assertTrue(any("duplicate task ID" in item for item in messages))
        self.assertTrue(any("ambiguous task ID" in item for item in messages))

    def test_unknown_membership_references(self) -> None:
        document = valid_document()
        document["category_memberships"][0] = {
            "category": "missing",
            "tasks": ["cccccccccccc"],
        }
        messages = self.errors(document)
        self.assertTrue(any("unknown category ID" in item for item in messages))
        self.assertTrue(any("unknown task ID" in item for item in messages))

    def test_self_dependency_and_cycle(self) -> None:
        document = valid_document()
        document["tasks"][0]["dependencies"] = ["aaaaaaaaaaaa"]
        self.assertTrue(any("depend on itself" in item for item in self.errors(document)))

        document = valid_document()
        document["tasks"][1]["dependencies"] = ["aaaaaaaaaaaa"]
        self.assertTrue(any("dependency cycle" in item for item in self.errors(document)))

    def test_completed_task_requires_completed_dependencies(self) -> None:
        document = valid_document()
        document["tasks"][0]["completed"] = True
        self.assertTrue(any("incomplete dependency" in item for item in self.errors(document)))

    def test_dependency_cannot_have_higher_priority(self) -> None:
        document = valid_document()
        document["tasks"][0]["priority"] = "could"
        document["tasks"][1]["priority"] = "must"
        self.assertTrue(any("higher than task priority" in item for item in self.errors(document)))

    def test_duplicate_membership_is_an_error(self) -> None:
        document = valid_document()
        document["category_memberships"].append(
            {"category": "work", "tasks": ["aaaaaaaaaaaa"]}
        )
        self.assertTrue(any("duplicate category/task membership" in item for item in self.errors(document)))

    def test_advisories_are_warnings(self) -> None:
        document = valid_document()
        document["tasks"][0].pop("priority")
        document["category_memberships"][0]["tasks"] = ["bbbbbbbbbbbb"]
        document["categories"].append({"id": "other", "display_name": "Work"})
        messages = self.warnings(document)
        self.assertTrue(any("no priority" in item for item in messages))
        self.assertTrue(any("no category" in item for item in messages))
        self.assertTrue(any("category is empty" in item for item in messages))
        self.assertTrue(any("duplicate category display name" in item for item in messages))

    def test_multiple_categories_is_a_warning(self) -> None:
        document = valid_document()
        document["categories"].append({"id": "other", "display_name": "Other"})
        document["category_memberships"].append(
            {"category": "other", "tasks": ["aaaaaaaaaaaa"]}
        )
        self.assertTrue(any("multiple categories" in item for item in self.warnings(document)))

    def test_conflicting_rendered_checkboxes_are_errors(self) -> None:
        issues = validate_completion_observations(
            [
                ("aaaaaaaaaaaa", False, "work.md:3"),
                ("aaaaaaaaaaaa", True, "work.md:9"),
            ]
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "error")

    def test_cli_strict_mode_promotes_warnings(self) -> None:
        document = valid_document()
        document["tasks"][0].pop("priority")
        with tempfile.TemporaryDirectory(prefix="todo-validation-") as temporary:
            path = Path(temporary) / "todo.json"
            path.write_text(json.dumps(document))
            relaxed = subprocess.run(
                [str(ROOT / "bin" / "validate-todos"), str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            strict = subprocess.run(
                [str(ROOT / "bin" / "validate-todos"), "--strict", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(relaxed.returncode, 0, relaxed.stderr)
        self.assertEqual(strict.returncode, 1, strict.stderr)
        self.assertIn("error (strict)", strict.stderr)


if __name__ == "__main__":
    unittest.main()

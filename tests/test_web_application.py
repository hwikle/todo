#!/usr/bin/env python3
"""Tests for revision-aware browser application operations."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar, cast


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_model import TodoList
from todo_schema import CanonicalSchemaBundle
from todo_web_application import RevisionConflict, TodoWebApplication, WebEditError


PARENT = "00000000-0000-4000-8000-000000000001"
SIBLING = "00000000-0000-4000-8000-000000000002"


def document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [
            {"id": PARENT, "name": "Parent", "priority": "must", "completed": False, "dependencies": []},
            {"id": SIBLING, "name": "Sibling", "priority": "should", "completed": False, "dependencies": []},
        ],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [{"category": "work", "tasks": [PARENT, SIBLING]}],
    })


class WebApplicationTest(unittest.TestCase):
    bundle: ClassVar[CanonicalSchemaBundle]

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = CanonicalSchemaBundle(ROOT / "schema")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="todo-web-")
        self.path = Path(self.temporary.name) / "todo.json"
        self.path.write_text(json.dumps(document(), indent=2) + "\n")
        self.service = TodoWebApplication(self.path, self.bundle)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_adds_and_positions_a_task_atomically(self) -> None:
        initial = self.service.load()
        result = self.service.add_task(
            initial.revision,
            name="Inserted",
            categories=("work",),
            priority="should",
            parent_id=None,
            after_id=PARENT,
            context_category="work",
        )
        added = next(task for task in result.document["tasks"] if task["name"] == "Inserted")
        self.assertEqual(
            result.document["category_memberships"][0]["tasks"],
            [PARENT, added["id"], SIBLING],
        )
        self.assertEqual(json.loads(self.path.read_text()), result.document)

    def test_rejects_stale_revision_without_changing_file(self) -> None:
        initial = self.service.load()
        self.path.write_text(self.path.read_text() + " ")
        before = self.path.read_bytes()
        with self.assertRaises(RevisionConflict):
            self.service.set_completed(initial.revision, PARENT, True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_invalid_nesting_without_changing_file(self) -> None:
        initial = self.service.load()
        before = self.path.read_bytes()
        with self.assertRaises(WebEditError):
            self.service.move_task(
                initial.revision,
                PARENT,
                old_parent_id=None,
                new_parent_id=SIBLING,
                after_id=None,
                context_category="work",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_edits_optional_fields_and_categories(self) -> None:
        initial = self.service.load()
        result = self.service.edit_task(
            initial.revision,
            PARENT,
            description_supplied=True,
            description="Details",
            priority_supplied=True,
            priority=None,
            categories=("work",),
        )
        task = result.document["tasks"][0]
        self.assertEqual(task["description"], "Details")
        self.assertNotIn("priority", task)


if __name__ == "__main__":
    unittest.main()

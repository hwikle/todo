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
from todo_web_application import (
    RevisionConflict,
    TaskRequiredError,
    TodoWebApplication,
    WebEditError,
)


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
        added = next(task for task in result.snapshot.document["tasks"] if task["id"] == result.task_id)
        self.assertEqual(
            result.snapshot.document["category_memberships"][0]["tasks"],
            [PARENT, added["id"], SIBLING],
        )
        self.assertEqual(json.loads(self.path.read_text()), result.snapshot.document)

    def test_creates_a_missing_list_once(self) -> None:
        missing = Path(self.temporary.name) / "missing" / "todo.json"
        service = TodoWebApplication(
            missing,
            self.bundle,
            [{"id": "work", "display_name": "Work"}],
        )
        self.assertFalse(service.exists())
        created = service.create("2042-02-03")
        self.assertEqual(created.document["date"], "2042-02-03")
        self.assertEqual(created.document["categories"][0]["id"], "work")
        with self.assertRaises(RevisionConflict):
            service.create("2042-02-03")

    def test_identical_names_remain_independent_by_id(self) -> None:
        initial = self.service.load()
        added = self.service.add_task(
            initial.revision,
            name="Parent",
            categories=("work",),
            priority="should",
            parent_id=None,
            after_id=PARENT,
            context_category="work",
        )
        edited = self.service.edit_task(
            added.snapshot.revision,
            added.task_id,
            name="Only this task changed",
        )
        self.assertEqual(edited.document["tasks"][0]["name"], "Parent")
        self.assertEqual(
            next(task for task in edited.document["tasks"] if task["id"] == added.task_id)["name"],
            "Only this task changed",
        )
        removed = self.service.remove_task(edited.revision, added.task_id)
        self.assertEqual([task["id"] for task in removed.document["tasks"]], [PARENT, SIBLING])

    def test_deletion_reports_dependent_task_details(self) -> None:
        initial = self.service.load()
        nested = self.service.move_task(
            initial.revision,
            SIBLING,
            old_parent_id=None,
            new_parent_id=PARENT,
            after_id=None,
            context_category="work",
        )
        with self.assertRaises(TaskRequiredError) as raised:
            self.service.remove_task(nested.revision, SIBLING)
        self.assertEqual(raised.exception.blockers[0]["id"], PARENT)

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

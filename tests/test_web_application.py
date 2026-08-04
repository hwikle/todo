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
    RepairRequiredError,
    TodoStructureError,
    RevisionConflict,
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
            {"id": SIBLING, "name": "Sibling", "priority": "must", "completed": False, "dependencies": []},
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
        )
        self.assertFalse(service.exists())
        created = service.create(
            "2042-02-03", [{"id": "work", "display_name": "Work"}]
        )
        self.assertEqual(created.document["date"], "2042-02-03")
        self.assertEqual(created.document["categories"][0]["id"], "work")
        with self.assertRaises(RevisionConflict):
            service.create("2042-02-03", [{"id": "work", "display_name": "Work"}])

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

    def test_deletion_removes_every_dependency_reference(self) -> None:
        initial = self.service.load()
        nested = self.service.move_task(
            initial.revision,
            SIBLING,
            old_parent_id=None,
            new_parent_id=PARENT,
            after_id=None,
            before_id=None,
            context_category="work",
        )
        third = self.service.add_task(
            nested.revision,
            name="Second parent",
            categories=("work",),
            priority="must",
            parent_id=None,
            after_id=PARENT,
            context_category="work",
        )
        shared = self.service.move_task(
            third.snapshot.revision,
            SIBLING,
            old_parent_id=PARENT,
            new_parent_id=third.task_id,
            after_id=None,
            before_id=None,
            context_category="work",
        )
        first_parent = next(task for task in shared.document["tasks"] if task["id"] == PARENT)
        first_parent["dependencies"].append(SIBLING)
        self.path.write_text(json.dumps(shared.document, indent=2) + "\n")
        shared = self.service.load()
        removed = self.service.remove_task(shared.revision, SIBLING)
        self.assertEqual(removed.document["tasks"][0]["dependencies"], [])
        self.assertTrue(all(SIBLING not in task["dependencies"] for task in removed.document["tasks"]))
        self.assertEqual(len(removed.document["tasks"]), 2)

    def test_rejects_stale_revision_without_changing_file(self) -> None:
        initial = self.service.load()
        self.path.write_text(self.path.read_text() + " ")
        before = self.path.read_bytes()
        with self.assertRaises(RevisionConflict):
            self.service.set_completed(initial.revision, PARENT, True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_invalid_nesting_without_changing_file(self) -> None:
        initial = self.service.load()
        lowered = self.service.edit_task(
            initial.revision,
            SIBLING,
            priority_supplied=True,
            priority="should",
        )
        before = self.path.read_bytes()
        with self.assertRaises(WebEditError):
            self.service.move_task(
                lowered.revision,
                SIBLING,
                old_parent_id=None,
                new_parent_id=PARENT,
                after_id=None,
                before_id=None,
                context_category="work",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_repair_mode_stages_invalid_edits_until_the_document_is_valid(self) -> None:
        invalid = document()
        invalid["tasks"][0]["dependencies"] = [SIBLING]
        invalid["tasks"][1]["priority"] = "should"
        original = json.dumps(invalid, indent=2) + "\n"
        self.path.write_text(original)

        with self.assertRaises(RepairRequiredError):
            TodoWebApplication(self.path, self.bundle).load()

        service = TodoWebApplication(self.path, self.bundle, repair=True)
        opened = service.load()
        self.assertFalse(opened.saved)
        self.assertTrue(any("less urgent" in issue.message for issue in opened.issues))

        still_invalid = service.edit_task(opened.revision, PARENT, name="Renamed parent")
        self.assertFalse(still_invalid.saved)
        self.assertEqual(self.path.read_text(), original)

        repaired = service.edit_task(
            still_invalid.revision,
            SIBLING,
            priority_supplied=True,
            priority="must",
        )
        self.assertTrue(repaired.saved)
        self.assertFalse(any(issue.severity == "error" for issue in repaired.issues))
        self.assertEqual(json.loads(self.path.read_text())["tasks"][0]["name"], "Renamed parent")

    def test_structure_error_names_the_invalid_task(self) -> None:
        invalid = document()
        invalid["tasks"][0]["completed"] = "no"  # type: ignore[typeddict-item]
        self.path.write_text(json.dumps(invalid))
        with self.assertRaises(TodoStructureError) as raised:
            TodoWebApplication(self.path, self.bundle, repair=True).load()
        self.assertIn('Task "Parent"', str(raised.exception))
        self.assertIn("$.tasks[0].completed", str(raised.exception))

    def test_malformed_json_reports_line_and_column(self) -> None:
        self.path.write_text('{\n  "tasks": [\n}')
        with self.assertRaises(TodoStructureError) as raised:
            TodoWebApplication(self.path, self.bundle, repair=True).load()
        self.assertIn("line 3, column 1", str(raised.exception))

    def test_repair_mode_refuses_to_partially_render_unknown_tasks(self) -> None:
        invalid = document()
        invalid["tasks"][0]["dependencies"] = ["00000000-0000-4000-8000-000000000099"]
        self.path.write_text(json.dumps(invalid))
        with self.assertRaises(TodoStructureError) as raised:
            TodoWebApplication(self.path, self.bundle, repair=True).load()
        self.assertIn("unknown task ID", str(raised.exception))

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

        cleared = self.service.edit_task(
            result.revision,
            PARENT,
            description_supplied=True,
            description=None,
        )
        self.assertNotIn("description", cleared.document["tasks"][0])

    def test_reorders_and_detaches_tasks_by_identity(self) -> None:
        initial = self.service.load()
        reordered = self.service.reorder_task(
            initial.revision, SIBLING, parent_id=None, category_id="work", offset=-1
        )
        self.assertEqual(
            reordered.document["category_memberships"][0]["tasks"],
            [SIBLING, PARENT],
        )
        nested = self.service.move_task(
            reordered.revision,
            SIBLING,
            old_parent_id=None,
            new_parent_id=PARENT,
            after_id=None,
            before_id=None,
            context_category="work",
        )
        self.assertEqual(nested.document["tasks"][0]["dependencies"], [SIBLING])
        detached = self.service.detach_task(nested.revision, SIBLING, PARENT)
        self.assertEqual(detached.document["tasks"][0]["dependencies"], [])

    def test_move_can_place_a_task_before_the_first_sibling(self) -> None:
        initial = self.service.load()
        moved = self.service.move_task(
            initial.revision,
            SIBLING,
            old_parent_id=None,
            new_parent_id=None,
            after_id=None,
            before_id=PARENT,
            context_category="work",
        )
        self.assertEqual(
            moved.document["category_memberships"][0]["tasks"],
            [SIBLING, PARENT],
        )

        with self.assertRaises(WebEditError):
            self.service.move_task(
                moved.revision,
                SIBLING,
                old_parent_id=None,
                new_parent_id=None,
                after_id=PARENT,
                before_id=PARENT,
                context_category="work",
            )

    def test_categories_are_managed_inside_the_list(self) -> None:
        initial = self.service.load()
        added = self.service.add_category(initial.revision, "learning", "Learning")
        self.assertEqual([item["id"] for item in added.document["categories"]], ["work", "learning"])
        renamed = self.service.rename_category(added.revision, "learning", "Study")
        self.assertEqual(renamed.document["categories"][1]["display_name"], "Study")
        moved = self.service.move_category(renamed.revision, "learning", -1)
        self.assertEqual([item["id"] for item in moved.document["categories"]], ["learning", "work"])
        removed = self.service.remove_category(moved.revision, "learning")
        self.assertEqual([item["id"] for item in removed.document["categories"]], ["work"])
        with self.assertRaises(WebEditError):
            self.service.remove_category(removed.revision, "work")


if __name__ == "__main__":
    unittest.main()

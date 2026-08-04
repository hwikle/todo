#!/usr/bin/env python3
"""Tests for the local browser HTTP adapter."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar, cast

from flask.testing import FlaskClient


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_model import TodoList
from todo_schema import CanonicalSchemaBundle
from todo_web import create_app


TASK_ID = "00000000-0000-4000-8000-000000000001"


def document() -> TodoList:
    return cast(TodoList, {
        "date": "2042-01-02",
        "tasks": [{"id": TASK_ID, "name": "Task", "priority": "should", "completed": False, "dependencies": []}],
        "categories": [{"id": "work", "display_name": "Work"}],
        "category_memberships": [{"category": "work", "tasks": [TASK_ID]}],
    })


class WebAdapterTest(unittest.TestCase):
    bundle: ClassVar[CanonicalSchemaBundle]

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = CanonicalSchemaBundle(ROOT / "schema")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="todo-http-")
        self.path = Path(self.temporary.name) / "todo.json"
        self.path.write_text(json.dumps(document(), indent=2) + "\n")
        app = create_app(self.path, self.bundle)
        app.config.update(TESTING=True)
        self.client: FlaskClient = app.test_client()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def snapshot(self) -> dict[str, object]:
        response = self.client.get("/api/todo")
        self.assertEqual(response.status_code, 200)
        return cast(dict[str, object], response.get_json())

    def test_page_is_an_editable_checklist(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="checklist"', response.data)
        self.assertIn(b"todo.js", response.data)

    def test_browser_assets_keep_context_menus_clickable_and_drag_feedback_stationary(self) -> None:
        script = (ROOT / "static" / "todo.js").read_text()
        stylesheet = (ROOT / "static" / "todo.css").read_text()
        self.assertIn('dropIndicator.className = "drop-indicator"', script)
        self.assertNotIn("outdent-drop", script)
        self.assertIn(".task-heading", stylesheet)
        self.assertIn(".drop-indicator { position: absolute", stylesheet)
        self.assertNotIn(".task-row.contextual { opacity", stylesheet)

    def test_missing_file_can_be_created_in_the_browser(self) -> None:
        missing = Path(self.temporary.name) / "missing" / "todo.json"
        app = create_app(missing, self.bundle)
        app.config.update(TESTING=True)
        client = app.test_client()
        initial = client.get("/api/todo")
        self.assertEqual(initial.status_code, 200)
        self.assertFalse(initial.get_json()["exists"])
        self.assertFalse(missing.exists())
        created = client.post(
            "/api/todo",
            json={
                "date": "2042-03-04",
                "categories": [{"id": "work", "display_name": "Work"}],
            },
        )
        self.assertEqual(created.status_code, 200, created.get_json())
        self.assertTrue(created.get_json()["exists"])
        self.assertEqual(json.loads(missing.read_text())["date"], "2042-03-04")

    def test_creation_race_preserves_the_other_file(self) -> None:
        missing = Path(self.temporary.name) / "race.json"
        app = create_app(missing, self.bundle)
        app.config.update(TESTING=True)
        client = app.test_client()
        missing.write_text(json.dumps(document(), indent=2) + "\n")
        before = missing.read_bytes()
        response = client.post(
            "/api/todo",
            json={
                "date": "2042-03-04",
                "categories": [{"id": "work", "display_name": "Work"}],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(missing.read_bytes(), before)

    def test_get_includes_document_revision_and_schema_priorities(self) -> None:
        payload = self.snapshot()
        self.assertEqual(payload["document"], document())
        self.assertEqual(payload["priorities"], ["must", "should", "could"])
        self.assertIsInstance(payload["revision"], str)
        self.assertTrue(payload["exists"])

    def test_add_returns_the_exact_created_id_for_duplicate_names(self) -> None:
        payload = self.snapshot()
        response = self.client.post(
            "/api/tasks",
            json={
                "revision": payload["revision"],
                "name": "Task",
                "categories": ["work"],
                "priority": "should",
                "parent_id": None,
                "after_id": TASK_ID,
                "context_category": "work",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        matching_ids = [task["id"] for task in result["document"]["tasks"] if task["name"] == "Task"]
        self.assertEqual(len(matching_ids), 2)
        self.assertIn(result["created_id"], matching_ids)
        self.assertNotEqual(result["created_id"], TASK_ID)
        removed = self.client.delete(
            f"/api/tasks/{result['created_id']}",
            json={"revision": result["revision"]},
        )
        self.assertEqual(removed.status_code, 200, removed.get_json())
        remaining = removed.get_json()["document"]["tasks"]
        self.assertEqual([(task["id"], task["name"]) for task in remaining], [(TASK_ID, "Task")])

    def test_delete_reports_the_exact_parent_blocker(self) -> None:
        payload = self.snapshot()
        added = self.client.post(
            "/api/tasks",
            json={
                "revision": payload["revision"],
                "name": "Task",
                "categories": ["work"],
                "priority": "could",
                "parent_id": TASK_ID,
                "after_id": None,
                "context_category": "work",
            },
        ).get_json()
        response = self.client.delete(
            f"/api/tasks/{added['created_id']}",
            json={"revision": added["revision"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "task_required")
        self.assertEqual(response.get_json()["blockers"][0]["id"], TASK_ID)

    def test_patch_autosaves_to_the_explicit_file(self) -> None:
        payload = self.snapshot()
        response = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": payload["revision"], "name": "Renamed"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(json.loads(self.path.read_text())["tasks"][0]["name"], "Renamed")

    def test_empty_description_clears_the_canonical_field(self) -> None:
        payload = self.snapshot()
        described = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": payload["revision"], "description": "Details"},
        ).get_json()
        cleared = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": described["revision"], "description": None},
        )
        self.assertEqual(cleared.status_code, 200, cleared.get_json())
        self.assertNotIn("description", cleared.get_json()["document"]["tasks"][0])
        self.assertNotIn("description", json.loads(self.path.read_text())["tasks"][0])

    def test_stale_edit_returns_conflict(self) -> None:
        payload = self.snapshot()
        self.path.write_text(self.path.read_text() + " ")
        response = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": payload["revision"], "name": "Renamed"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "revision_conflict")

    def test_category_reorder_and_removal_routes(self) -> None:
        payload = self.snapshot()
        added = self.client.post(
            "/api/categories",
            json={"revision": payload["revision"], "id": "learning", "display_name": "Learning"},
        ).get_json()
        moved = self.client.patch(
            "/api/categories/learning",
            json={"revision": added["revision"], "offset": -1},
        ).get_json()
        self.assertEqual(moved["document"]["categories"][0]["id"], "learning")
        removed = self.client.delete(
            "/api/categories/learning", json={"revision": moved["revision"]}
        )
        self.assertEqual(removed.status_code, 200, removed.get_json())

    def test_move_route_accepts_before_placement(self) -> None:
        payload = self.snapshot()
        added = self.client.post(
            "/api/tasks",
            json={
                "revision": payload["revision"],
                "name": "Second",
                "categories": ["work"],
                "priority": "should",
                "parent_id": None,
                "after_id": TASK_ID,
                "context_category": "work",
            },
        ).get_json()
        moved = self.client.post(
            f"/api/tasks/{added['created_id']}/move",
            json={
                "revision": added["revision"],
                "old_parent_id": None,
                "new_parent_id": None,
                "after_id": None,
                "before_id": TASK_ID,
                "context_category": "work",
            },
        )
        self.assertEqual(moved.status_code, 200, moved.get_json())
        self.assertEqual(
            moved.get_json()["document"]["category_memberships"][0]["tasks"],
            [added["created_id"], TASK_ID],
        )


if __name__ == "__main__":
    unittest.main()

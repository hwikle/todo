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

    def test_missing_file_fails_before_the_server_starts(self) -> None:
        with self.assertRaises(FileNotFoundError):
            create_app(Path(self.temporary.name) / "missing.json", self.bundle)

    def test_get_includes_document_revision_and_schema_priorities(self) -> None:
        payload = self.snapshot()
        self.assertEqual(payload["document"], document())
        self.assertEqual(payload["priorities"], ["must", "should", "could"])
        self.assertIsInstance(payload["revision"], str)

    def test_patch_autosaves_to_the_explicit_file(self) -> None:
        payload = self.snapshot()
        response = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": payload["revision"], "name": "Renamed"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(json.loads(self.path.read_text())["tasks"][0]["name"], "Renamed")

    def test_stale_edit_returns_conflict(self) -> None:
        payload = self.snapshot()
        self.path.write_text(self.path.read_text() + " ")
        response = self.client.patch(
            f"/api/tasks/{TASK_ID}",
            json={"revision": payload["revision"], "name": "Renamed"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "revision_conflict")


if __name__ == "__main__":
    unittest.main()

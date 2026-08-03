#!/usr/bin/env python3
"""Tests for deterministic Markdown-to-canonical-JSON conversion."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_markdown import MarkdownConversionError
from todo_markdown_io import convert_daily_directory
from todo_validation import CanonicalTodoValidator


class Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"{self.value:012x}"


class MarkdownConversionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="todo-conversion-")
        self.day = Path(self.temporary.name) / "2042-01-02"
        self.day.mkdir()
        self.validator = CanonicalTodoValidator(ROOT / "schema")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.day / name).write_text(content)

    def test_converts_nested_tasks_and_ignores_legacy_ids(self) -> None:
        self.write(
            "work.md",
            """# Work — 2042-01-02

## Must

- [ ] Parent <!-- task:aaaaaaaaaaaa due:2042-01-05 time:09:30 due-kind:hard -->
    Due: January 5, 2042 at 9:30 AM — Hard deadline.
    Parent description.
    - [x] Child <!-- task:bbbbbbbbbbbb -->
        Child description.

## Should

## Could
""",
        )
        document = convert_daily_directory(
            self.day, list(self.validator.priority_policy.order), Ids()
        )
        self.assertEqual(self.validator.validate(document), [])
        parent, child = document["tasks"]
        self.assertEqual(parent["id"], "000000000001")
        self.assertEqual(child["id"], "000000000002")
        self.assertEqual(parent["dependencies"], [child["id"]])
        self.assertEqual(parent["description"], "Parent description.")
        self.assertEqual(child["description"], "Child description.")
        self.assertEqual(child["priority"], "must")
        self.assertEqual(
            parent["due"],
            {"year": 2042, "month": 1, "day": 5, "time": "09:30"},
        )
        self.assertEqual(parent["deadline_kind"], "hard")
        self.assertEqual(
            document["category_memberships"][0]["tasks"],
            [parent["id"], child["id"]],
        )

    def test_identical_names_remain_distinct(self) -> None:
        self.write(
            "work.md",
            """# Work — 2042-01-02

## Must

- [ ] Same name
- [ ] Same name
""",
        )
        document = convert_daily_directory(
            self.day, list(self.validator.priority_policy.order), Ids()
        )
        self.assertEqual(len(document["tasks"]), 2)
        self.assertNotEqual(document["tasks"][0]["id"], document["tasks"][1]["id"])

    def test_rejects_skipped_indentation(self) -> None:
        self.write(
            "work.md",
            """# Work — 2042-01-02

## Must

- [ ] Parent
        - [ ] Child
""",
        )
        with self.assertRaisesRegex(MarkdownConversionError, "skips a nesting level"):
            convert_daily_directory(self.day, list(self.validator.priority_policy.order), Ids())

    def test_rejects_mismatched_date(self) -> None:
        self.write("work.md", "# Work — 2042-01-03\n\n## Must\n")
        with self.assertRaisesRegex(MarkdownConversionError, "does not match"):
            convert_daily_directory(self.day, list(self.validator.priority_policy.order), Ids())

    def test_cli_refuses_to_overwrite(self) -> None:
        self.write("work.md", "# Work — 2042-01-02\n\n## Must\n\n- [ ] Task\n")
        output = self.day / "todo.json"
        first = subprocess.run(
            [str(ROOT / "bin" / "convert-todos"), str(self.day)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        second = subprocess.run(
            [str(ROOT / "bin" / "convert-todos"), str(self.day)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 2)
        self.assertIn("refusing to overwrite", second.stderr)
        self.assertEqual(json.loads(output.read_text())["date"], "2042-01-02")

    def test_stdout_does_not_write(self) -> None:
        self.write("work.md", "# Work — 2042-01-02\n\n## Must\n\n- [ ] Task\n")
        result = subprocess.run(
            [str(ROOT / "bin" / "convert-todos"), "--stdout", str(self.day)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["date"], "2042-01-02")
        self.assertFalse((self.day / "todo.json").exists())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for direct Markdown-to-JSON-Schema validation."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class SchemaValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="todo-schema-test-")
        self.repo = Path(self.temporary.name) / "todo"
        self.repo.mkdir()
        for name in ("bin", "config", "schema", "backlog"):
            shutil.copytree(ROOT / name, self.repo / name)
        self.invoke("bin/create-daily-todo", "--date", "2042-01-02")
        self.invoke(
            "bin/todo", "add", "--date", "2042-01-02", "--type", "work",
            "--priority", "Must", "--due-date", "2042-01-05", "--due-time",
            "09:30", "--due-kind", "hard", "Schema-backed task",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.repo / arguments[0]), *arguments[1:]],
            cwd=self.repo,
            check=check,
            capture_output=True,
            text=True,
        )

    def test_standalone_validator_accepts_valid_markdown(self) -> None:
        result = self.invoke("bin/validate-todos")
        self.assertIn("Validated", result.stdout)

    def test_validator_reads_the_schema_file(self) -> None:
        path = self.repo / "schema" / "task.schema.json"
        schema = json.loads(path.read_text())
        schema["$defs"]["task"]["required"].append("schemaProbe")
        path.write_text(json.dumps(schema, indent=2) + "\n")
        result = self.invoke("bin/validate-todos", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema requires fields", result.stderr)

    def test_generation_validates_due_schema_before_writing(self) -> None:
        path = self.repo / "schema" / "due.schema.json"
        schema = json.loads(path.read_text())
        schema["required"].append("schemaProbe")
        path.write_text(json.dumps(schema, indent=2) + "\n")
        result = self.invoke(
            "bin/create-daily-todo", "--date", "2042-01-03", check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema requires fields", result.stderr)
        self.assertFalse((self.repo / "todos" / "2042-01-03").exists())

    def test_fix_assigns_id_before_schema_validation(self) -> None:
        path = self.repo / "todos" / "2042-01-02" / "work.md"
        content = path.read_text().replace(
            "## Could\n", "## Could\n\n- [ ] Manually entered task\n"
        )
        path.write_text(content)
        failed = self.invoke("bin/validate-todos", check=False)
        self.assertEqual(failed.returncode, 2)
        self.assertIn("schema requires string", failed.stderr)
        self.invoke("bin/validate-todos", "--fix")
        self.assertRegex(path.read_text(), r"Manually entered task <!-- task:[0-9a-f]{12} -->")


if __name__ == "__main__":
    unittest.main()

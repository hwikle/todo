#!/usr/bin/env python3
"""Regression test: list creation has no scheduler or rendering dependency."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class IndependentGenerationTest(unittest.TestCase):
    def test_list_create_generates_only_canonical_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-entrypoint-") as temporary:
            output = Path(temporary) / "todo.json"
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "list", "create",
                    "--date",
                    "2042-01-02",
                    "--output", str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertEqual(list(output.parent.glob("*.md")), [])
            self.assertFalse((Path(temporary) / "launchd").exists())

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-entrypoint-") as temporary:
            target = Path(temporary) / "todo.json"
            command = [
                str(ROOT / "bin" / "todo"), "list", "create",
                "--date",
                "2042-01-02",
                "--output", str(target),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = target.read_text()
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(target.read_text(), before)


if __name__ == "__main__":
    unittest.main()

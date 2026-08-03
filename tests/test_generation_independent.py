#!/usr/bin/env python3
"""Regression test: the scheduler entry point has no scheduler dependency."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class IndependentGenerationTest(unittest.TestCase):
    def test_entry_point_generates_without_launchd_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-entrypoint-") as temporary:
            data_dir = Path(temporary) / "todos"
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "create-daily-todo"),
                    "--date",
                    "2042-01-02",
                    "--data-dir",
                    str(data_dir),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            daily = data_dir / "2042-01-02"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((daily / "todo.json").is_file())
            self.assertEqual(len(list(daily.glob("*.md"))), 8)
            self.assertFalse((Path(temporary) / "launchd").exists())

    def test_existing_day_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-entrypoint-") as temporary:
            data_dir = Path(temporary) / "todos"
            command = [
                str(ROOT / "bin" / "create-daily-todo"),
                "--date",
                "2042-01-02",
                "--data-dir",
                str(data_dir),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            target = data_dir / "2042-01-02" / "todo.json"
            self.assertEqual(first.returncode, 0, first.stderr)
            before = target.read_text()
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_text(), before)


if __name__ == "__main__":
    unittest.main()

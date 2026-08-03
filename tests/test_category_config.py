#!/usr/bin/env python3
"""Tests for canonical category configuration."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class CategoryConfigTest(unittest.TestCase):
    def test_lists_canonical_categories(self) -> None:
        result = subprocess.run(
            [str(ROOT / "bin" / "todo-config"), "list-types"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("work\tWork\tdaily", result.stdout)
        self.assertIn("someday\tSomeday\tbacklog", result.stdout)

    def test_rejects_existing_category_without_modifying_config(self) -> None:
        config = ROOT / "config" / "task-types.conf"
        before = config.read_text()
        result = subprocess.run(
            [str(ROOT / "bin" / "todo-config"), "add-type", "work", "Duplicate"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(config.read_text(), before)


if __name__ == "__main__":
    unittest.main()

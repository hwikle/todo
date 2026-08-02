#!/usr/bin/env python3
"""Regression test: daily generation works without any scheduler installed."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class IndependentGenerationTest(unittest.TestCase):
    def test_generator_has_no_scheduler_dependency(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-generation-test-") as temporary:
            isolated = Path(temporary) / "todo"
            isolated.mkdir()
            for name in ("bin", "config", "schema", "backlog"):
                source = ROOT / name
                destination = isolated / name
                if source.is_dir():
                    shutil.copytree(source, destination)
            result = subprocess.run(
                [str(isolated / "bin" / "create-daily-todo"), "--date", "2042-01-02"],
                cwd=isolated,
                check=True,
                capture_output=True,
                text=True,
            )
            daily = isolated / "todos" / "2042-01-02"
            self.assertTrue(daily.is_dir())
            self.assertEqual(
                sorted(path.stem for path in daily.glob("*.md")),
                sorted(
                    [
                        "work",
                        "learning",
                        "software-projects",
                        "finance",
                        "health",
                        "household",
                        "errands",
                        "intellectual-projects",
                    ]
                ),
            )
            self.assertIn("Created", result.stdout)
            self.assertFalse((isolated / "launchd").exists())

    def test_existing_day_gains_new_configured_category_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="todo-category-test-") as temporary:
            isolated = Path(temporary) / "todo"
            isolated.mkdir()
            for name in ("bin", "config", "schema", "backlog"):
                shutil.copytree(ROOT / name, isolated / name)
            command = isolated / "bin" / "create-daily-todo"
            subprocess.run(
                [str(command), "--date", "2042-01-02"], cwd=isolated, check=True,
                capture_output=True, text=True,
            )
            work = isolated / "todos" / "2042-01-02" / "work.md"
            original_work = work.read_text()
            types = isolated / "config" / "task-types.conf"
            with types.open("a") as handle:
                handle.write("new-category|New Category|daily\n")
            subprocess.run(
                [str(command), "--date", "2042-01-02"], cwd=isolated, check=True,
                capture_output=True, text=True,
            )
            self.assertTrue(
                (isolated / "todos" / "2042-01-02" / "new-category.md").exists()
            )
            self.assertEqual(work.read_text(), original_work)


if __name__ == "__main__":
    unittest.main()

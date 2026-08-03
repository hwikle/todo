#!/usr/bin/env python3
"""Tests for explicit, configurable scheduling."""

from __future__ import annotations

import datetime as dt
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_schedule import ScheduleConfig, ScheduleConfigurationError, from_document, render_launchd


class ScheduleTest(unittest.TestCase):
    def test_configuration_round_trips(self) -> None:
        document = {
            "repository_directory": "/example/repository",
            "lists_directory": "/example/lists",
            "generation_time": "04:37",
            "codex_time": "04:42",
            "notifications": True,
        }
        config = from_document(document)
        self.assertEqual(json.loads(config.to_json()), document)

    def test_configuration_rejects_implicit_or_invalid_values(self) -> None:
        document: dict[str, object] = {
            "repository_directory": "relative/repository",
            "lists_directory": "/example/lists",
            "generation_time": "25:00",
            "codex_time": "04:42",
            "notifications": True,
        }
        with self.assertRaisesRegex(ScheduleConfigurationError, "absolute path"):
            from_document(document)
        document["repository_directory"] = "/example/repository"
        with self.assertRaisesRegex(ScheduleConfigurationError, "24-hour HH:MM"):
            from_document(document)

    def test_launchd_uses_configured_paths_time_and_notification(self) -> None:
        config = ScheduleConfig(
            repository_directory=Path("/example/repository"),
            lists_directory=Path("/example/lists"),
            generation_time=dt.time(4, 37),
            codex_time=dt.time(4, 42),
            notifications=False,
        )
        document = plistlib.loads(render_launchd(config, "example.todo").encode())
        self.assertEqual(document["ProgramArguments"], ["/example/repository/libexec/create-daily-todo"])
        self.assertEqual(document["EnvironmentVariables"]["TODO_LISTS_DIR"], "/example/lists")
        self.assertEqual(document["EnvironmentVariables"]["TODO_NOTIFY"], "0")
        self.assertEqual(document["StartCalendarInterval"], {"Hour": 4, "Minute": 37})
        self.assertNotIn("codex_time", document)

    def test_cli_writes_and_shows_explicit_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "schedule.json"
            result = subprocess.run(
                [
                    str(ROOT / "bin" / "todo"), "schedule", "configure",
                    "--config", str(config_path),
                    "--repository-dir", str(ROOT),
                    "--lists-dir", str(root / "lists"),
                    "--generation-time", "04:37",
                    "--codex-time", "04:42",
                    "--notify",
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            shown = subprocess.run(
                [str(ROOT / "bin" / "todo"), "schedule", "show", "--config", str(config_path)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(shown.returncode, 0, shown.stderr)
            document = json.loads(shown.stdout)
            self.assertEqual(document["generation_time"], "04:37")
            self.assertEqual(document["codex_time"], "04:42")
            self.assertTrue(document["notifications"])


if __name__ == "__main__":
    unittest.main()

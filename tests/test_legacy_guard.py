#!/usr/bin/env python3
"""Tests that legacy Markdown data commands cannot run accidentally."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class LegacyGuardTest(unittest.TestCase):
    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.pop("TODO_ENABLE_LEGACY", None)
        return subprocess.run(
            [str(ROOT / "bin" / "todo"), *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )

    def test_legacy_generator_is_disabled(self) -> None:
        result = self.invoke("generate", "--date", "2042-01-02")
        self.assertEqual(result.returncode, 2)
        self.assertIn("legacy Markdown task commands are disabled", result.stderr)

    def test_configuration_inspection_remains_available(self) -> None:
        result = self.invoke("types")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("work", result.stdout)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for complete, user-facing command-line guidance."""

from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_main import parser
from todo_schema import CanonicalSchemaBundle


class CliHelpTest(unittest.TestCase):
    bundle: ClassVar[CanonicalSchemaBundle]

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = CanonicalSchemaBundle(ROOT / "schema")

    def run_todo(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin" / "todo"), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_missing_command_prints_top_level_help(self) -> None:
        result = self.run_todo()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Create, organize, validate, and review TODO lists", result.stderr)
        self.assertIn("workflow to perform", result.stderr)
        self.assertIn("todo: the following arguments are required: COMMAND", result.stderr)

    def test_missing_required_arguments_prints_leaf_help(self) -> None:
        result = self.run_todo("task", "add")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Add one task to a canonical TODO list.", result.stderr)
        self.assertIn("--dependency-of TASK", result.stderr)
        self.assertIn("canonical TODO-list JSON file to read", result.stderr)
        self.assertIn("required: FILE, NAME, --category", result.stderr)

    def test_every_parser_and_argument_has_help(self) -> None:
        pending = [parser(self.bundle)]
        while pending:
            current = pending.pop()
            self.assertTrue(current.description, current.prog)
            for action in current._actions:
                if isinstance(action, argparse._HelpAction):
                    continue
                self.assertNotIn(action.help, (None, argparse.SUPPRESS), f"{current.prog}: {action.dest}")
                if isinstance(action, argparse._SubParsersAction):
                    pending.extend(action.choices.values())

    def test_schema_choices_remain_visible(self) -> None:
        result = self.run_todo("task", "add", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        priorities = "{" + ",".join(self.bundle.priority_policy.order) + "}"
        self.assertIn(priorities, result.stdout)
        self.assertIn("{hard,soft}", result.stdout)


if __name__ == "__main__":
    unittest.main()

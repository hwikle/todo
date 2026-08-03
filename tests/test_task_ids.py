#!/usr/bin/env python3
"""Tests for canonical UUIDv4 generation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_ids import TaskIdSource, is_canonical_task_id


class TaskIdTest(unittest.TestCase):
    def test_generates_canonical_uuid(self) -> None:
        value = TaskIdSource().next()
        self.assertTrue(is_canonical_task_id(value))


if __name__ == "__main__":
    unittest.main()

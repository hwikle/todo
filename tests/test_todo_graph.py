#!/usr/bin/env python3
"""Tests for validated-model dependency graph and category root selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from todo_graph import TaskGraph, category_roots
from todo_model import Task


def task(task_id: str, dependencies: list[str]) -> Task:
    return cast(Task, {
        "id": task_id,
        "name": task_id,
        "completed": False,
        "dependencies": dependencies,
    })


class TaskGraphTest(unittest.TestCase):
    def test_descendants_include_transitive_dependencies(self) -> None:
        graph = TaskGraph([
            task("parent", ["child"]),
            task("child", ["grandchild"]),
            task("grandchild", []),
        ])
        self.assertEqual(graph.descendants("parent"), {"child", "grandchild"})

    def test_category_roots_preserve_membership_order(self) -> None:
        graph = TaskGraph([
            task("first", ["shared"]),
            task("second", ["shared"]),
            task("shared", []),
        ])
        self.assertEqual(
            category_roots(graph, ["second", "shared", "first"]),
            ("second", "first"),
        )

    def test_dependency_is_root_when_parent_is_not_a_member(self) -> None:
        graph = TaskGraph([task("parent", ["child"]), task("child", [])])
        self.assertEqual(category_roots(graph, ["child"]), ("child",))


if __name__ == "__main__":
    unittest.main()

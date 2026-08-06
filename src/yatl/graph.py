"""Dependency-graph operations for validated canonical TODO models."""

from __future__ import annotations

from collections.abc import Iterable
from functools import cache

from yatl.model import Task


class TaskGraph:
    """An ordered dependency graph built from a validated task collection."""

    def __init__(self, tasks: Iterable[Task]) -> None:
        self._tasks = {task["id"]: task for task in tasks}

    def task(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def dependencies(self, task_id: str) -> tuple[str, ...]:
        return tuple(self._tasks[task_id]["dependencies"])

    @cache
    def descendants(self, task_id: str) -> frozenset[str]:
        result: set[str] = set()
        for dependency_id in self.dependencies(task_id):
            result.add(dependency_id)
            result.update(self.descendants(dependency_id))
        return frozenset(result)


def category_roots(graph: TaskGraph, member_ids: Iterable[str]) -> tuple[str, ...]:
    """Select category members not nested beneath another category member."""
    members = tuple(member_ids)
    nested: set[str] = set()
    member_set = set(members)
    for task_id in members:
        nested.update(graph.descendants(task_id) & member_set)
    return tuple(task_id for task_id in members if task_id not in nested)

"""Shared static types for the canonical JSON-compatible TODO model."""

from __future__ import annotations

from typing import Literal, TypedDict


Priority = Literal["must", "should", "could"]
DeadlineKind = Literal["hard", "soft"]


class DueDateRequired(TypedDict):
    year: int


class DueDate(DueDateRequired, total=False):
    month: int
    day: int
    time: str


class TaskRequired(TypedDict):
    id: str
    name: str
    completed: bool
    dependencies: list[str]


class Task(TaskRequired, total=False):
    description: str
    priority: Priority
    due: DueDate
    deadline_kind: DeadlineKind


class Category(TypedDict):
    id: str
    display_name: str


class CategoryMembership(TypedDict):
    category: str
    tasks: list[str]


class TodoList(TypedDict):
    date: str
    tasks: list[Task]
    categories: list[Category]
    category_memberships: list[CategoryMembership]

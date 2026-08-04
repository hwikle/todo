"""Scheduler-independent canonical daily TODO generation."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Iterable, Optional

from todo_model import Category, CategoryMembership, Task, TodoList


class GenerationError(Exception):
    """Canonical daily generation cannot proceed safely."""


def generate_document(
    target_date: str,
    previous: Optional[TodoList],
    initial_categories: Iterable[Category],
) -> TodoList:
    try:
        target_date = dt.date.fromisoformat(target_date).isoformat()
    except ValueError as exc:
        raise GenerationError(f"invalid target date {target_date!r}") from exc

    if previous is None:
        categories = [copy.deepcopy(category) for category in initial_categories]
        return {
            "date": target_date,
            "tasks": [],
            "categories": categories,
            "category_memberships": [
                {"category": category["id"], "tasks": []} for category in categories
            ],
        }

    retained_ids = {
        task["id"] for task in previous["tasks"] if not task["completed"]
    }
    tasks: list[Task] = []
    for task in previous["tasks"]:
        if task["id"] not in retained_ids:
            continue
        carried = copy.deepcopy(task)
        carried["completed"] = False
        carried["dependencies"] = [
            dependency_id
            for dependency_id in carried["dependencies"]
            if dependency_id in retained_ids
        ]
        tasks.append(carried)

    categories = [copy.deepcopy(category) for category in previous["categories"]]
    category_ids = {category["id"] for category in categories}
    for category in initial_categories:
        if category["id"] not in category_ids:
            categories.append(copy.deepcopy(category))
            category_ids.add(category["id"])

    memberships_by_category: dict[str, list[str]] = {
        category["id"]: [] for category in categories
    }
    for membership in previous["category_memberships"]:
        current = memberships_by_category.setdefault(membership["category"], [])
        for task_id in membership["tasks"]:
            if task_id in retained_ids and task_id not in current:
                current.append(task_id)
    memberships: list[CategoryMembership] = [
        {"category": category["id"], "tasks": memberships_by_category[category["id"]]}
        for category in categories
    ]
    return {
        "date": target_date,
        "tasks": tasks,
        "categories": categories,
        "category_memberships": memberships,
    }

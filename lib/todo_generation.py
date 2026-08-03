"""Scheduler-independent canonical daily TODO generation."""

from __future__ import annotations

import copy
import datetime as dt
import re
from pathlib import Path
from typing import Iterable, Optional

from todo_model import Category, CategoryMembership, Task, TodoList


class GenerationError(Exception):
    """Canonical daily generation cannot proceed safely."""


def configured_daily_categories(path: Path) -> list[Category]:
    categories: list[Category] = []
    seen: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise GenerationError(f"cannot read category configuration {path}: {exc}") from exc
    for line_number, raw in enumerate(lines, 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        parts = [part.strip() for part in value.split("|")]
        if len(parts) != 3:
            raise GenerationError(f"{path}:{line_number}: expected slug|display name|behavior")
        category_id, display_name, behavior = parts
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", category_id):
            raise GenerationError(f"{path}:{line_number}: invalid category ID {category_id!r}")
        if category_id in seen:
            raise GenerationError(f"{path}:{line_number}: duplicate category ID {category_id!r}")
        if not display_name:
            raise GenerationError(f"{path}:{line_number}: empty category display name")
        if behavior not in {"daily", "backlog"}:
            raise GenerationError(f"{path}:{line_number}: invalid behavior {behavior!r}")
        seen.add(category_id)
        if behavior == "daily":
            categories.append({"id": category_id, "display_name": display_name})
    return categories


def latest_previous_list(data_dir: Path, target_date: str) -> Optional[Path]:
    candidates: list[tuple[str, Path]] = []
    if not data_dir.exists():
        return None
    for child in data_dir.iterdir():
        if not child.is_dir() or child.name >= target_date:
            continue
        try:
            dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        candidate = child / "todo.json"
        if candidate.is_file():
            candidates.append((child.name, candidate))
    return max(candidates, default=("", None), key=lambda item: item[0])[1]


def generate_document(
    target_date: str,
    previous: Optional[TodoList],
    configured_categories: Iterable[Category],
) -> TodoList:
    try:
        target_date = dt.date.fromisoformat(target_date).isoformat()
    except ValueError as exc:
        raise GenerationError(f"invalid target date {target_date!r}") from exc

    if previous is None:
        categories = [copy.deepcopy(category) for category in configured_categories]
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
    for category in configured_categories:
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

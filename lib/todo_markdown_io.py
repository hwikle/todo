"""Filesystem adapter for legacy Markdown-to-canonical conversion."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable, Optional

from todo_ids import TaskIdSource
from todo_markdown import MarkdownConversionError, parse_category_text
from todo_model import Category, CategoryMembership, Priority, Task, TodoList


def convert_daily_directory(
    source: Path,
    priority_values: list[Priority],
    id_generator: Optional[Callable[[], str]] = None,
) -> TodoList:
    source = source.resolve()
    try:
        date = dt.date.fromisoformat(source.name).isoformat()
    except ValueError as exc:
        raise MarkdownConversionError(
            f"{source}: directory name must be an ISO date"
        ) from exc
    if not source.is_dir():
        raise MarkdownConversionError(f"{source}: source must be a directory")
    files = sorted(source.glob("*.md"))
    if not files:
        raise MarkdownConversionError(f"{source}: no category Markdown files found")
    priorities = {value.casefold(): value for value in priority_values}
    ids = TaskIdSource(id_generator)
    generated_ids: set[str] = set()
    categories: list[Category] = []
    canonical_tasks: list[Task] = []
    memberships: list[CategoryMembership] = []
    for path in files:
        try:
            content = path.read_text()
        except OSError as exc:
            raise MarkdownConversionError(f"cannot read {path}: {exc}") from exc
        category, tasks = parse_category_text(content, path, date, priorities, ids)
        for task in tasks:
            if task.task_id in generated_ids:
                raise MarkdownConversionError(
                    f"{task.source}: generated duplicate task ID {task.task_id!r}"
                )
            generated_ids.add(task.task_id)
        categories.append(category)
        task_ids = [task.task_id for task in tasks]
        canonical_tasks.extend(task.canonical() for task in tasks)
        memberships.append({"category": category["id"], "tasks": task_ids})
    return {
        "date": date,
        "tasks": canonical_tasks,
        "categories": categories,
        "category_memberships": memberships,
    }

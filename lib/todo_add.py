"""Incrementally add one task while preserving canonical document invariants."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from todo_ids import TaskIdSource
from todo_model import DeadlineKind, DueDate, Priority, Task, TodoList
from todo_priority import PriorityPolicy


class TaskAdditionError(Exception):
    """A task cannot be added without ambiguity or invariant violation."""


@dataclass(frozen=True)
class AddedTask:
    document: TodoList
    task: Task


def _resolve_task(document: TodoList, selector: str) -> Task:
    by_id = [task for task in document["tasks"] if task["id"] == selector]
    if by_id:
        return by_id[0]
    by_name = [task for task in document["tasks"] if task["name"] == selector]
    if not by_name:
        raise TaskAdditionError(f"no existing task matches {selector!r}")
    if len(by_name) > 1:
        raise TaskAdditionError(f"task selector {selector!r} is ambiguous")
    return by_name[0]


def _resolve_category(document: TodoList, selector: str) -> str:
    by_id = [item for item in document["categories"] if item["id"] == selector]
    if by_id:
        return by_id[0]["id"]
    by_name = [item for item in document["categories"] if item["display_name"] == selector]
    if not by_name:
        raise TaskAdditionError(f"no category matches {selector!r}")
    if len(by_name) > 1:
        raise TaskAdditionError(f"category selector {selector!r} is ambiguous")
    return by_name[0]["id"]


def add_task(
    document: TodoList,
    *,
    name: str,
    category_selectors: list[str],
    priority_policy: PriorityPolicy,
    priority: Priority | None = None,
    description: str | None = None,
    dependency_selectors: list[str] | None = None,
    due: DueDate | None = None,
    deadline_kind: DeadlineKind | None = None,
    ids: TaskIdSource | None = None,
) -> AddedTask:
    if not name.strip():
        raise TaskAdditionError("task name cannot be empty")
    if not category_selectors:
        raise TaskAdditionError("at least one category is required")
    if priority is not None and priority not in priority_policy.order:
        raise TaskAdditionError(f"unknown priority {priority!r}")
    if (due is None) != (deadline_kind is None):
        raise TaskAdditionError("due date and deadline kind must be provided together")

    categories = [_resolve_category(document, item) for item in category_selectors]
    if len(categories) != len(set(categories)):
        raise TaskAdditionError("the same category was selected more than once")

    dependencies = [
        _resolve_task(document, item) for item in (dependency_selectors or [])
    ]
    dependency_ids = [task["id"] for task in dependencies]
    if len(dependency_ids) != len(set(dependency_ids)):
        raise TaskAdditionError("the same dependency was selected more than once")
    if priority is not None:
        for dependency in dependencies:
            dependency_priority = dependency.get("priority")
            if (
                dependency_priority is not None
                and priority_policy.rank(dependency_priority) < priority_policy.rank(priority)
            ):
                raise TaskAdditionError(
                    f"dependency {dependency['name']!r} has higher priority "
                    f"{dependency_priority!r} than new task priority {priority!r}"
                )

    task_id = (ids or TaskIdSource()).next(task["id"] for task in document["tasks"])
    task: Task = {
        "id": task_id,
        "name": name.strip(),
        "completed": False,
        "dependencies": dependency_ids,
    }
    if priority is not None:
        task["priority"] = priority
    if description is not None:
        task["description"] = description
    if due is not None and deadline_kind is not None:
        task["due"] = due
        task["deadline_kind"] = deadline_kind

    updated = copy.deepcopy(document)
    updated["tasks"].append(task)
    memberships = {
        membership["category"]: membership
        for membership in updated["category_memberships"]
    }
    for category_id in categories:
        membership = memberships.get(category_id)
        if membership is None:
            membership = {"category": category_id, "tasks": []}
            updated["category_memberships"].append(membership)
            memberships[category_id] = membership
        membership["tasks"].append(task_id)
    return AddedTask(updated, task)

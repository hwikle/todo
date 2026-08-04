"""Pure canonical task mutation operations."""

from __future__ import annotations

import copy
from collections.abc import Iterable

from todo_model import Task, TodoList
from todo_priority import PriorityPolicy
from todo_selectors import SelectorError, resolve_category, resolve_task


class TaskMutationError(Exception):
    """A requested task mutation would be ambiguous or invalid."""


def dependency_reaches(document: TodoList, start_id: str, target_id: str) -> bool:
    tasks = {task["id"]: task for task in document["tasks"]}
    pending = [start_id]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(tasks[current]["dependencies"])
    return False


def attach_to_parents(
    document: TodoList,
    new_task: Task,
    parent_selectors: Iterable[str],
    priority_policy: PriorityPolicy,
) -> None:
    try:
        parents = [resolve_task(document, selector) for selector in parent_selectors]
    except SelectorError as exc:
        raise TaskMutationError(str(exc)) from exc
    parent_ids = [task["id"] for task in parents]
    if len(parent_ids) != len(set(parent_ids)):
        raise TaskMutationError("the same parent was selected more than once")
    for parent in parents:
        if parent["completed"]:
            raise TaskMutationError(f"completed parent {parent['name']!r} cannot gain an incomplete dependency")
        parent_priority = parent.get("priority")
        new_priority = new_task.get("priority")
        if (
            parent_priority is not None
            and new_priority is None
            and priority_policy.rank(parent_priority) < len(priority_policy.order) - 1
        ):
            raise TaskMutationError(
                f"new task is unprioritized and less urgent than parent "
                f"{parent['name']!r} priority {parent_priority!r}"
            )
        if (
            parent_priority is not None
            and new_priority is not None
            and priority_policy.rank(new_priority) > priority_policy.rank(parent_priority)
        ):
            raise TaskMutationError(
                f"new task priority {new_priority!r} is less urgent than parent "
                f"{parent['name']!r} priority {parent_priority!r}"
            )
        for dependency_id in new_task["dependencies"]:
            if dependency_reaches(document, dependency_id, parent["id"]):
                raise TaskMutationError(
                    f"attaching to parent {parent['name']!r} would create a dependency cycle"
                )
    for parent in parents:
        parent["dependencies"].append(new_task["id"])


def set_completion(document: TodoList, selector: str, completed: bool) -> TodoList:
    try:
        selected = resolve_task(document, selector)
    except SelectorError as exc:
        raise TaskMutationError(str(exc)) from exc
    if completed:
        tasks = {task["id"]: task for task in document["tasks"]}
        incomplete = [tasks[item]["name"] for item in selected["dependencies"] if not tasks[item]["completed"]]
        if incomplete:
            raise TaskMutationError(f"task has incomplete dependencies: {', '.join(incomplete)}")
    else:
        completed_parents = [
            task["name"]
            for task in document["tasks"]
            if task["completed"] and selected["id"] in task["dependencies"]
        ]
        if completed_parents:
            raise TaskMutationError(
                "completed tasks depend on this task: " + ", ".join(completed_parents)
            )
    updated = copy.deepcopy(document)
    resolve_task(updated, selected["id"])["completed"] = completed
    return updated


def remove_task(document: TodoList, selector: str) -> TodoList:
    try:
        selected = resolve_task(document, selector)
    except SelectorError as exc:
        raise TaskMutationError(str(exc)) from exc
    updated = copy.deepcopy(document)
    updated["tasks"] = [task for task in updated["tasks"] if task["id"] != selected["id"]]
    for task in updated["tasks"]:
        task["dependencies"] = [item for item in task["dependencies"] if item != selected["id"]]
    for membership in updated["category_memberships"]:
        membership["tasks"] = [item for item in membership["tasks"] if item != selected["id"]]
    return updated

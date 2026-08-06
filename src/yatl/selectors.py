"""Unambiguous selectors for canonical tasks and categories."""

from __future__ import annotations

from yatl.model import Category, Task, TodoList


class SelectorError(Exception):
    """A selector is missing or ambiguous."""


def resolve_task(document: TodoList, selector: str) -> Task:
    by_id = [task for task in document["tasks"] if task["id"] == selector]
    if by_id:
        return by_id[0]
    by_name = [task for task in document["tasks"] if task["name"] == selector]
    if not by_name:
        raise SelectorError(f"no existing task matches {selector!r}")
    if len(by_name) > 1:
        raise SelectorError(f"task selector {selector!r} is ambiguous")
    return by_name[0]


def resolve_category(document: TodoList, selector: str) -> Category:
    by_id = [item for item in document["categories"] if item["id"] == selector]
    if by_id:
        return by_id[0]
    by_name = [item for item in document["categories"] if item["display_name"] == selector]
    if not by_name:
        raise SelectorError(f"no category matches {selector!r}")
    if len(by_name) > 1:
        raise SelectorError(f"category selector {selector!r} is ambiguous")
    return by_name[0]

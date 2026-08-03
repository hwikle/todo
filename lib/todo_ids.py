"""Canonical UUIDv4 task-identity generation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import copy
import uuid

from todo_model import TodoList


class TaskIdGenerationError(Exception):
    """A unique canonical task ID could not be generated."""


def is_canonical_task_id(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


class TaskIdSource:
    def __init__(self, generator: Callable[[], str] | None = None) -> None:
        self.generator = generator or (lambda: str(uuid.uuid4()))
        self.seen: set[str] = set()

    def next(self, excluded: Iterable[str] = ()) -> str:
        occupied = set(excluded)
        for _ in range(1000):
            candidate = self.generator()
            if not is_canonical_task_id(candidate):
                raise TaskIdGenerationError(
                    f"task ID generator produced non-canonical UUIDv4 {candidate!r}"
                )
            if candidate not in occupied and candidate not in self.seen:
                self.seen.add(candidate)
                return candidate
        raise TaskIdGenerationError("could not generate a unique UUIDv4 task ID")


def migrate_task_ids(document: TodoList, ids: TaskIdSource | None = None) -> TodoList:
    source = ids or TaskIdSource()
    existing = [task["id"] for task in document["tasks"]]
    if len(existing) != len(set(existing)):
        raise TaskIdGenerationError("cannot migrate duplicate existing task IDs")
    preserved = {task_id for task_id in existing if is_canonical_task_id(task_id)}
    mapping: dict[str, str] = {}
    for task_id in existing:
        mapping[task_id] = (
            task_id if task_id in preserved else source.next(preserved | set(mapping.values()))
        )

    migrated = copy.deepcopy(document)
    for task in migrated["tasks"]:
        task["id"] = mapping[task["id"]]
        try:
            task["dependencies"] = [mapping[item] for item in task["dependencies"]]
        except KeyError as exc:
            raise TaskIdGenerationError(
                f"cannot migrate unknown dependency ID {exc.args[0]!r}"
            ) from exc
    for membership in migrated["category_memberships"]:
        try:
            membership["tasks"] = [mapping[item] for item in membership["tasks"]]
        except KeyError as exc:
            raise TaskIdGenerationError(
                f"cannot migrate unknown membership task ID {exc.args[0]!r}"
            ) from exc
    return migrated

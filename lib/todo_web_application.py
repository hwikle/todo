"""Application service for atomic, revision-aware browser edits."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, cast

from todo_application import AddTaskRequest, EditTaskRequest, TodoApplication
from todo_generation import generate_document
from todo_io import create_text_atomic, write_text_atomic
from todo_model import Category, DeadlineKind, DueDate, Priority, Task, TodoList
from todo_schema import CanonicalSchemaBundle
from todo_selectors import resolve_task


class WebEditError(ValueError):
    """A browser edit is malformed or invalid."""


class RevisionConflict(WebEditError):
    """The canonical file changed after the browser last loaded it."""


class TaskRequiredError(WebEditError):
    """A task cannot be removed while other tasks depend on it."""

    def __init__(self, blockers: list[dict[str, Any]]) -> None:
        self.blockers = blockers
        super().__init__("outdent this task from its parent tasks before deleting it")


@dataclass(frozen=True)
class DocumentSnapshot:
    document: TodoList
    revision: str


@dataclass(frozen=True)
class TaskCreationResult:
    snapshot: DocumentSnapshot
    task_id: str


class TodoWebApplication:
    """Coordinate browser operations without coupling domain logic to HTTP."""

    def __init__(
        self,
        path: Path,
        bundle: CanonicalSchemaBundle,
        configured_categories: Iterable[Category] = (),
    ) -> None:
        self.path = path.resolve()
        self.application = TodoApplication(bundle)
        self.configured_categories = tuple(copy.deepcopy(list(configured_categories)))

    @staticmethod
    def _revision(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def load(self) -> DocumentSnapshot:
        content = self.path.read_bytes()
        document = cast(TodoList, json.loads(content))
        errors = [
            issue for issue in self.application.validate(document)
            if issue.severity == "error"
        ]
        if errors:
            first = errors[0]
            raise WebEditError(f"{first.location}: {first.message}")
        return DocumentSnapshot(document, self._revision(content))

    def exists(self) -> bool:
        return self.path.exists()

    def creation_state(self) -> dict[str, Any]:
        return {
            "exists": False,
            "default_date": dt.date.today().isoformat(),
            "categories": list(copy.deepcopy(self.configured_categories)),
        }

    def create(self, target_date: str) -> DocumentSnapshot:
        if self.path.exists():
            raise RevisionConflict("the TODO list was created elsewhere; reload before continuing")
        document = generate_document(target_date, None, self.configured_categories)
        errors = [
            issue for issue in self.application.validate(document)
            if issue.severity == "error"
        ]
        if errors:
            first = errors[0]
            raise WebEditError(f"{first.location}: {first.message}")
        content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        try:
            create_text_atomic(self.path, content)
        except FileExistsError as exc:
            raise RevisionConflict(
                "the TODO list was created elsewhere; reload before continuing"
            ) from exc
        return DocumentSnapshot(document, self._revision(content.encode()))

    def _save(self, document: TodoList, expected_revision: str) -> DocumentSnapshot:
        current = self.path.read_bytes()
        if self._revision(current) != expected_revision:
            raise RevisionConflict("the TODO list changed on disk; reload before saving")
        errors = [
            issue for issue in self.application.validate(document)
            if issue.severity == "error"
        ]
        if errors:
            first = errors[0]
            raise WebEditError(f"{first.location}: {first.message}")
        content = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
        write_text_atomic(self.path, content.decode(), replace=True)
        return DocumentSnapshot(document, self._revision(content))

    def _change(
        self,
        expected_revision: str,
        operation: Callable[[TodoList], TodoList],
    ) -> DocumentSnapshot:
        snapshot = self.load()
        if snapshot.revision != expected_revision:
            raise RevisionConflict("the TODO list changed on disk; reload before saving")
        return self._save(operation(snapshot.document), expected_revision)

    def add_task(
        self,
        expected_revision: str,
        *,
        name: str,
        categories: tuple[str, ...],
        priority: Optional[Priority],
        parent_id: Optional[str],
        after_id: Optional[str],
        context_category: Optional[str],
    ) -> TaskCreationResult:
        created_id: Optional[str] = None

        def operation(document: TodoList) -> TodoList:
            nonlocal created_id
            before = {task["id"] for task in document["tasks"]}
            updated = self.application.add(
                document,
                AddTaskRequest(
                    name=name,
                    categories=categories,
                    priority=priority,
                    dependency_of=(parent_id,) if parent_id else (),
                ),
            )
            new_task = next(task for task in updated["tasks"] if task["id"] not in before)
            created_id = new_task["id"]
            self._position(updated, new_task["id"], parent_id, after_id, context_category)
            return updated

        snapshot = self._change(expected_revision, operation)
        if created_id is None:
            raise WebEditError("task creation did not produce exactly one new task")
        return TaskCreationResult(snapshot, created_id)

    def edit_task(
        self,
        expected_revision: str,
        task_id: str,
        *,
        name: Optional[str] = None,
        description_supplied: bool = False,
        description: Optional[str] = None,
        priority_supplied: bool = False,
        priority: Optional[Priority] = None,
        categories: Optional[tuple[str, ...]] = None,
        due_supplied: bool = False,
        due: Optional[DueDate] = None,
        deadline_kind: Optional[DeadlineKind] = None,
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            current_categories = {
                membership["category"]
                for membership in document["category_memberships"]
                if task_id in membership["tasks"]
            }
            desired_categories = current_categories if categories is None else set(categories)
            request = EditTaskRequest(
                name=name,
                description=description if description_supplied and description is not None else None,
                clear_description=description_supplied and description is None,
                priority=priority if priority_supplied and priority is not None else None,
                clear_priority=priority_supplied and priority is None,
                add_categories=tuple(sorted(desired_categories - current_categories)),
                remove_categories=tuple(sorted(current_categories - desired_categories)),
                due=due if due_supplied and due is not None else None,
                deadline_kind=deadline_kind if due_supplied and due is not None else None,
                clear_due=due_supplied and due is None,
            )
            return self.application.edit(document, task_id, request)

        return self._change(expected_revision, operation)

    def set_completed(
        self, expected_revision: str, task_id: str, completed: bool
    ) -> DocumentSnapshot:
        return self._change(
            expected_revision,
            lambda document: self.application.complete(document, task_id, completed),
        )

    def move_task(
        self,
        expected_revision: str,
        task_id: str,
        *,
        old_parent_id: Optional[str],
        new_parent_id: Optional[str],
        after_id: Optional[str],
        context_category: Optional[str],
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            resolve_task(updated, task_id)
            if old_parent_id:
                old_parent = resolve_task(updated, old_parent_id)
                if task_id not in old_parent["dependencies"]:
                    raise WebEditError("task is not a dependency of its displayed parent")
                old_parent["dependencies"].remove(task_id)
            self._position(updated, task_id, new_parent_id, after_id, context_category)
            return updated

        return self._change(expected_revision, operation)

    def remove_task(self, expected_revision: str, task_id: str) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            parents = [task for task in document["tasks"] if task_id in task["dependencies"]]
            if parents:
                memberships = {
                    task["id"]: [
                        item["category"]
                        for item in document["category_memberships"]
                        if task["id"] in item["tasks"]
                    ]
                    for task in parents
                }
                raise TaskRequiredError([
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "priority": task.get("priority"),
                        "categories": memberships[task["id"]],
                    }
                    for task in parents
                ])
            return self.application.remove(document, task_id)

        return self._change(
            expected_revision,
            operation,
        )

    @staticmethod
    def _position(
        document: TodoList,
        task_id: str,
        parent_id: Optional[str],
        after_id: Optional[str],
        context_category: Optional[str],
    ) -> None:
        if parent_id:
            parent = resolve_task(document, parent_id)
            if task_id in parent["dependencies"]:
                parent["dependencies"].remove(task_id)
            position = (
                parent["dependencies"].index(after_id) + 1
                if after_id in parent["dependencies"] else len(parent["dependencies"])
            )
            parent["dependencies"].insert(position, task_id)
            return
        if context_category is None:
            return
        membership = next(
            (item for item in document["category_memberships"] if item["category"] == context_category),
            None,
        )
        if membership is None or task_id not in membership["tasks"]:
            raise WebEditError("task is not assigned to the displayed category")
        membership["tasks"].remove(task_id)
        position = (
            membership["tasks"].index(after_id) + 1
            if after_id in membership["tasks"] else len(membership["tasks"])
        )
        membership["tasks"].insert(position, task_id)


def snapshot_payload(snapshot: DocumentSnapshot) -> dict[str, Any]:
    return {"document": snapshot.document, "revision": snapshot.revision}

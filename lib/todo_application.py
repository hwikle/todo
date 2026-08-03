"""Shared application operations for canonical TODO documents."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

from todo_add import TaskAdditionError, add_task
from todo_ids import TaskIdGenerationError
from todo_model import DeadlineKind, DueDate, Priority, TodoList
from todo_schema import CanonicalSchemaBundle
from todo_selectors import SelectorError, resolve_category, resolve_task
from todo_task_mutation import TaskMutationError, attach_to_parents, remove_task, set_completion
from todo_validation import CanonicalTodoValidator, Issue


class TodoApplicationError(ValueError):
    """A requested operation could not produce a valid canonical document."""


@dataclass(frozen=True)
class AddTaskRequest:
    name: str
    categories: tuple[str, ...]
    description: Optional[str] = None
    priority: Optional[Priority] = None
    depends_on: tuple[str, ...] = ()
    dependency_of: tuple[str, ...] = ()
    due: Optional[DueDate] = None
    deadline_kind: Optional[DeadlineKind] = None


@dataclass(frozen=True)
class EditTaskRequest:
    name: Optional[str] = None
    description: Optional[str] = None
    clear_description: bool = False
    priority: Optional[Priority] = None
    clear_priority: bool = False
    add_categories: tuple[str, ...] = ()
    remove_categories: tuple[str, ...] = ()
    add_dependencies: tuple[str, ...] = ()
    remove_dependencies: tuple[str, ...] = ()
    due: Optional[DueDate] = None
    deadline_kind: Optional[DeadlineKind] = None
    clear_due: bool = False


class TodoApplication:
    def __init__(self, bundle: CanonicalSchemaBundle) -> None:
        self.bundle = bundle
        self.validator = CanonicalTodoValidator(bundle.schema_dir)

    def _checked(self, document: TodoList) -> TodoList:
        issues = self.validator.validate(document)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            first = errors[0]
            raise TodoApplicationError(f"{first.location}: {first.message}")
        return document

    def validate(self, document: TodoList) -> list[Issue]:
        return self.validator.validate(document)

    def add(self, document: TodoList, request: AddTaskRequest) -> TodoList:
        if (request.due is None) != (request.deadline_kind is None):
            raise TodoApplicationError("due date and deadline kind must be provided together")
        try:
            added = add_task(
                document,
                name=request.name,
                category_selectors=list(request.categories),
                priority_policy=self.bundle.priority_policy,
                priority=request.priority,
                description=request.description,
                dependency_selectors=list(request.depends_on),
                due=request.due,
                deadline_kind=request.deadline_kind,
            )
            attach_to_parents(
                added.document, added.task, request.dependency_of, self.bundle.priority_policy
            )
            return self._checked(added.document)
        except (TaskAdditionError, TaskIdGenerationError, TaskMutationError, SelectorError) as exc:
            raise TodoApplicationError(str(exc)) from exc

    def edit(self, document: TodoList, selector: str, request: EditTaskRequest) -> TodoList:
        updated = copy.deepcopy(document)
        try:
            task = resolve_task(updated, selector)
            if request.name is not None:
                if not request.name.strip():
                    raise TodoApplicationError("task name cannot be empty")
                task["name"] = request.name.strip()
            if request.description is not None and request.clear_description:
                raise TodoApplicationError("description and clear-description conflict")
            if request.description is not None:
                task["description"] = request.description
            if request.clear_description:
                task.pop("description", None)
            if request.priority is not None and request.clear_priority:
                raise TodoApplicationError("priority and clear-priority conflict")
            if request.priority is not None:
                task["priority"] = request.priority
            if request.clear_priority:
                task.pop("priority", None)
            if request.clear_due and (request.due is not None or request.deadline_kind is not None):
                raise TodoApplicationError("clear-due conflicts with due values")
            if request.clear_due:
                task.pop("due", None)
                task.pop("deadline_kind", None)
            elif request.due is not None or request.deadline_kind is not None:
                if request.due is None or request.deadline_kind is None:
                    raise TodoApplicationError("due date and deadline kind must be provided together")
                task["due"] = request.due
                task["deadline_kind"] = request.deadline_kind
            self._change_dependencies(updated, task["id"], request)
            self._change_categories(updated, task["id"], request)
            return self._checked(updated)
        except (SelectorError, TaskMutationError) as exc:
            raise TodoApplicationError(str(exc)) from exc

    @staticmethod
    def _change_dependencies(document: TodoList, task_id: str, request: EditTaskRequest) -> None:
        task = resolve_task(document, task_id)
        for selector in request.add_dependencies:
            dependency = resolve_task(document, selector)
            if dependency["id"] in task["dependencies"]:
                raise TodoApplicationError(f"dependency {selector!r} is already present")
            task["dependencies"].append(dependency["id"])
        for selector in request.remove_dependencies:
            dependency = resolve_task(document, selector)
            if dependency["id"] not in task["dependencies"]:
                raise TodoApplicationError(f"dependency {selector!r} is not present")
            task["dependencies"].remove(dependency["id"])

    @staticmethod
    def _change_categories(document: TodoList, task_id: str, request: EditTaskRequest) -> None:
        memberships = {item["category"]: item for item in document["category_memberships"]}
        for selector in request.add_categories:
            category_id = resolve_category(document, selector)["id"]
            membership = memberships.setdefault(category_id, {"category": category_id, "tasks": []})
            if membership not in document["category_memberships"]:
                document["category_memberships"].append(membership)
            if task_id in membership["tasks"]:
                raise TodoApplicationError(f"category {selector!r} is already assigned")
            membership["tasks"].append(task_id)
        for selector in request.remove_categories:
            category_id = resolve_category(document, selector)["id"]
            removable = memberships.get(category_id)
            if removable is None or task_id not in removable["tasks"]:
                raise TodoApplicationError(f"category {selector!r} is not assigned")
            removable["tasks"].remove(task_id)

    def complete(self, document: TodoList, selector: str, completed: bool) -> TodoList:
        try:
            return self._checked(set_completion(document, selector, completed))
        except TaskMutationError as exc:
            raise TodoApplicationError(str(exc)) from exc

    def remove(self, document: TodoList, selector: str) -> TodoList:
        try:
            return self._checked(remove_task(document, selector))
        except TaskMutationError as exc:
            raise TodoApplicationError(str(exc)) from exc

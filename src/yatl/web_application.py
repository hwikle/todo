"""Application service for atomic, revision-aware browser edits."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional, cast

from yatl.application import AddTaskRequest, EditTaskRequest, TodoApplication
from yatl.generation import generate_document
from yatl.io import create_text_atomic, write_text_atomic
from yatl.model import Category, DeadlineKind, DueDate, Priority, Task, TodoList
from yatl.schema import CanonicalSchemaBundle
from yatl.selectors import resolve_task
from yatl.validation import Issue


class WebEditError(ValueError):
    """A browser edit is malformed or invalid."""


class RevisionConflict(WebEditError):
    """The canonical file changed after the browser last loaded it."""


class TodoStructureError(WebEditError):
    """The source cannot be represented by the checklist editor."""


class RepairRequiredError(WebEditError):
    """A structurally valid document has semantic errors."""

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        self.issues = issues
        super().__init__("the TODO list contains semantic validation errors")


@dataclass(frozen=True)
class DocumentSnapshot:
    document: TodoList
    revision: str
    issues: tuple[Issue, ...] = ()
    saved: bool = True
    repair_completed: bool = False


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
        repair: bool = False,
    ) -> None:
        self.path = path.resolve()
        self.application = TodoApplication(bundle)
        self.repair = repair
        self._repair_document: Optional[TodoList] = None
        self._repair_revision: Optional[str] = None

    @staticmethod
    def _revision(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def load(self) -> DocumentSnapshot:
        content = self.path.read_bytes()
        revision = self._revision(content)
        if self._repair_document is not None:
            if revision != self._repair_revision:
                raise RevisionConflict("the TODO list changed on disk; reload before continuing")
            issues = tuple(self.application.validator.validate_semantics(self._repair_document))
            return DocumentSnapshot(copy.deepcopy(self._repair_document), revision, issues, False)
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise TodoStructureError(
                f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        schema_errors = self.application.validator.validate_schema(value)
        if schema_errors:
            raise TodoStructureError(format_issues(schema_errors, value))
        document = cast(TodoList, value)
        issues = tuple(self.application.validator.validate_semantics(document))
        errors = tuple(issue for issue in issues if issue.severity == "error")
        unrepairable = tuple(issue for issue in errors if not _editor_can_repair(issue))
        if unrepairable:
            raise TodoStructureError(format_issues(unrepairable, document))
        if errors and not self.repair:
            raise RepairRequiredError(errors)
        if errors:
            self._repair_document = copy.deepcopy(document)
            self._repair_revision = revision
            return DocumentSnapshot(document, revision, issues, False)
        self.repair = False
        return DocumentSnapshot(document, revision, issues)

    def exists(self) -> bool:
        return self.path.exists()

    def creation_state(self) -> dict[str, Any]:
        return {
            "exists": False,
            "default_date": dt.date.today().isoformat(),
        }

    def create(self, target_date: str, categories: list[Category]) -> DocumentSnapshot:
        if self.path.exists():
            raise RevisionConflict("the TODO list was created elsewhere; reload before continuing")
        if not categories:
            raise WebEditError("at least one category is required")
        document = generate_document(target_date, None, categories)
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
        schema_errors = self.application.validator.validate_schema(document)
        if schema_errors:
            raise WebEditError(format_issues(schema_errors, document))
        issues = tuple(self.application.validator.validate_semantics(document))
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors and self.repair:
            self._repair_document = copy.deepcopy(document)
            self._repair_revision = expected_revision
            return DocumentSnapshot(copy.deepcopy(document), expected_revision, issues, False)
        if errors:
            raise WebEditError(format_issues(errors, document))
        content = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
        repair_completed = self.repair and self._repair_document is not None
        write_text_atomic(self.path, content.decode(), replace=True)
        self._repair_document = None
        self._repair_revision = None
        if repair_completed:
            self.repair = False
        return DocumentSnapshot(
            document,
            self._revision(content),
            issues,
            repair_completed=repair_completed,
        )

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
        description: Optional[str] = None,
    ) -> TaskCreationResult:
        created_id: Optional[str] = None

        def operation(document: TodoList) -> TodoList:
            nonlocal created_id
            before = {task["id"] for task in document["tasks"]}
            updated = self.application.add(
                document,
                AddTaskRequest(
                    name=name,
                    description=description,
                    categories=categories,
                    priority=priority,
                    dependency_of=(parent_id,) if parent_id else (),
                ),
                validate=not self.repair,
            )
            new_task = next(task for task in updated["tasks"] if task["id"] not in before)
            created_id = new_task["id"]
            self._position(
                updated, new_task["id"], parent_id, after_id, None, context_category
            )
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
            return self.application.edit(document, task_id, request, validate=not self.repair)

        return self._change(expected_revision, operation)

    def set_completed(
        self, expected_revision: str, task_id: str, completed: bool
    ) -> DocumentSnapshot:
        return self._change(
            expected_revision,
            lambda document: self.application.complete(
                document, task_id, completed, validate=not self.repair
            ),
        )

    def move_task(
        self,
        expected_revision: str,
        task_id: str,
        *,
        old_parent_id: Optional[str],
        new_parent_id: Optional[str],
        after_id: Optional[str],
        before_id: Optional[str],
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
            self._position(
                updated, task_id, new_parent_id, after_id, before_id, context_category
            )
            return updated

        return self._change(expected_revision, operation)

    def reorder_task(
        self,
        expected_revision: str,
        task_id: str,
        *,
        parent_id: Optional[str],
        category_id: Optional[str],
        offset: int,
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            if parent_id:
                siblings = resolve_task(updated, parent_id)["dependencies"]
            else:
                membership = next(
                    (item for item in updated["category_memberships"] if item["category"] == category_id),
                    None,
                )
                if membership is None:
                    raise WebEditError("root task reordering requires its displayed category")
                siblings = membership["tasks"]
            if task_id not in siblings:
                raise WebEditError("task is not in its displayed sibling list")
            index = siblings.index(task_id)
            target = max(0, min(len(siblings) - 1, index + offset))
            siblings.pop(index)
            siblings.insert(target, task_id)
            return updated

        return self._change(expected_revision, operation)

    def detach_task(
        self, expected_revision: str, task_id: str, parent_id: str
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            parent = resolve_task(updated, parent_id)
            if task_id not in parent["dependencies"]:
                raise WebEditError("task is not attached to its displayed parent")
            parent["dependencies"].remove(task_id)
            return updated

        return self._change(expected_revision, operation)

    def remove_task(self, expected_revision: str, task_id: str) -> DocumentSnapshot:
        return self._change(
            expected_revision,
            lambda document: self.application.remove(document, task_id, validate=not self.repair),
        )

    def add_category(
        self, expected_revision: str, category_id: str, display_name: str
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            updated["categories"].append({"id": category_id, "display_name": display_name.strip()})
            updated["category_memberships"].append({"category": category_id, "tasks": []})
            return updated

        return self._change(expected_revision, operation)

    def rename_category(
        self, expected_revision: str, category_id: str, display_name: str
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            category = next((item for item in updated["categories"] if item["id"] == category_id), None)
            if category is None:
                raise WebEditError(f"unknown category {category_id!r}")
            category["display_name"] = display_name.strip()
            return updated

        return self._change(expected_revision, operation)

    def move_category(
        self, expected_revision: str, category_id: str, offset: int
    ) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            index = next((i for i, item in enumerate(updated["categories"]) if item["id"] == category_id), None)
            if index is None:
                raise WebEditError(f"unknown category {category_id!r}")
            target = max(0, min(len(updated["categories"]) - 1, index + offset))
            category = updated["categories"].pop(index)
            updated["categories"].insert(target, category)
            return updated

        return self._change(expected_revision, operation)

    def remove_category(self, expected_revision: str, category_id: str) -> DocumentSnapshot:
        def operation(document: TodoList) -> TodoList:
            updated = copy.deepcopy(document)
            if len(updated["categories"]) == 1:
                raise WebEditError("a TODO list must keep at least one category")
            membership = next(
                (item for item in updated["category_memberships"] if item["category"] == category_id),
                None,
            )
            if membership is None:
                raise WebEditError(f"unknown category {category_id!r}")
            if membership["tasks"]:
                raise WebEditError("remove or reassign every task in this category first")
            updated["categories"] = [item for item in updated["categories"] if item["id"] != category_id]
            updated["category_memberships"] = [
                item for item in updated["category_memberships"] if item["category"] != category_id
            ]
            return updated

        return self._change(expected_revision, operation)

    @staticmethod
    def _position(
        document: TodoList,
        task_id: str,
        parent_id: Optional[str],
        after_id: Optional[str],
        before_id: Optional[str],
        context_category: Optional[str],
    ) -> None:
        if after_id is not None and before_id is not None:
            raise WebEditError("task placement cannot specify both before and after")
        if parent_id:
            parent = resolve_task(document, parent_id)
            if task_id in parent["dependencies"]:
                parent["dependencies"].remove(task_id)
            if before_id in parent["dependencies"]:
                position = parent["dependencies"].index(before_id)
            elif after_id in parent["dependencies"]:
                position = parent["dependencies"].index(after_id) + 1
            else:
                position = len(parent["dependencies"])
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
        if before_id in membership["tasks"]:
            position = membership["tasks"].index(before_id)
        elif after_id in membership["tasks"]:
            position = membership["tasks"].index(after_id) + 1
        else:
            position = len(membership["tasks"])
        membership["tasks"].insert(position, task_id)


def snapshot_payload(snapshot: DocumentSnapshot) -> dict[str, Any]:
    return {
        "document": snapshot.document,
        "revision": snapshot.revision,
        "issues": [
            {
                **issue.__dict__,
                "label": _model_label(issue.location, snapshot.document),
                "task_ids": _issue_task_ids(issue.location, snapshot.document),
            }
            for issue in snapshot.issues
        ],
        "saved": snapshot.saved,
        "repair_completed": snapshot.repair_completed,
    }


def format_issues(issues: list[Issue] | tuple[Issue, ...], document: object) -> str:
    lines: list[str] = []
    for issue in issues:
        label = _model_label(issue.location, document)
        lines.append(f"{label} ({issue.location}): {issue.message}" if label else f"{issue.location}: {issue.message}")
    return "\n".join(lines)


def _model_label(location: str, document: object) -> Optional[str]:
    if not isinstance(document, dict):
        return None
    for collection, singular, fields in (
        ("tasks", "Task", ("name", "id")),
        ("categories", "Category", ("display_name", "id")),
    ):
        prefix = f"$.{collection}["
        if not location.startswith(prefix):
            continue
        index_text = location[len(prefix):].split("]", 1)[0]
        try:
            item = document.get(collection, [])[int(index_text)]
        except (IndexError, TypeError, ValueError):
            return f"Unidentified {singular.lower()}"
        if isinstance(item, dict):
            for field in fields:
                value = item.get(field)
                if isinstance(value, str) and value:
                    return f'{singular} "{value}"'
        return f"Unidentified {singular.lower()}"
    return None


def _issue_task_ids(location: str, document: TodoList) -> list[str]:
    prefix = "$.tasks["
    if not location.startswith(prefix):
        return []
    try:
        task_index = int(location[len(prefix):].split("]", 1)[0])
        task = document["tasks"][task_index]
    except (IndexError, ValueError):
        return []
    result = [task["id"]]
    dependency_marker = ".dependencies["
    if dependency_marker in location:
        try:
            dependency_index = int(location.split(dependency_marker, 1)[1].split("]", 1)[0])
            dependency_id = task["dependencies"][dependency_index]
        except (IndexError, ValueError):
            return result
        if dependency_id not in result:
            result.append(dependency_id)
    return result


def _editor_can_repair(issue: Issue) -> bool:
    unrepresentable = (
        "ambiguous task ID",
        "ambiguous category ID",
        "duplicate task ID",
        "duplicate category ID",
        "duplicate category/task membership",
        "unknown task ID",
        "unknown category ID",
        "task cannot depend on itself",
    )
    return not any(text in issue.message for text in unrepresentable)

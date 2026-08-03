"""Canonical TODO-list schema and semantic validation."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource


@dataclass(frozen=True)
class Issue:
    severity: str
    location: str
    message: str


class ValidationConfigurationError(Exception):
    """The repository schemas cannot be loaded or used."""


def json_path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif isinstance(part, str) and part.replace("_", "a").isalnum():
            result += f".{part}"
        else:
            result += f"[{json.dumps(part)}]"
    return result


class CanonicalTodoValidator:
    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir.resolve()
        self.schemas = self._load_schemas()
        self._validate_local_references()
        self.priority_order = self._load_priority_order()
        resources = [
            (schema["$id"], Resource.from_contents(schema))
            for schema in self.schemas.values()
        ]
        registry = Registry().with_resources(resources)
        self.validator = Draft202012Validator(
            self.schemas["todo-list.schema.json"],
            registry=registry,
            format_checker=FormatChecker(),
        )

    def _load_schemas(self) -> dict[str, dict[str, Any]]:
        required = {
            "category.schema.json",
            "due-date.schema.json",
            "priority.schema.json",
            "task.schema.json",
            "todo-list.schema.json",
        }
        schemas: dict[str, dict[str, Any]] = {}
        for name in sorted(required):
            path = self.schema_dir / name
            try:
                schema = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationConfigurationError(f"cannot load {path}: {exc}") from exc
            if not isinstance(schema, dict):
                raise ValidationConfigurationError(f"{path}: schema must be an object")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ValidationConfigurationError(f"{path}: invalid schema: {exc.message}") from exc
            if not isinstance(schema.get("$id"), str):
                raise ValidationConfigurationError(f"{path}: schema requires a string $id")
            schemas[name] = schema
        return schemas

    def _validate_local_references(self) -> None:
        for source_name, schema in self.schemas.items():
            stack: list[Any] = [schema]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    reference = value.get("$ref")
                    if isinstance(reference, str):
                        file_name, separator, fragment = reference.partition("#")
                        target_name = file_name or source_name
                        if "://" in target_name or Path(target_name).name != target_name:
                            raise ValidationConfigurationError(
                                f"{source_name}: schema references must be local filenames"
                            )
                        if target_name not in self.schemas:
                            raise ValidationConfigurationError(
                                f"{source_name}: unresolved schema reference {reference!r}"
                            )
                        target: Any = self.schemas[target_name]
                        if separator and fragment:
                            if not fragment.startswith("/"):
                                raise ValidationConfigurationError(
                                    f"{source_name}: unsupported schema reference {reference!r}"
                                )
                            for raw_part in fragment[1:].split("/"):
                                part = raw_part.replace("~1", "/").replace("~0", "~")
                                if not isinstance(target, dict) or part not in target:
                                    raise ValidationConfigurationError(
                                        f"{source_name}: unresolved schema reference {reference!r}"
                                    )
                                target = target[part]
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)

    def _load_priority_order(self) -> dict[str, int]:
        schema = self.schemas["priority.schema.json"]
        values = schema.get("enum")
        ordered = schema.get("x-order")
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValidationConfigurationError("priority.schema.json: enum must contain strings")
        if not isinstance(ordered, list) or not all(isinstance(item, str) for item in ordered):
            raise ValidationConfigurationError("priority.schema.json: x-order must contain strings")
        if len(ordered) != len(set(ordered)) or set(ordered) != set(values):
            raise ValidationConfigurationError(
                "priority.schema.json: x-order must contain each enum value exactly once"
            )
        return {name: rank for rank, name in enumerate(ordered)}

    def validate(self, document: Any) -> list[Issue]:
        issues = [
            Issue("error", json_path(error.absolute_path), error.message)
            for error in sorted(
                self.validator.iter_errors(document),
                key=lambda item: (list(item.absolute_path), item.message),
            )
        ]
        if issues or not isinstance(document, dict):
            return issues
        issues.extend(self._validate_semantics(document))
        return sorted(issues, key=lambda issue: (issue.location, issue.severity, issue.message))

    def _validate_semantics(self, document: dict[str, Any]) -> list[Issue]:
        issues: list[Issue] = []
        tasks: list[dict[str, Any]] = document["tasks"]
        categories: list[dict[str, Any]] = document["categories"]
        memberships: list[dict[str, Any]] = document["category_memberships"]

        task_indexes = self._indexes(tasks, "id")
        category_indexes = self._indexes(categories, "id")
        issues.extend(self._duplicate_id_issues(task_indexes, "tasks", "task"))
        issues.extend(self._duplicate_id_issues(category_indexes, "categories", "category"))

        task_by_id = {
            task_id: tasks[indexes[0]]
            for task_id, indexes in task_indexes.items()
            if len(indexes) == 1
        }
        category_by_id = {
            category_id: categories[indexes[0]]
            for category_id, indexes in category_indexes.items()
            if len(indexes) == 1
        }

        for index, task in enumerate(tasks):
            task_id = task["id"]
            if "priority" not in task:
                issues.append(Issue("warning", f"$.tasks[{index}].priority", "task has no priority"))
            issues.extend(self._validate_due_date(task, index))
            for dep_index, dependency_id in enumerate(task["dependencies"]):
                location = f"$.tasks[{index}].dependencies[{dep_index}]"
                if dependency_id == task_id:
                    issues.append(Issue("error", location, "task cannot depend on itself"))
                    continue
                matches = task_indexes.get(dependency_id, [])
                if not matches:
                    issues.append(Issue("error", location, f"unknown task ID {dependency_id!r}"))
                    continue
                if len(matches) > 1:
                    issues.append(Issue("error", location, f"ambiguous task ID {dependency_id!r}"))
                    continue
                dependency = tasks[matches[0]]
                if task["completed"] and not dependency["completed"]:
                    issues.append(
                        Issue("error", location, "completed task has an incomplete dependency")
                    )
                if "priority" in task and "priority" in dependency:
                    task_rank = self.priority_order[task["priority"]]
                    dependency_rank = self.priority_order[dependency["priority"]]
                    if dependency_rank < task_rank:
                        issues.append(
                            Issue(
                                "error",
                                location,
                                f"dependency priority {dependency['priority']!r} is higher than "
                                f"task priority {task['priority']!r}",
                            )
                        )

        issues.extend(self._dependency_cycle_issues(task_by_id, task_indexes))

        category_tasks: dict[str, set[str]] = {category_id: set() for category_id in category_by_id}
        task_categories: dict[str, set[str]] = {task_id: set() for task_id in task_by_id}
        seen_memberships: set[tuple[str, str]] = set()
        for membership_index, membership in enumerate(memberships):
            category_id = membership["category"]
            category_matches = category_indexes.get(category_id, [])
            category_location = f"$.category_memberships[{membership_index}].category"
            if not category_matches:
                issues.append(Issue("error", category_location, f"unknown category ID {category_id!r}"))
            elif len(category_matches) > 1:
                issues.append(Issue("error", category_location, f"ambiguous category ID {category_id!r}"))
            for task_position, task_id in enumerate(membership["tasks"]):
                location = f"$.category_memberships[{membership_index}].tasks[{task_position}]"
                task_matches = task_indexes.get(task_id, [])
                if not task_matches:
                    issues.append(Issue("error", location, f"unknown task ID {task_id!r}"))
                    continue
                if len(task_matches) > 1:
                    issues.append(Issue("error", location, f"ambiguous task ID {task_id!r}"))
                    continue
                if len(category_matches) != 1:
                    continue
                association = (category_id, task_id)
                if association in seen_memberships:
                    issues.append(
                        Issue("error", location, "duplicate category/task membership")
                    )
                    continue
                seen_memberships.add(association)
                category_tasks[category_id].add(task_id)
                task_categories[task_id].add(category_id)

        for category_id, task_ids in category_tasks.items():
            if not task_ids:
                index = category_indexes[category_id][0]
                issues.append(Issue("warning", f"$.categories[{index}]", "category is empty"))
        for task_id, category_ids in task_categories.items():
            index = task_indexes[task_id][0]
            if not category_ids:
                issues.append(Issue("warning", f"$.tasks[{index}]", "task has no category"))
            elif len(category_ids) > 1:
                issues.append(
                    Issue(
                        "warning",
                        f"$.tasks[{index}]",
                        f"task belongs to multiple categories: {sorted(category_ids)}",
                    )
                )

        display_names: dict[str, list[int]] = {}
        for index, category in enumerate(categories):
            display_names.setdefault(category["display_name"], []).append(index)
        for name, indexes in display_names.items():
            if len(indexes) > 1:
                for index in indexes[1:]:
                    issues.append(
                        Issue(
                            "warning",
                            f"$.categories[{index}].display_name",
                            f"duplicate category display name {name!r}",
                        )
                    )
        return issues

    @staticmethod
    def _indexes(values: Sequence[dict[str, Any]], field: str) -> dict[str, list[int]]:
        result: dict[str, list[int]] = {}
        for index, value in enumerate(values):
            result.setdefault(value[field], []).append(index)
        return result

    @staticmethod
    def _duplicate_id_issues(
        indexes: dict[str, list[int]], collection: str, kind: str
    ) -> list[Issue]:
        result: list[Issue] = []
        for value, positions in indexes.items():
            if len(positions) > 1:
                for position in positions:
                    result.append(
                        Issue(
                            "error",
                            f"$.{collection}[{position}].id",
                            f"duplicate {kind} ID {value!r}",
                        )
                    )
        return result

    @staticmethod
    def _validate_due_date(task: dict[str, Any], task_index: int) -> list[Issue]:
        if "due" not in task:
            return []
        due = task["due"]
        try:
            dt.date(due["year"], due.get("month", 1), due.get("day", 1))
        except ValueError as exc:
            return [Issue("error", f"$.tasks[{task_index}].due", f"invalid calendar date: {exc}")]
        return []

    @staticmethod
    def _dependency_cycle_issues(
        task_by_id: dict[str, dict[str, Any]], task_indexes: dict[str, list[int]]
    ) -> list[Issue]:
        issues: list[Issue] = []
        state: dict[str, int] = {}
        stack: list[str] = []
        reported: set[tuple[str, ...]] = set()

        def visit(task_id: str) -> None:
            state[task_id] = 1
            stack.append(task_id)
            for dependency_id in task_by_id[task_id]["dependencies"]:
                if dependency_id not in task_by_id or dependency_id == task_id:
                    continue
                if state.get(dependency_id, 0) == 0:
                    visit(dependency_id)
                elif state.get(dependency_id) == 1:
                    start = stack.index(dependency_id)
                    cycle = tuple(stack[start:] + [dependency_id])
                    normalized = min(
                        tuple(cycle[index:-1] + cycle[:index] + (cycle[index],))
                        for index in range(len(cycle) - 1)
                    )
                    if normalized not in reported:
                        reported.add(normalized)
                        index = task_indexes[task_id][0]
                        issues.append(
                            Issue(
                                "error",
                                f"$.tasks[{index}].dependencies",
                                f"dependency cycle: {' -> '.join(cycle)}",
                            )
                        )
            stack.pop()
            state[task_id] = 2

        for task_id in task_by_id:
            if state.get(task_id, 0) == 0:
                visit(task_id)
        return issues


def validate_completion_observations(
    observations: Iterable[tuple[str, bool, str]],
) -> list[Issue]:
    """Reject conflicting rendered checkbox states for the same canonical task."""
    first: dict[str, tuple[bool, str]] = {}
    issues: list[Issue] = []
    for task_id, completed, location in observations:
        if task_id not in first:
            first[task_id] = (completed, location)
            continue
        prior_completed, prior_location = first[task_id]
        if completed != prior_completed:
            issues.append(
                Issue(
                    "error",
                    location,
                    f"checkbox state conflicts with {prior_location} for task {task_id!r}",
                )
            )
    return issues

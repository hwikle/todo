"""Load and compile the canonical JSON Schema bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from todo_priority import PriorityConfigurationError, PriorityPolicy, priority_policy_from_schema


class SchemaConfigurationError(Exception):
    """Canonical schema resources cannot be loaded or compiled."""


class CanonicalSchemaBundle:
    REQUIRED = {
        "category.schema.json",
        "due-date.schema.json",
        "priority.schema.json",
        "task-id.schema.json",
        "task.schema.json",
        "todo-list.schema.json",
    }

    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir.resolve()
        self.schemas = self._load_schemas()
        self._validate_local_references()
        try:
            self.priority_policy = priority_policy_from_schema(
                self.schemas["priority.schema.json"]
            )
        except PriorityConfigurationError as exc:
            raise SchemaConfigurationError(str(exc)) from exc
        resources = [
            (schema["$id"], Resource.from_contents(schema))
            for schema in self.schemas.values()
        ]
        self.registry = Registry().with_resources(resources)
        self.validator = Draft202012Validator(
            self.schemas["todo-list.schema.json"],
            registry=self.registry,
            format_checker=FormatChecker(),
        )

    def validator_for(self, schema_name: str) -> Draft202012Validator:
        try:
            schema = self.schemas[schema_name]
        except KeyError as exc:
            raise SchemaConfigurationError(f"unknown canonical schema {schema_name!r}") from exc
        return Draft202012Validator(
            schema,
            registry=self.registry,
            format_checker=FormatChecker(),
        )

    def _load_schemas(self) -> dict[str, dict[str, Any]]:
        schemas: dict[str, dict[str, Any]] = {}
        for name in sorted(self.REQUIRED):
            path = self.schema_dir / name
            try:
                schema = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise SchemaConfigurationError(f"cannot load {path}: {exc}") from exc
            if not isinstance(schema, dict):
                raise SchemaConfigurationError(f"{path}: schema must be an object")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise SchemaConfigurationError(
                    f"{path}: invalid schema: {exc.message}"
                ) from exc
            if not isinstance(schema.get("$id"), str):
                raise SchemaConfigurationError(f"{path}: schema requires a string $id")
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
                            raise SchemaConfigurationError(
                                f"{source_name}: schema references must be local filenames"
                            )
                        if target_name not in self.schemas:
                            raise SchemaConfigurationError(
                                f"{source_name}: unresolved schema reference {reference!r}"
                            )
                        target: Any = self.schemas[target_name]
                        if separator and fragment:
                            if not fragment.startswith("/"):
                                raise SchemaConfigurationError(
                                    f"{source_name}: unsupported schema reference {reference!r}"
                                )
                            for raw_part in fragment[1:].split("/"):
                                part = raw_part.replace("~1", "/").replace("~0", "~")
                                if not isinstance(target, dict) or part not in target:
                                    raise SchemaConfigurationError(
                                        f"{source_name}: unresolved schema reference {reference!r}"
                                    )
                                target = target[part]
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)

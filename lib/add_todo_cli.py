#!/usr/bin/env python3
"""Add one task to a canonical JSON TODO list."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
from typing import Optional, cast

from todo_add import TaskAdditionError, add_task
from todo_ids import TaskIdGenerationError
from todo_io import load_json, write_text_atomic
from todo_model import DeadlineKind, DueDate, Priority, TodoList
from todo_schema import CanonicalSchemaBundle, SchemaConfigurationError


ROOT = Path(__file__).resolve().parent.parent
DUE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$")


def deadline_kinds(bundle: CanonicalSchemaBundle) -> list[str]:
    values = bundle.schemas["task.schema.json"]["properties"]["deadline_kind"]["enum"]
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise SchemaConfigurationError("task.schema.json: deadline_kind enum must contain strings")
    return values


def parser(bundle: CanonicalSchemaBundle) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("name")
    result.add_argument("--output", type=Path, default=Path("todo.json"))
    result.add_argument("--description")
    result.add_argument("--category", action="append", required=True)
    result.add_argument("--priority", choices=bundle.priority_policy.order)
    result.add_argument("--depends-on", action="append", default=[])
    result.add_argument("--due", help="YYYY, YYYY-MM, or YYYY-MM-DD")
    result.add_argument("--due-time", help="HH:MM; requires a complete due date")
    result.add_argument("--deadline-kind", choices=deadline_kinds(bundle))
    return result


def parse_due(value: str | None, time: str | None) -> DueDate | None:
    if value is None:
        if time is not None:
            raise TaskAdditionError("--due-time requires --due")
        return None
    match = DUE_RE.fullmatch(value)
    if match is None:
        raise TaskAdditionError("--due must use YYYY, YYYY-MM, or YYYY-MM-DD")
    due: DueDate = {"year": int(match.group("year"))}
    if match.group("month") is not None:
        due["month"] = int(match.group("month"))
    if match.group("day") is not None:
        due["day"] = int(match.group("day"))
    try:
        dt.date(due["year"], due.get("month", 1), due.get("day", 1))
    except ValueError as exc:
        raise TaskAdditionError(f"invalid due date: {exc}") from exc
    if time is not None:
        if "day" not in due:
            raise TaskAdditionError("--due-time requires a complete YYYY-MM-DD due date")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            raise TaskAdditionError("--due-time must use HH:MM")
        due["time"] = time
    return due


def main() -> int:
    try:
        bundle = CanonicalSchemaBundle(ROOT / "schema")
        args = parser(bundle).parse_args()
        path = args.output.resolve()
        if not path.is_file():
            raise TaskAdditionError(f"canonical TODO list does not exist: {path}")
        document = cast(TodoList, load_json(path))
        due = parse_due(args.due, args.due_time)
        if (due is None) != (args.deadline_kind is None):
            raise TaskAdditionError("--due and --deadline-kind must be provided together")
        added = add_task(
            document,
            name=args.name,
            category_selectors=args.category,
            priority_policy=bundle.priority_policy,
            priority=cast(Optional[Priority], args.priority),
            description=args.description,
            dependency_selectors=args.depends_on,
            due=due,
            deadline_kind=cast(Optional[DeadlineKind], args.deadline_kind),
        )
        task_errors = sorted(
            bundle.validator_for("task.schema.json").iter_errors(added.task),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if task_errors:
            raise TaskAdditionError(f"new task is invalid: {task_errors[0].message}")
        content = json.dumps(added.document, indent=2, ensure_ascii=False) + "\n"
        write_text_atomic(path, content)
    except (
        OSError,
        json.JSONDecodeError,
        SchemaConfigurationError,
        TaskAdditionError,
        TaskIdGenerationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

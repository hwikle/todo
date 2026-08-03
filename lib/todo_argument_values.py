"""Shared parsing of schema-backed command-line values."""

from __future__ import annotations

import datetime as dt
import re

from todo_add import TaskAdditionError
from todo_model import DueDate
from todo_schema import CanonicalSchemaBundle, SchemaConfigurationError


DUE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$")


def deadline_kinds(bundle: CanonicalSchemaBundle) -> list[str]:
    values = bundle.schemas["task.schema.json"]["properties"]["deadline_kind"]["enum"]
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise SchemaConfigurationError("task.schema.json: deadline_kind enum must contain strings")
    return values


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

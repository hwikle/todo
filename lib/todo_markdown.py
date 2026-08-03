"""Parse legacy daily Markdown into canonical TODO-list JSON."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, cast

from todo_model import (
    Category,
    CategoryMembership,
    DeadlineKind,
    DueDate,
    Priority,
    Task,
    TodoList,
)


TITLE_RE = re.compile(r"^# (?P<label>.+?) — (?P<date>\d{4}-\d{2}-\d{2})$")
PRIORITY_RE = re.compile(r"^## (?P<label>.+?)\s*$")
TASK_RE = re.compile(
    r"^(?P<indent> *)- \[(?P<check>[ xX])\] (?P<name>.+?)"
    r"(?:\s+<!--\s*(?P<meta>.*?)\s*-->)?\s*$"
)


class MarkdownConversionError(Exception):
    """A Markdown source cannot be converted without guessing."""


@dataclass
class ParsedTask:
    task_id: str
    name: str
    completed: bool
    priority: Priority
    source: str
    description: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    due: Optional[DueDate] = None
    deadline_kind: Optional[DeadlineKind] = None

    def canonical(self) -> Task:
        result: Task = {
            "id": self.task_id,
            "name": self.name,
            "priority": self.priority,
            "completed": self.completed,
            "dependencies": list(self.dependencies),
        }
        if self.description:
            result["description"] = "\n".join(self.description)
        if self.due is not None:
            result["due"] = self.due
            if self.deadline_kind is not None:
                result["deadline_kind"] = self.deadline_kind
        return result


class FreshIdSource:
    def __init__(self, generator: Optional[Callable[[], str]] = None) -> None:
        self.generator = generator or (lambda: uuid.uuid4().hex[:12])
        self.seen: set[str] = set()

    def next(self) -> str:
        for _ in range(1000):
            candidate = self.generator()
            if re.fullmatch(r"[0-9a-f]{12}", candidate) and candidate not in self.seen:
                self.seen.add(candidate)
                return candidate
        raise MarkdownConversionError("could not generate a unique 12-character task ID")


def parse_metadata(value: str, source: Path, line_number: int) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for token in value.split():
        if ":" not in token:
            raise MarkdownConversionError(
                f"{source}:{line_number}: malformed task metadata {token!r}"
            )
        key, item = token.split(":", 1)
        if key in metadata:
            raise MarkdownConversionError(
                f"{source}:{line_number}: duplicate metadata key {key!r}"
            )
        metadata[key] = item
    unknown = set(metadata) - {"task", "due", "time", "due-kind"}
    if unknown:
        raise MarkdownConversionError(
            f"{source}:{line_number}: unknown task metadata {sorted(unknown)}"
        )
    return metadata


def canonical_due(
    metadata: dict[str, str], source: Path, line_number: int
) -> tuple[Optional[DueDate], Optional[DeadlineKind]]:
    due_value = metadata.get("due")
    due_time = metadata.get("time")
    deadline_kind = metadata.get("due-kind")
    if due_time and not due_value:
        raise MarkdownConversionError(f"{source}:{line_number}: time requires a due date")
    if deadline_kind and not due_value:
        raise MarkdownConversionError(f"{source}:{line_number}: deadline kind requires a due date")
    if due_value and not deadline_kind:
        raise MarkdownConversionError(f"{source}:{line_number}: due date requires a deadline kind")
    if deadline_kind not in {None, "hard", "soft"}:
        raise MarkdownConversionError(
            f"{source}:{line_number}: unknown deadline kind {deadline_kind!r}"
        )
    if not due_value:
        return None, None
    try:
        parsed = dt.date.fromisoformat(due_value)
    except ValueError as exc:
        raise MarkdownConversionError(
            f"{source}:{line_number}: invalid due date {due_value!r}"
        ) from exc
    due: DueDate = {
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
    }
    if due_time:
        try:
            dt.time.fromisoformat(due_time)
        except ValueError as exc:
            raise MarkdownConversionError(
                f"{source}:{line_number}: invalid due time {due_time!r}"
            ) from exc
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", due_time):
            raise MarkdownConversionError(
                f"{source}:{line_number}: due time must use HH:MM"
            )
        due["time"] = due_time
    return due, cast(Optional[DeadlineKind], deadline_kind)


def parse_category_file(
    path: Path,
    expected_date: str,
    priorities: dict[str, Priority],
    ids: FreshIdSource,
) -> tuple[Category, list[ParsedTask]]:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise MarkdownConversionError(f"cannot read {path}: {exc}") from exc
    if not lines:
        raise MarkdownConversionError(f"{path}:1: missing category title")
    title = TITLE_RE.fullmatch(lines[0])
    if not title:
        raise MarkdownConversionError(
            f"{path}:1: expected '# Category — YYYY-MM-DD'"
        )
    if title.group("date") != expected_date:
        raise MarkdownConversionError(
            f"{path}:1: title date {title.group('date')} does not match {expected_date}"
        )

    category = {"id": path.stem, "display_name": title.group("label")}
    tasks: list[ParsedTask] = []
    stack: list[tuple[int, ParsedTask]] = []
    current_priority: Optional[str] = None
    seen_priorities: set[str] = set()

    for line_number, line in enumerate(lines[1:], 2):
        if "\t" in line:
            raise MarkdownConversionError(f"{path}:{line_number}: tabs are not allowed")
        heading = PRIORITY_RE.fullmatch(line)
        if heading:
            label = heading.group("label").strip()
            key = label.casefold()
            if key not in priorities:
                raise MarkdownConversionError(f"{path}:{line_number}: unknown priority {label!r}")
            current_priority = priorities[key]
            if current_priority in seen_priorities:
                raise MarkdownConversionError(
                    f"{path}:{line_number}: duplicate priority heading {label!r}"
                )
            seen_priorities.add(current_priority)
            stack.clear()
            continue

        match = TASK_RE.fullmatch(line)
        if match:
            if current_priority is None:
                raise MarkdownConversionError(
                    f"{path}:{line_number}: task appears before a priority heading"
                )
            indent = len(match.group("indent"))
            if indent % 4:
                raise MarkdownConversionError(
                    f"{path}:{line_number}: task indentation must use groups of four spaces"
                )
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if indent and (not stack or stack[-1][0] != indent - 4):
                raise MarkdownConversionError(
                    f"{path}:{line_number}: task indentation skips a nesting level"
                )
            metadata = parse_metadata(match.group("meta") or "", path, line_number)
            due, deadline_kind = canonical_due(metadata, path, line_number)
            parsed = ParsedTask(
                task_id=ids.next(),
                name=match.group("name").strip(),
                completed=match.group("check").lower() == "x",
                priority=current_priority,
                source=f"{path}:{line_number}",
                due=due,
                deadline_kind=deadline_kind,
            )
            if not parsed.name:
                raise MarkdownConversionError(f"{path}:{line_number}: task name cannot be empty")
            if stack:
                stack[-1][1].dependencies.append(parsed.task_id)
            tasks.append(parsed)
            stack.append((indent, parsed))
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("#"):
            raise MarkdownConversionError(f"{path}:{line_number}: unsupported heading {stripped!r}")
        if not stack:
            raise MarkdownConversionError(
                f"{path}:{line_number}: text is not attached to a task"
            )
        indent = len(line) - len(line.lstrip(" "))
        if indent < stack[-1][0] + 4:
            raise MarkdownConversionError(
                f"{path}:{line_number}: task details must be indented four spaces"
            )
        if stripped.startswith("Due: "):
            if stack[-1][1].due is None:
                raise MarkdownConversionError(
                    f"{path}:{line_number}: visible due text lacks structured due metadata"
                )
            continue
        stack[-1][1].description.append(stripped)
    return category, tasks


def convert_daily_directory(
    source: Path,
    priority_values: list[Priority],
    id_generator: Optional[Callable[[], str]] = None,
) -> TodoList:
    source = source.resolve()
    try:
        date = dt.date.fromisoformat(source.name).isoformat()
    except ValueError as exc:
        raise MarkdownConversionError(
            f"{source}: directory name must be an ISO date"
        ) from exc
    if not source.is_dir():
        raise MarkdownConversionError(f"{source}: source must be a directory")
    files = sorted(source.glob("*.md"))
    if not files:
        raise MarkdownConversionError(f"{source}: no category Markdown files found")
    priorities = {value.casefold(): value for value in priority_values}
    ids = FreshIdSource(id_generator)
    categories: list[Category] = []
    canonical_tasks: list[Task] = []
    memberships: list[CategoryMembership] = []
    for path in files:
        category, tasks = parse_category_file(path, date, priorities, ids)
        categories.append(category)
        task_ids = [task.task_id for task in tasks]
        canonical_tasks.extend(task.canonical() for task in tasks)
        memberships.append({"category": category["id"], "tasks": task_ids})
    return {
        "date": date,
        "tasks": canonical_tasks,
        "categories": categories,
        "category_memberships": memberships,
    }

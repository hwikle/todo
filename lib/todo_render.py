"""Render canonical TODO-list JSON as deterministic, ID-free Markdown views."""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedOccurrence:
    task_id: str
    completed: bool
    line: int


@dataclass(frozen=True)
class RenderedMarkdown:
    content: str
    occurrences: tuple[RenderedOccurrence, ...]


def priority_label(priority: str) -> str:
    return priority.capitalize()


def due_metadata(task: dict[str, Any]) -> str:
    due = task["due"]
    values = [
        f"due:{due['year']:04d}",
    ]
    if "month" in due:
        values[0] += f"-{due['month']:02d}"
    if "day" in due:
        values[0] += f"-{due['day']:02d}"
    if "time" in due:
        values.append(f"time:{due['time']}")
    values.append(f"due-kind:{task['deadline_kind']}")
    return f" <!-- {' '.join(values)} -->"


def due_display(task: dict[str, Any]) -> str:
    due = task["due"]
    if "day" in due:
        value = f"{calendar.month_name[due['month']]} {due['day']}, {due['year']}"
    elif "month" in due:
        value = f"{calendar.month_name[due['month']]} {due['year']}"
    else:
        value = str(due["year"])
    if "time" in due:
        parsed = dt.time.fromisoformat(due["time"])
        value += f" at {parsed.strftime('%I:%M %p').lstrip('0')}"
    kind = "Hard deadline" if task["deadline_kind"] == "hard" else "Soft deadline"
    return f"Due: {value} — {kind}."


def render_document(
    document: dict[str, Any], priority_order: list[str]
) -> dict[str, RenderedMarkdown]:
    tasks = {task["id"]: task for task in document["tasks"]}
    memberships = {
        membership["category"]: membership["tasks"]
        for membership in document["category_memberships"]
    }
    result: dict[str, RenderedMarkdown] = {}
    for category in document["categories"]:
        lines = [f"# {category['display_name']} — {document['date']}", ""]
        occurrences: list[RenderedOccurrence] = []
        member_ids = memberships.get(category["id"], [])
        section_order = list(priority_order)
        if any("priority" not in tasks[task_id] for task_id in member_ids):
            section_order.append("unprioritized")
        for priority in section_order:
            heading = "Unprioritized" if priority == "unprioritized" else priority_label(priority)
            lines.extend([f"## {heading}", ""])
            for task_id in member_ids:
                task = tasks[task_id]
                task_priority = task.get("priority", "unprioritized")
                if task_priority != priority:
                    continue
                _render_task(
                    task,
                    tasks,
                    lines,
                    occurrences,
                    depth=0,
                    section_priority=priority,
                )
                lines.append("")
        result[f"{category['id']}.md"] = RenderedMarkdown(
            content="\n".join(lines).rstrip() + "\n",
            occurrences=tuple(occurrences),
        )
    return result


def _render_task(
    task: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    lines: list[str],
    occurrences: list[RenderedOccurrence],
    depth: int,
    section_priority: str,
) -> None:
    indent = "    " * depth
    mark = "x" if task["completed"] else " "
    annotation = ""
    task_priority = task.get("priority")
    if depth and task_priority != section_priority:
        label = "Unprioritized" if task_priority is None else priority_label(task_priority)
        annotation = f" — {label}"
    metadata = due_metadata(task) if "due" in task else ""
    lines.append(f"{indent}- [{mark}] {task['name']}{annotation}{metadata}")
    occurrences.append(
        RenderedOccurrence(task_id=task["id"], completed=task["completed"], line=len(lines))
    )
    continuation = indent + "    "
    if "due" in task:
        lines.append(f"{continuation}{due_display(task)}")
    if "description" in task:
        for description_line in task["description"].splitlines():
            lines.append(f"{continuation}{description_line}")
    for dependency_id in task["dependencies"]:
        _render_task(
            tasks[dependency_id],
            tasks,
            lines,
            occurrences,
            depth + 1,
            section_priority,
        )

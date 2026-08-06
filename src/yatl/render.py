"""Render canonical TODO-list JSON as deterministic, ID-free Markdown views."""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from yatl.graph import TaskGraph, category_roots
from yatl.model import Priority, Task, TodoList


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


def due_display(task: Task) -> str:
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
    document: TodoList, priority_order: list[Priority]
) -> dict[str, RenderedMarkdown]:
    graph = TaskGraph(document["tasks"])
    memberships = {
        membership["category"]: membership["tasks"]
        for membership in document["category_memberships"]
    }
    result: dict[str, RenderedMarkdown] = {}
    for category in document["categories"]:
        lines = [f"# {category['display_name']} — {document['date']}", ""]
        occurrences: list[RenderedOccurrence] = []
        member_ids = memberships.get(category["id"], [])
        root_ids = category_roots(graph, member_ids)
        section_order: list[str] = list(priority_order)
        if any("priority" not in graph.task(task_id) for task_id in root_ids):
            section_order.append("unprioritized")
        for priority in section_order:
            heading = "Unprioritized" if priority == "unprioritized" else priority_label(priority)
            lines.extend([f"## {heading}", ""])
            for task_id in root_ids:
                task = graph.task(task_id)
                task_priority = task.get("priority", "unprioritized")
                if task_priority != priority:
                    continue
                _render_task(
                    task,
                    graph,
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


def combine_rendered(rendered: dict[str, RenderedMarkdown]) -> str:
    """Combine category views in canonical category order."""
    return "\n---\n\n".join(
        view.content.rstrip() for view in rendered.values()
    ) + "\n"


def _render_task(
    task: Task,
    graph: TaskGraph,
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
    lines.append(f"{indent}- [{mark}] {task['name']}{annotation}")
    occurrences.append(
        RenderedOccurrence(task_id=task["id"], completed=task["completed"], line=len(lines))
    )
    continuation = indent + "    "
    if "due" in task:
        lines.append(f"{continuation}{due_display(task)}")
    if "description" in task:
        for description_line in task["description"].splitlines():
            lines.append(f"{continuation}{description_line}")
    for dependency_id in graph.dependencies(task["id"]):
        _render_task(
            graph.task(dependency_id),
            graph,
            lines,
            occurrences,
            depth + 1,
            section_priority,
        )

"""Synchronize checkbox-only Markdown edits into canonical TODO JSON."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from todo_model import TodoList
from todo_render import RenderedMarkdown
from todo_validation import Issue, validate_completion_observations


CHECKBOX_RE = re.compile(r"^(?P<prefix>\s*- \[)(?P<check>[ xX])(?P<suffix>\] .*)$")


@dataclass(frozen=True)
class SyncResult:
    document: TodoList
    changed_task_ids: tuple[str, ...]
    issues: tuple[Issue, ...]


def synchronize_views(
    document: TodoList,
    rendered: dict[str, RenderedMarkdown],
    view_dir: Path,
) -> SyncResult:
    issues: list[Issue] = []
    expected_names = set(rendered)
    actual_names = {path.name for path in view_dir.glob("*.md")}
    for missing in sorted(expected_names - actual_names):
        issues.append(Issue("error", str(view_dir / missing), "rendered category file is missing"))
    for extra in sorted(actual_names - expected_names):
        issues.append(Issue("error", str(view_dir / extra), "unexpected Markdown file"))
    if issues:
        return SyncResult(document, (), tuple(issues))

    observations: list[tuple[str, bool, str]] = []
    for name, expected in rendered.items():
        path = view_dir / name
        try:
            actual_lines = path.read_text().splitlines()
        except OSError as exc:
            issues.append(Issue("error", str(path), f"cannot read rendered view: {exc}"))
            continue
        expected_lines = expected.content.splitlines()
        if len(actual_lines) != len(expected_lines):
            issues.append(
                Issue(
                    "error",
                    str(path),
                    f"structure differs: expected {len(expected_lines)} lines, got {len(actual_lines)}",
                )
            )
            continue
        occurrence_by_line = {occurrence.line: occurrence for occurrence in expected.occurrences}
        for line_number, (expected_line, actual_line) in enumerate(
            zip(expected_lines, actual_lines), 1
        ):
            occurrence = occurrence_by_line.get(line_number)
            if occurrence is None:
                if actual_line != expected_line:
                    issues.append(
                        Issue(
                            "error",
                            f"{path}:{line_number}",
                            "non-checkbox content differs from the canonical render",
                        )
                    )
                continue
            expected_match = CHECKBOX_RE.fullmatch(expected_line)
            actual_match = CHECKBOX_RE.fullmatch(actual_line)
            if not expected_match or not actual_match:
                issues.append(
                    Issue(
                        "error",
                        f"{path}:{line_number}",
                        "task line no longer has the canonical checkbox structure",
                    )
                )
                continue
            if (
                expected_match.group("prefix") != actual_match.group("prefix")
                or expected_match.group("suffix") != actual_match.group("suffix")
            ):
                issues.append(
                    Issue(
                        "error",
                        f"{path}:{line_number}",
                        "task content differs from the canonical render",
                    )
                )
                continue
            observations.append(
                (
                    occurrence.task_id,
                    actual_match.group("check").lower() == "x",
                    f"{path}:{line_number}",
                )
            )
    issues.extend(validate_completion_observations(observations))
    if issues:
        return SyncResult(document, (), tuple(issues))

    states: dict[str, bool] = {}
    for task_id, completed, _location in observations:
        states[task_id] = completed
    updated = copy.deepcopy(document)
    changed: list[str] = []
    for task in updated["tasks"]:
        if task["id"] in states and task["completed"] != states[task["id"]]:
            task["completed"] = states[task["id"]]
            changed.append(task["id"])
    return SyncResult(updated, tuple(changed), ())

#!/usr/bin/env python3
"""Synchronize checkbox-only rendered Markdown edits into canonical JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from todo_render import render_document
from todo_sync import synchronize_views
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("todo_list", type=Path, help="canonical TODO-list JSON")
    result.add_argument("--view-dir", type=Path, help="rendered Markdown directory")
    result.add_argument("--strict", action="store_true", help="treat warnings as errors")
    return result


def write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def print_issues(issues: list, strict: bool) -> bool:
    failed = False
    for issue in issues:
        effective = "error" if strict and issue.severity == "warning" else issue.severity
        suffix = " (strict)" if effective != issue.severity else ""
        print(f"{issue.location}: {effective}{suffix}: {issue.message}", file=sys.stderr)
        failed = failed or effective == "error"
    return failed


def main() -> int:
    args = parser().parse_args()
    try:
        document = json.loads(args.todo_list.read_text())
        validator = CanonicalTodoValidator(ROOT / "schema")
    except (OSError, json.JSONDecodeError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    source_issues = validator.validate(document)
    if print_issues(source_issues, args.strict):
        print("Synchronization stopped because canonical JSON is invalid.", file=sys.stderr)
        return 1

    rendered = render_document(document, list(validator.priority_order))
    view_dir = (args.view_dir or args.todo_list.parent).resolve()
    result = synchronize_views(document, rendered, view_dir)
    if print_issues(list(result.issues), args.strict):
        print("Synchronization failed; canonical JSON was not changed.", file=sys.stderr)
        return 1
    updated_issues = validator.validate(result.document)
    if print_issues(updated_issues, args.strict):
        print("Synchronized state is invalid; canonical JSON was not changed.", file=sys.stderr)
        return 1
    if not result.changed_task_ids:
        print("Checkboxes already match canonical JSON; no changes made.")
        return 0
    try:
        write_atomic(
            args.todo_list,
            json.dumps(result.document, indent=2, ensure_ascii=False) + "\n",
        )
    except OSError as exc:
        print(f"error: cannot update canonical JSON: {exc}", file=sys.stderr)
        return 2
    print(
        f"Synchronized {len(result.changed_task_ids)} task(s) into {args.todo_list}: "
        + ", ".join(result.changed_task_ids)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

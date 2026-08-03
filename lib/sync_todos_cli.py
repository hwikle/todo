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
    outputs = result.add_mutually_exclusive_group()
    outputs.add_argument("--output", type=Path, help="write updated JSON to a new path")
    outputs.add_argument("--stdout", action="store_true", help="print updated JSON")
    outputs.add_argument("--dry-run", action="store_true", help="report changes without writing")
    result.add_argument("--strict", action="store_true", help="treat warnings as errors")
    return result


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    input_path = args.todo_list.resolve()
    output_path = args.output.resolve() if args.output else None
    if output_path == input_path:
        print("error: --output must differ from the input; omit it for in-place updates", file=sys.stderr)
        return 2
    if output_path and output_path.exists():
        print(f"error: refusing to overwrite existing output: {output_path}", file=sys.stderr)
        return 2
    try:
        document = json.loads(input_path.read_text())
        validator = CanonicalTodoValidator(ROOT / "schema")
    except (OSError, json.JSONDecodeError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    source_issues = validator.validate(document)
    if print_issues(source_issues, args.strict):
        print("Synchronization stopped because canonical JSON is invalid.", file=sys.stderr)
        return 1

    rendered = render_document(document, list(validator.priority_policy.order))
    view_dir = (args.view_dir or input_path.parent).resolve()
    result = synchronize_views(document, rendered, view_dir)
    if print_issues(list(result.issues), args.strict):
        print("Synchronization failed; canonical JSON was not changed.", file=sys.stderr)
        return 1
    updated_issues = validator.validate(result.document)
    if print_issues(updated_issues, args.strict):
        print("Synchronized state is invalid; canonical JSON was not changed.", file=sys.stderr)
        return 1
    content = json.dumps(result.document, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(content, end="")
        return 0
    if args.dry_run:
        if result.changed_task_ids:
            print(
                f"Would synchronize {len(result.changed_task_ids)} task(s): "
                + ", ".join(result.changed_task_ids)
            )
        else:
            print("Checkboxes already match canonical JSON; no changes would be made.")
        return 0
    if output_path:
        try:
            write_atomic(output_path, content)
        except OSError as exc:
            print(f"error: cannot write synchronized JSON: {exc}", file=sys.stderr)
            return 2
        print(
            f"Wrote synchronized JSON with {len(result.changed_task_ids)} changed task(s) "
            f"to {output_path}"
        )
        return 0
    if not result.changed_task_ids:
        print("Checkboxes already match canonical JSON; no changes made.")
        return 0
    try:
        write_atomic(input_path, content)
    except OSError as exc:
        print(f"error: cannot update canonical JSON: {exc}", file=sys.stderr)
        return 2
    print(
        f"Synchronized {len(result.changed_task_ids)} task(s) into {input_path}: "
        + ", ".join(result.changed_task_ids)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

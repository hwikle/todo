#!/usr/bin/env python3
"""Generate a canonical daily TODO list independently of scheduling."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

from todo_generation import (
    GenerationError,
    configured_daily_categories,
    generate_document,
    latest_previous_list,
)
from todo_render import render_document
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--date", default=dt.date.today().isoformat())
    result.add_argument("--data-dir", type=Path, default=ROOT / "todos")
    result.add_argument("--previous", type=Path, help="explicit previous canonical list")
    result.add_argument("--output", type=Path, help="generated JSON destination")
    result.add_argument("--render", action="store_true", help="also render category Markdown")
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


def print_issues(issues: list, strict: bool, prefix: str = "") -> bool:
    failed = False
    for issue in issues:
        effective = "error" if strict and issue.severity == "warning" else issue.severity
        suffix = " (strict)" if effective != issue.severity else ""
        print(f"{prefix}{issue.location}: {effective}{suffix}: {issue.message}", file=sys.stderr)
        failed = failed or effective == "error"
    return failed


def main() -> int:
    args = parser().parse_args()
    try:
        target_date = dt.date.fromisoformat(args.date).isoformat()
    except ValueError:
        print(f"error: invalid target date {args.date!r}", file=sys.stderr)
        return 2
    data_dir = args.data_dir.resolve()
    target = args.output.resolve() if args.output else data_dir / target_date / "todo.json"
    if target.exists():
        print(f"Canonical TODO list already exists: {target}")
        return 0
    try:
        validator = CanonicalTodoValidator(ROOT / "schema")
        categories = configured_daily_categories(ROOT / "config" / "task-types.conf")
        previous_path = args.previous.resolve() if args.previous else latest_previous_list(
            data_dir, target_date
        )
        previous = json.loads(previous_path.read_text()) if previous_path else None
    except (OSError, json.JSONDecodeError, GenerationError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if previous is not None:
        previous_issues = validator.validate(previous)
        if print_issues(previous_issues, args.strict, f"{previous_path}:"):
            print("Generation stopped because the previous list is invalid.", file=sys.stderr)
            return 1
        if previous["date"] >= target_date:
            print(
                f"error: previous list date {previous['date']} must predate {target_date}",
                file=sys.stderr,
            )
            return 2
    try:
        document = generate_document(target_date, previous, categories)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    issues = validator.validate(document)
    if print_issues(issues, args.strict):
        print("Generated list is invalid; no output was written.", file=sys.stderr)
        return 1
    try:
        write_atomic(target, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        if args.render:
            rendered = render_document(document, list(validator.priority_order))
            for name, view in rendered.items():
                write_atomic(target.parent / name, view.content)
    except OSError as exc:
        print(f"error: cannot write generated TODO list: {exc}", file=sys.stderr)
        return 2
    source = f" from {previous_path}" if previous_path else ""
    rendered_text = " and rendered Markdown" if args.render else ""
    print(f"Generated {target}{source}{rendered_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

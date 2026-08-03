"""Grouped command-line operations for canonical TODO lists."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import cast

from todo_cli import print_issues
from todo_generation import GenerationError, generate_document
from todo_io import emit_text, load_json
from todo_model import TodoList
from todo_repository import RepositoryError, configured_daily_categories
from todo_schema import CanonicalSchemaBundle
from todo_validation import Issue


ROOT = Path(__file__).resolve().parent.parent


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser(
        "list", help="create or validate TODO lists",
        description="Create a canonical TODO list or check existing lists for problems.",
    )
    commands = group.add_subparsers(
        dest="list_command", required=True, metavar="ACTION", help="list operation to perform"
    )
    create = commands.add_parser(
        "create", help="create a TODO list",
        description="Create a list for a date, optionally carrying forward unfinished tasks.",
    )
    create.add_argument(
        "--date", default=dt.date.today().isoformat(), metavar="YYYY-MM-DD",
        help="date for the new list (default: today)",
    )
    create.add_argument(
        "--previous", type=Path, metavar="FILE",
        help="canonical earlier list whose unfinished tasks should carry forward",
    )
    create.add_argument(
        "--output", type=Path, metavar="FILE",
        help="write JSON to FILE instead of standard output",
    )
    create.add_argument("--replace", action="store_true", help="allow --output to replace an existing file")
    create.add_argument("--strict", action="store_true", help="treat validation warnings as errors")
    validate = commands.add_parser(
        "validate", help="validate TODO lists",
        description="Check one or more JSON files or directories against canonical rules.",
    )
    validate.add_argument(
        "paths", nargs="+", type=Path, metavar="PATH",
        help="JSON file or directory to validate; directories are searched recursively",
    )
    validate.add_argument("--strict", action="store_true", help="treat validation warnings as errors")


def _expanded(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        result.extend(sorted(path.rglob("*.json")) if path.is_dir() else [path])
    return result


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    if args.list_command == "validate":
        failures = 0
        for path in _expanded(args.paths):
            try:
                document = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"{path}: error: {exc}", file=sys.stderr)
                failures += 1
                continue
            if print_issues(bundle_issues(bundle, document), args.strict, f"{path}:"):
                failures += 1
        return 1 if failures else 0
    try:
        target_date = dt.date.fromisoformat(args.date).isoformat()
        previous = cast(TodoList, load_json(args.previous)) if args.previous else None
        if previous is not None:
            issues = bundle_issues(bundle, previous)
            if print_issues(issues, args.strict, f"{args.previous}:"):
                return 1
            if previous["date"] >= target_date:
                raise GenerationError("previous list must predate the target date")
        categories = configured_daily_categories(ROOT / "config" / "task-types.conf")
        document = generate_document(target_date, previous, categories)
        issues = bundle_issues(bundle, document)
        if print_issues(issues, args.strict):
            return 1
        emit_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            args.output,
            args.replace,
        )
        return 0
    except (OSError, json.JSONDecodeError, ValueError, GenerationError, RepositoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def bundle_issues(bundle: CanonicalSchemaBundle, document: object) -> list[Issue]:
    from todo_validation import CanonicalTodoValidator

    validator = CanonicalTodoValidator(bundle.schema_dir)
    return validator.validate(document)

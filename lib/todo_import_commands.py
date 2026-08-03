"""Grouped imports into the canonical TODO model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from todo_cli import print_issues
from todo_io import emit_text
from todo_markdown import MarkdownConversionError
from todo_markdown_io import convert_daily_directory
from todo_schema import CanonicalSchemaBundle
from todo_validation import CanonicalTodoValidator


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser("import", help="import external task formats")
    formats = group.add_subparsers(dest="import_format", required=True)
    markdown = formats.add_parser("markdown")
    markdown.add_argument("source", type=Path)
    markdown.add_argument("--output", type=Path)
    markdown.add_argument("--replace", action="store_true")
    markdown.add_argument("--strict", action="store_true")


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        document = convert_daily_directory(
            args.source, list(bundle.priority_policy.order)
        )
        issues = CanonicalTodoValidator(bundle.schema_dir).validate(document)
        if print_issues(issues, args.strict):
            return 1
        emit_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            args.output,
            args.replace,
        )
        return 0
    except (OSError, MarkdownConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

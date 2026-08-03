#!/usr/bin/env python3
"""Convert a daily Markdown directory to canonical TODO-list JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from todo_cli import print_issues
from todo_io import write_text_atomic
from todo_markdown import MarkdownConversionError
from todo_markdown_io import convert_daily_directory
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("source", type=Path, help="daily Markdown directory")
    result.add_argument("--output", type=Path, help="output JSON path")
    result.add_argument("--stdout", action="store_true", help="print JSON without writing")
    result.add_argument("--strict", action="store_true", help="treat warnings as errors")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.stdout and args.output:
        print("error: --stdout and --output cannot be combined", file=sys.stderr)
        return 2
    try:
        validator = CanonicalTodoValidator(ROOT / "schema")
        document = convert_daily_directory(
            args.source,
            list(validator.priority_policy.order),
        )
        issues = validator.validate(document)
    except (MarkdownConversionError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if print_issues(issues, args.strict):
        print("Conversion failed validation; no output was written.", file=sys.stderr)
        return 1

    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(content, end="")
        return 0
    output = (args.output or args.source / "todo.json").resolve()
    try:
        write_text_atomic(output, content, replace=False)
    except (OSError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Converted {len(document['tasks'])} task(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

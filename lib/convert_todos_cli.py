#!/usr/bin/env python3
"""Convert a daily Markdown directory to canonical TODO-list JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from todo_markdown import MarkdownConversionError, convert_daily_directory
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("source", type=Path, help="daily Markdown directory")
    result.add_argument("--output", type=Path, help="output JSON path")
    result.add_argument("--stdout", action="store_true", help="print JSON without writing")
    result.add_argument("--strict", action="store_true", help="treat warnings as errors")
    return result


def write_atomic(path: Path, content: str) -> None:
    if path.exists():
        raise MarkdownConversionError(f"{path}: refusing to overwrite existing output")
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

    for issue in issues:
        effective = "error" if args.strict and issue.severity == "warning" else issue.severity
        suffix = " (strict)" if effective != issue.severity else ""
        print(f"{issue.location}: {effective}{suffix}: {issue.message}", file=sys.stderr)
    if any(issue.severity == "error" for issue in issues) or (
        args.strict and any(issue.severity == "warning" for issue in issues)
    ):
        print("Conversion failed validation; no output was written.", file=sys.stderr)
        return 1

    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(content, end="")
        return 0
    output = (args.output or args.source / "todo.json").resolve()
    try:
        write_atomic(output, content)
    except (OSError, MarkdownConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Converted {len(document['tasks'])} task(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

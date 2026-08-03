#!/usr/bin/env python3
"""Render canonical TODO-list JSON into ID-free category Markdown files."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from todo_render import combine_rendered, render_document
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("todo_list", type=Path, help="canonical TODO-list JSON")
    outputs = result.add_mutually_exclusive_group()
    outputs.add_argument("--output-dir", type=Path, help="category-file destination")
    outputs.add_argument("--combined-output", type=Path, help="combined Markdown destination")
    outputs.add_argument("--stdout", action="store_true", help="print combined Markdown")
    result.add_argument("--replace", action="store_true", help="replace existing category files")
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


def main() -> int:
    args = parser().parse_args()
    try:
        document = json.loads(args.todo_list.read_text())
        validator = CanonicalTodoValidator(ROOT / "schema")
        issues = validator.validate(document)
    except (OSError, json.JSONDecodeError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for issue in issues:
        effective = "error" if args.strict and issue.severity == "warning" else issue.severity
        suffix = " (strict)" if effective != issue.severity else ""
        print(f"{issue.location}: {effective}{suffix}: {issue.message}", file=sys.stderr)
    if any(issue.severity == "error" for issue in issues) or (
        args.strict and any(issue.severity == "warning" for issue in issues)
    ):
        print("Rendering failed validation; no files were written.", file=sys.stderr)
        return 1

    rendered = render_document(document, list(validator.priority_order))
    if args.stdout:
        print(combine_rendered(rendered), end="")
        return 0
    if args.combined_output:
        destination = args.combined_output.resolve()
        if destination.exists() and not args.replace:
            print(f"error: refusing to replace existing file: {destination}", file=sys.stderr)
            return 2
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(destination, combine_rendered(rendered))
        except OSError as exc:
            print(f"error: cannot write combined Markdown: {exc}", file=sys.stderr)
            return 2
        print(f"Rendered {len(rendered)} categories to {destination}")
        return 0
    output_dir = (args.output_dir or args.todo_list.parent).resolve()
    destinations = {output_dir / name: view for name, view in rendered.items()}
    existing = [path for path in destinations if path.exists()]
    if existing and not args.replace:
        print(
            "error: refusing to replace existing files: "
            + ", ".join(str(path) for path in existing),
            file=sys.stderr,
        )
        return 2
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for path, view in destinations.items():
            write_atomic(path, view.content)
    except OSError as exc:
        print(f"error: cannot write rendered Markdown: {exc}", file=sys.stderr)
        return 2
    occurrence_count = sum(len(view.occurrences) for view in rendered.values())
    print(
        f"Rendered {len(rendered)} category file(s) with "
        f"{occurrence_count} task occurrence(s) to {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

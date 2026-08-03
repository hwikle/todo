#!/usr/bin/env python3
"""Render canonical TODO-list JSON into ID-free category Markdown files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from todo_cli import print_issues
from todo_io import load_json, write_text_atomic
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


def main() -> int:
    args = parser().parse_args()
    try:
        document = load_json(args.todo_list)
        validator = CanonicalTodoValidator(ROOT / "schema")
        issues = validator.validate(document)
    except (OSError, json.JSONDecodeError, ValidationConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if print_issues(issues, args.strict):
        print("Rendering failed validation; no files were written.", file=sys.stderr)
        return 1

    rendered = render_document(document, list(validator.priority_policy.order))
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
            write_text_atomic(destination, combine_rendered(rendered))
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
            write_text_atomic(path, view.content)
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

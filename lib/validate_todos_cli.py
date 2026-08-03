#!/usr/bin/env python3
"""Validate canonical Daily TODO JSON documents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from todo_validation import CanonicalTodoValidator, ValidationConfigurationError
from todo_cli import print_issues
from todo_io import load_json


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("paths", nargs="+", type=Path, help="JSON files or directories")
    result.add_argument(
        "--strict",
        action="store_true",
        help="treat validation warnings as errors",
    )
    return result


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        if path.is_dir():
            result.extend(sorted(path.rglob("*.json")))
        else:
            result.append(path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        validator = CanonicalTodoValidator(ROOT / "schema")
    except ValidationConfigurationError as exc:
        print(f"validation configuration error: {exc}", file=sys.stderr)
        return 2

    paths = expand_paths(args.paths)
    if not paths:
        print("validation error: no JSON documents found", file=sys.stderr)
        return 2

    failures = 0
    warning_count = 0
    for path in paths:
        try:
            document = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: error: cannot load JSON: {exc}", file=sys.stderr)
            failures += 1
            continue
        issues = validator.validate(document)
        warning_count += sum(issue.severity == "warning" for issue in issues)
        if print_issues(issues, args.strict, f"{path}:"):
            failures += 1

    if failures:
        print(
            f"Validation failed for {failures} of {len(paths)} document(s).",
            file=sys.stderr,
        )
        return 1
    print(f"Validated {len(paths)} document(s) with {warning_count} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

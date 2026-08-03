#!/usr/bin/env python3
"""Atomically migrate canonical TODO task references to UUIDv4 IDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import cast

from todo_cli import print_issues
from todo_ids import TaskIdGenerationError, migrate_task_ids
from todo_io import load_json, write_text_atomic
from todo_model import TodoList
from todo_validation import CanonicalTodoValidator, ValidationConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("path", nargs="?", type=Path, default=Path("todo.json"))
    return result


def main() -> int:
    path = parser().parse_args().path.resolve()
    try:
        original = cast(TodoList, load_json(path))
        migrated = migrate_task_ids(original)
        validator = CanonicalTodoValidator(ROOT / "schema")
        issues = validator.validate(migrated)
    except (
        OSError,
        json.JSONDecodeError,
        TaskIdGenerationError,
        ValidationConfigurationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if print_issues(issues, strict=False):
        print("Migration failed validation; canonical JSON was not changed.", file=sys.stderr)
        return 1
    try:
        write_text_atomic(path, json.dumps(migrated, indent=2, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"error: cannot write migrated TODO list: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

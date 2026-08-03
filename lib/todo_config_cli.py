#!/usr/bin/env python3
"""Inspect and update canonical category configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from todo_io import write_text_atomic
from todo_repository import RepositoryError, category_definitions


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "task-types.conf"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("list-types", aliases=["types"], help="list configured categories")
    add_type = commands.add_parser("add-type", help="add a configured category")
    add_type.add_argument("slug")
    add_type.add_argument("label")
    add_type.add_argument("--behavior", choices=["daily", "backlog"], default="daily")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        definitions = category_definitions(CONFIG)
        if args.command in {"list-types", "types"}:
            for item in definitions:
                print(f"{item.id}\t{item.display_name}\t{item.behavior}")
            return 0
        if not SLUG_RE.fullmatch(args.slug):
            raise RepositoryError("category slug must be lowercase words separated by hyphens")
        if any(item.id == args.slug for item in definitions):
            raise RepositoryError(f"category {args.slug!r} already exists")
        if not args.label.strip():
            raise RepositoryError("category display name cannot be empty")
        content = CONFIG.read_text()
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{args.slug}|{args.label.strip()}|{args.behavior}\n"
        write_text_atomic(CONFIG, content)
    except (OSError, RepositoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Added category {args.slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Grouped category-configuration commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from todo_io import write_text_atomic
from todo_repository import CategoryDefinition, RepositoryError, category_definitions


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "task-types.conf"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser("category", help="manage category configuration")
    commands = group.add_subparsers(dest="category_command", required=True)
    commands.add_parser("list")
    add = commands.add_parser("add")
    add.add_argument("id")
    add.add_argument("name")
    add.add_argument("--behavior", choices=["daily", "backlog"], default="daily")
    rename = commands.add_parser("rename")
    rename.add_argument("id")
    rename.add_argument("name")
    remove = commands.add_parser("remove")
    remove.add_argument("id")


def _serialize(items: list[CategoryDefinition]) -> str:
    return "# slug|display name|behavior\n" + "".join(
        f"{item.id}|{item.display_name}|{item.behavior}\n" for item in items
    )


def run(args: argparse.Namespace) -> int:
    try:
        items = category_definitions(CONFIG)
        if args.category_command == "list":
            for item in items:
                print(f"{item.id}\t{item.display_name}\t{item.behavior}")
            return 0
        match = next((item for item in items if item.id == args.id), None)
        if args.category_command == "add":
            if not SLUG_RE.fullmatch(args.id):
                raise RepositoryError("category ID must be lowercase words separated by hyphens")
            if match is not None:
                raise RepositoryError(f"category {args.id!r} already exists")
            if not args.name.strip():
                raise RepositoryError("category display name cannot be empty")
            items.append(CategoryDefinition(args.id, args.name.strip(), args.behavior))
        elif args.category_command == "rename":
            if match is None:
                raise RepositoryError(f"unknown category {args.id!r}")
            if not args.name.strip():
                raise RepositoryError("category display name cannot be empty")
            items[items.index(match)] = CategoryDefinition(match.id, args.name.strip(), match.behavior)
        else:
            if match is None:
                raise RepositoryError(f"unknown category {args.id!r}")
            items.remove(match)
        write_text_atomic(CONFIG, _serialize(items))
        return 0
    except (OSError, RepositoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

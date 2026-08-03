"""Unified Daily TODO command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import todo_category_commands
import todo_import_commands
import todo_list_commands
import todo_schedule_commands
import todo_task_commands
import todo_view_commands
from todo_schema import CanonicalSchemaBundle, SchemaConfigurationError


ROOT = Path(__file__).resolve().parent.parent


def parser(bundle: CanonicalSchemaBundle) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="todo", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    todo_task_commands.configure(commands, bundle)
    todo_list_commands.configure(commands)
    todo_view_commands.configure(commands)
    todo_category_commands.configure(commands)
    todo_import_commands.configure(commands)
    todo_schedule_commands.configure(commands)
    return result


def main() -> int:
    try:
        bundle = CanonicalSchemaBundle(ROOT / "schema")
        args = parser(bundle).parse_args()
        if args.command == "task":
            return todo_task_commands.run(args, bundle)
        if args.command == "list":
            return todo_list_commands.run(args, bundle)
        if args.command == "view":
            return todo_view_commands.run(args, bundle)
        if args.command == "category":
            return todo_category_commands.run(args)
        if args.command == "import":
            return todo_import_commands.run(args, bundle)
        return todo_schedule_commands.run(args)
    except SchemaConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

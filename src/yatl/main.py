"""Unified Daily TODO command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import cast

from . import import_commands
from . import list_commands
from . import task_commands
from . import view_commands
from . import web_commands

from yatl.parser import TodoArgumentParser
from yatl.schema import CanonicalSchemaBundle, SchemaConfigurationError

from yatl.resources import SCHEMA_DIR


def parser(bundle: CanonicalSchemaBundle) -> argparse.ArgumentParser:
    result = TodoArgumentParser(
        prog="yatl",
        description=(
            "Yet another todo list"
        ),
    )
    commands = cast(
        "argparse._SubParsersAction[argparse.ArgumentParser]",
        result.add_subparsers(
            dest="command", required=True, metavar="COMMAND", help="workflow to perform"
        ),
    )
    todo_task_commands.configure(commands, bundle)
    todo_list_commands.configure(commands)
    todo_view_commands.configure(commands)
    todo_import_commands.configure(commands)
    todo_web_commands.configure(commands)
    return result


def main() -> int:
    locator = RepositoryResourceLocator(
        root=Path(__file__).parents[2]
    )

    try:
        bundle = CanonicalSchemaBundle(locator.schema_dir)
    except SchemaConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)

        return 1

    args = parser(bundle).parse_args()

    if args.command == "task":
        return todo_task_commands.run(args, bundle)
    if args.command == "list":
        return todo_list_commands.run(args, bundle)
    if args.command == "view":
        return todo_view_commands.run(args, bundle)
    if args.command == "import":
        return todo_import_commands.run(args, bundle)
    if args.command == "serve":
        return todo_web_commands.run(args, bundle)

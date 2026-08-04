"""Command-line adapter for the local browser checklist."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import sys

from todo_schema import CanonicalSchemaBundle
from todo_web import create_app
from todo_web_application import (
    RepairRequiredError,
    TodoStructureError,
    WebEditError,
    format_issues,
)


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    serve = subparsers.add_parser(
        "serve",
        help="edit a TODO list in a browser",
        description="Open one explicitly selected canonical TODO list as an editable checklist.",
    )
    serve.add_argument("file", type=Path, metavar="FILE", help="canonical TODO-list JSON file to edit")
    serve.add_argument("--host", default="127.0.0.1", metavar="HOST", help="address to listen on (default: 127.0.0.1)")
    serve.add_argument("--port", default=8000, type=int, metavar="PORT", help="port to listen on (default: 8000)")
    serve.add_argument(
        "--repair",
        action="store_true",
        help="open a structurally valid list with semantic errors for repair",
    )


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        app = create_app(args.file, bundle, repair=args.repair)
        app.run(host=args.host, port=args.port, debug=False)
        return 0
    except RepairRequiredError as exc:
        print("error: the TODO list contains semantic validation errors:", file=sys.stderr)
        print(format_issues(exc.issues, _read_json_if_possible(args.file)), file=sys.stderr)
        command = f"todo serve {shlex.quote(str(args.file))} --repair"
        print(f"\nOpen it in repair mode:\n\n    {command}", file=sys.stderr)
        return 1
    except TodoStructureError as exc:
        print(f"error: the TODO list cannot be opened:\n{exc}", file=sys.stderr)
        command = f"todo list validate {shlex.quote(str(args.file))}"
        print(f"\nEdit the file directly, then validate it again:\n\n    {command}", file=sys.stderr)
        return 1
    except (OSError, WebEditError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _read_json_if_possible(path: Path) -> object:
    import json

    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}

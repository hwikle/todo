"""Command-line adapter for the local browser checklist."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from todo_schema import CanonicalSchemaBundle
from todo_repository import RepositoryError
from todo_web import create_app
from todo_web_application import WebEditError


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    serve = subparsers.add_parser(
        "serve",
        help="edit a TODO list in a browser",
        description="Open one explicitly selected canonical TODO list as an editable checklist.",
    )
    serve.add_argument("file", type=Path, metavar="FILE", help="canonical TODO-list JSON file to edit")
    serve.add_argument("--host", default="127.0.0.1", metavar="HOST", help="address to listen on (default: 127.0.0.1)")
    serve.add_argument("--port", default=8000, type=int, metavar="PORT", help="port to listen on (default: 8000)")


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        app = create_app(args.file, bundle)
        app.run(host=args.host, port=args.port, debug=False)
        return 0
    except (OSError, RepositoryError, WebEditError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

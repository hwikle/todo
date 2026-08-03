"""Grouped rendering and checkbox synchronization commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import cast

from todo_cli import print_issues
from todo_io import emit_text, load_json, load_markdown_directory, write_text_atomic
from todo_model import TodoList
from todo_render import combine_rendered, render_document
from todo_schema import CanonicalSchemaBundle
from todo_sync import synchronize_views
from todo_validation import CanonicalTodoValidator


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser("view", help="render and synchronize Markdown views")
    commands = group.add_subparsers(dest="view_command", required=True)
    render = commands.add_parser("render")
    render.add_argument("file", type=Path)
    outputs = render.add_mutually_exclusive_group()
    outputs.add_argument("--output", type=Path)
    outputs.add_argument("--output-dir", type=Path)
    render.add_argument("--replace", action="store_true")
    render.add_argument("--strict", action="store_true")
    sync = commands.add_parser("sync")
    sync.add_argument("file", type=Path)
    sync.add_argument("--view-dir", type=Path, required=True)
    sync.add_argument("--output", type=Path)
    sync.add_argument("--replace", action="store_true")
    sync.add_argument("--strict", action="store_true")


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        document = cast(TodoList, load_json(args.file))
        validator = CanonicalTodoValidator(bundle.schema_dir)
        issues = validator.validate(document)
        if print_issues(issues, args.strict):
            return 1
        rendered = render_document(document, list(bundle.priority_policy.order))
        if args.view_command == "render":
            if args.output_dir is None:
                emit_text(combine_rendered(rendered), args.output, args.replace)
            else:
                destinations = [args.output_dir / name for name in rendered]
                if not args.replace and any(path.exists() for path in destinations):
                    raise FileExistsError("rendered destination already exists")
                args.output_dir.mkdir(parents=True, exist_ok=True)
                for name, view in rendered.items():
                    write_text_atomic(args.output_dir / name, view.content)
            return 0
        views = load_markdown_directory(args.view_dir)
        result = synchronize_views(document, rendered, views, str(args.view_dir))
        if print_issues(result.issues, args.strict):
            return 1
        updated_issues = validator.validate(result.document)
        if print_issues(updated_issues, args.strict):
            return 1
        emit_text(
            json.dumps(result.document, indent=2, ensure_ascii=False) + "\n",
            args.output,
            args.replace,
        )
        return 0
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

"""Grouped imports into the canonical TODO model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from yatl.cli import print_issues
from yatl.io import emit_text
from yatl.markdown import MarkdownConversionError
from yatl.markdown_io import convert_daily_directory
from yatl.schema import CanonicalSchemaBundle
from yatl.validation import CanonicalTodoValidator


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser(
        "import", help="import an existing TODO list",
        description="Convert a supported external representation into canonical JSON.",
    )
    formats = group.add_subparsers(
        dest="import_format", required=True, metavar="FORMAT", help="source format to import"
    )
    markdown = formats.add_parser(
        "markdown", help="import category Markdown files",
        description="Convert a dated directory of category Markdown files into canonical JSON.",
    )
    markdown.add_argument("source", type=Path, metavar="DIR", help="dated directory containing category Markdown files")
    markdown.add_argument(
        "--output", type=Path, metavar="FILE",
        help="write JSON to FILE instead of standard output",
    )
    markdown.add_argument("--replace", action="store_true", help="allow --output to replace an existing file")
    markdown.add_argument("--strict", action="store_true", help="treat validation warnings as errors")


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        document = convert_daily_directory(
            args.source, list(bundle.priority_policy.order)
        )
        issues = CanonicalTodoValidator(bundle.schema_dir).validate(document)
        if print_issues(issues, args.strict):
            return 1
        emit_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            args.output,
            args.replace,
        )
        return 0
    except (OSError, MarkdownConversionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

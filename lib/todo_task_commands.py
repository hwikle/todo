"""Grouped command-line operations for canonical tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, cast

from todo_application import AddTaskRequest, EditTaskRequest, TodoApplication, TodoApplicationError
from todo_io import emit_text, load_json
from todo_model import DeadlineKind, Priority, TodoList
from todo_schema import CanonicalSchemaBundle
from todo_selectors import SelectorError, resolve_task
from todo_argument_values import deadline_kinds, parse_due


def _document_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, metavar="FILE", help="canonical TODO-list JSON file to read")
    parser.add_argument(
        "--output", type=Path, metavar="FILE",
        help="write the updated JSON to FILE instead of standard output",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="allow --output to replace an existing file",
    )


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], bundle: CanonicalSchemaBundle) -> None:
    task = subparsers.add_parser(
        "task", help="inspect or change tasks",
        description="Inspect tasks or produce an updated canonical TODO list.",
    )
    commands = task.add_subparsers(
        dest="task_command", required=True, metavar="ACTION", help="task operation to perform"
    )

    add = commands.add_parser(
        "add", help="add a task", description="Add one task to a canonical TODO list."
    )
    _document_output(add)
    add.add_argument("name", metavar="NAME", help="short task name")
    add.add_argument("--description", metavar="TEXT", help="optional longer description")
    add.add_argument(
        "--category", action="append", required=True, metavar="CATEGORY",
        help="assign a category by ID or exact name; repeat for multiple categories",
    )
    add.add_argument(
        "--priority", choices=bundle.priority_policy.order,
        help="set the task priority",
    )
    add.add_argument(
        "--depends-on", action="append", default=[], metavar="TASK",
        help="make the new task depend on TASK; repeat for multiple dependencies",
    )
    add.add_argument(
        "--dependency-of", action="append", default=[], metavar="TASK",
        help="make the new task a dependency of TASK; repeat for multiple dependent tasks",
    )
    add.add_argument("--due", metavar="DATE", help="due date as YYYY, YYYY-MM, or YYYY-MM-DD")
    add.add_argument("--due-time", metavar="HH:MM", help="due time; requires a complete due date")
    add.add_argument(
        "--deadline-kind", choices=deadline_kinds(bundle),
        help="classify the due date; requires --due",
    )

    edit = commands.add_parser(
        "edit", help="edit a task",
        description="Change one task's fields, categories, or dependencies.",
    )
    _document_output(edit)
    edit.add_argument("task", metavar="TASK", help="task UUID or exact unique name")
    edit.add_argument("--name", metavar="NAME", help="replace the short task name")
    edit.add_argument("--description", metavar="TEXT", help="replace the description")
    edit.add_argument("--clear-description", action="store_true", help="remove the description")
    edit.add_argument(
        "--priority", choices=bundle.priority_policy.order,
        help="replace the priority",
    )
    edit.add_argument("--clear-priority", action="store_true", help="make the task unprioritized")
    edit.add_argument(
        "--add-category", action="append", default=[], metavar="CATEGORY",
        help="add a category by ID or exact name; repeat as needed",
    )
    edit.add_argument(
        "--remove-category", action="append", default=[], metavar="CATEGORY",
        help="remove a category by ID or exact name; repeat as needed",
    )
    edit.add_argument(
        "--add-dependency", action="append", default=[], metavar="TASK",
        help="add a dependency by UUID or exact name; repeat as needed",
    )
    edit.add_argument(
        "--remove-dependency", action="append", default=[], metavar="TASK",
        help="remove a dependency by UUID or exact name; repeat as needed",
    )
    edit.add_argument("--due", metavar="DATE", help="replace the due date: YYYY, YYYY-MM, or YYYY-MM-DD")
    edit.add_argument("--due-time", metavar="HH:MM", help="replace the due time; requires a complete due date")
    edit.add_argument(
        "--deadline-kind", choices=deadline_kinds(bundle),
        help="replace the deadline classification; requires --due",
    )
    edit.add_argument("--clear-due", action="store_true", help="remove the due date and classification")

    lifecycle = {
        "remove": ("remove a task", "Remove a task that no other task depends on."),
        "complete": ("mark a task complete", "Mark a task complete after its dependencies are complete."),
        "reopen": ("mark a task incomplete", "Mark a task incomplete when no completed task depends on it."),
    }
    for name, (help_text, description) in lifecycle.items():
        command = commands.add_parser(name, help=help_text, description=description)
        _document_output(command)
        command.add_argument("task", metavar="TASK", help="task UUID or exact unique name")

    show = commands.add_parser(
        "show", help="show one task", description="Print one task as JSON."
    )
    show.add_argument("file", type=Path, metavar="FILE", help="canonical TODO-list JSON file")
    show.add_argument("task", metavar="TASK", help="task UUID or exact unique name")
    listing = commands.add_parser(
        "list", help="list all tasks", description="Print every task in a canonical TODO list as JSON."
    )
    listing.add_argument("file", type=Path, metavar="FILE", help="canonical TODO-list JSON file")


def _load(path: Path) -> TodoList:
    return cast(TodoList, load_json(path.resolve()))


def _content(document: TodoList) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        document = _load(args.file)
        application = TodoApplication(bundle)
        command = args.task_command
        if command == "list":
            print(json.dumps(document["tasks"], indent=2, ensure_ascii=False))
            return 0
        if command == "show":
            print(json.dumps(resolve_task(document, args.task), indent=2, ensure_ascii=False))
            return 0
        if command == "add":
            due = parse_due(args.due, args.due_time)
            if (due is None) != (args.deadline_kind is None):
                raise TodoApplicationError("--due and --deadline-kind must be provided together")
            result = application.add(document, AddTaskRequest(
                name=args.name,
                categories=tuple(args.category),
                priority=cast(Optional[Priority], args.priority),
                description=args.description,
                depends_on=tuple(args.depends_on),
                dependency_of=tuple(args.dependency_of),
                due=due,
                deadline_kind=cast(Optional[DeadlineKind], args.deadline_kind),
            ))
        elif command == "edit":
            due = parse_due(args.due, args.due_time)
            result = application.edit(document, args.task, EditTaskRequest(
                name=args.name, description=args.description,
                clear_description=args.clear_description,
                priority=cast(Optional[Priority], args.priority),
                clear_priority=args.clear_priority,
                add_categories=tuple(args.add_category),
                remove_categories=tuple(args.remove_category),
                add_dependencies=tuple(args.add_dependency),
                remove_dependencies=tuple(args.remove_dependency),
                due=due, deadline_kind=cast(Optional[DeadlineKind], args.deadline_kind),
                clear_due=args.clear_due,
            ))
        elif command == "remove":
            result = application.remove(document, args.task)
        elif command == "complete":
            result = application.complete(document, args.task, True)
        else:
            result = application.complete(document, args.task, False)
        emit_text(_content(result), args.output, args.replace)
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        SelectorError,
        TodoApplicationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

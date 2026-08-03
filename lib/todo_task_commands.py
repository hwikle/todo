"""Grouped command-line operations for canonical tasks."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Optional, cast

from todo_add import TaskAdditionError, add_task
from todo_ids import TaskIdGenerationError
from todo_io import emit_text, load_json
from todo_model import DeadlineKind, Priority, TodoList
from todo_schema import CanonicalSchemaBundle
from todo_selectors import SelectorError, resolve_category, resolve_task
from todo_task_mutation import (
    TaskMutationError,
    attach_to_parents,
    remove_task,
    set_completion,
)
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


def _validate_document(bundle: CanonicalSchemaBundle, document: TodoList) -> None:
    errors = [item for item in bundle.validator.iter_errors(document)]
    if errors:
        raise TaskMutationError(f"edited document is invalid: {errors[0].message}")


def _edit(args: argparse.Namespace, bundle: CanonicalSchemaBundle, document: TodoList) -> TodoList:
    updated = copy.deepcopy(document)
    try:
        task = resolve_task(updated, args.task)
        if args.name is not None:
            if not args.name.strip():
                raise TaskMutationError("task name cannot be empty")
            task["name"] = args.name.strip()
        if args.description is not None and args.clear_description:
            raise TaskMutationError("--description and --clear-description conflict")
        if args.description is not None:
            task["description"] = args.description
        if args.clear_description:
            task.pop("description", None)
        if args.priority is not None and args.clear_priority:
            raise TaskMutationError("--priority and --clear-priority conflict")
        if args.priority is not None:
            task["priority"] = cast(Priority, args.priority)
        if args.clear_priority:
            task.pop("priority", None)
        if args.clear_due and any((args.due, args.due_time, args.deadline_kind)):
            raise TaskMutationError("--clear-due conflicts with due options")
        if args.clear_due:
            task.pop("due", None)
            task.pop("deadline_kind", None)
        elif any((args.due, args.due_time, args.deadline_kind)):
            due = parse_due(args.due, args.due_time)
            if due is None or args.deadline_kind is None:
                raise TaskMutationError("--due and --deadline-kind must be provided together")
            task["due"] = due
            task["deadline_kind"] = cast(DeadlineKind, args.deadline_kind)
        for selector in args.add_dependency:
            dependency = resolve_task(updated, selector)
            if dependency["id"] in task["dependencies"]:
                raise TaskMutationError(f"dependency {selector!r} is already present")
            task["dependencies"].append(dependency["id"])
        for selector in args.remove_dependency:
            dependency = resolve_task(updated, selector)
            if dependency["id"] not in task["dependencies"]:
                raise TaskMutationError(f"dependency {selector!r} is not present")
            task["dependencies"].remove(dependency["id"])
        memberships = {item["category"]: item for item in updated["category_memberships"]}
        for selector in args.add_category:
            category_id = resolve_category(updated, selector)["id"]
            membership = memberships.setdefault(category_id, {"category": category_id, "tasks": []})
            if membership not in updated["category_memberships"]:
                updated["category_memberships"].append(membership)
            if task["id"] in membership["tasks"]:
                raise TaskMutationError(f"category {selector!r} is already assigned")
            membership["tasks"].append(task["id"])
        for selector in args.remove_category:
            category_id = resolve_category(updated, selector)["id"]
            removable = memberships.get(category_id)
            if removable is None or task["id"] not in removable["tasks"]:
                raise TaskMutationError(f"category {selector!r} is not assigned")
            removable["tasks"].remove(task["id"])
    except SelectorError as exc:
        raise TaskMutationError(str(exc)) from exc
    _validate_document(bundle, updated)
    return updated


def run(args: argparse.Namespace, bundle: CanonicalSchemaBundle) -> int:
    try:
        document = _load(args.file)
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
                raise TaskAdditionError("--due and --deadline-kind must be provided together")
            added = add_task(
                document,
                name=args.name,
                category_selectors=args.category,
                priority_policy=bundle.priority_policy,
                priority=cast(Optional[Priority], args.priority),
                description=args.description,
                dependency_selectors=args.depends_on,
                due=due,
                deadline_kind=cast(Optional[DeadlineKind], args.deadline_kind),
            )
            attach_to_parents(
                added.document, added.task, args.dependency_of, bundle.priority_policy
            )
            task_errors = sorted(
                bundle.validator_for("task.schema.json").iter_errors(added.task),
                key=lambda error: (list(error.absolute_path), error.message),
            )
            if task_errors:
                raise TaskAdditionError(f"new task is invalid: {task_errors[0].message}")
            result = added.document
        elif command == "edit":
            result = _edit(args, bundle, document)
        elif command == "remove":
            result = remove_task(document, args.task)
        elif command == "complete":
            result = set_completion(document, args.task, True)
        else:
            result = set_completion(document, args.task, False)
        emit_text(_content(result), args.output, args.replace)
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        SelectorError,
        TaskAdditionError,
        TaskIdGenerationError,
        TaskMutationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

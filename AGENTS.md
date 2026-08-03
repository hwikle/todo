# Repository guidance

This repository is a Markdown-first task system. Markdown under `todos/` and
`backlog/` is authoritative; JSON is only an export and validation model.

## Before changing tasks

- Read `config/task-types.conf`, `config/priorities.conf`, and
  `config/due-kinds.conf`; never hard-code their values.
- Use `bin/todo` when practical. Direct Markdown edits are supported.
- Preserve task IDs in `<!-- task:xxxxxxxxxxxx -->` comments.
- If a manually added task lacks an ID, run `bin/todo validate --fix`.
- Do not overwrite an existing daily directory or remove historical tasks.

## Task syntax

```markdown
- [ ] Short name <!-- task:12-hex-digits -->
    Optional description.
    - [ ] Subtask name <!-- task:12-hex-digits -->
        Optional subtask description.
```

Tasks and subtasks share the same recursive structure in the current Markdown
format. Category comes from the filename. In the canonical JSON model, priority
is an optional task property using `schema/priority.schema.json`. Categories are
defined independently using `schema/category.schema.json`, and TODO-list
category memberships associate them with tasks. Markdown filenames, headings,
and hierarchy are view concerns rather than schema semantics.

An optional due date is stored in the task comment as `due:YYYY-MM-DD` and must
also have a configured `due-kind:slug`. An optional local `time:HH:MM` is valid
only when the date is present. Preserve these fields during edits.

Do not mark a parent complete while it contains an unchecked subtask. The daily
carry-forward operation copies unchecked tasks, descriptions, and unchecked
descendants; completed tasks remain only in historical files.

## Generation and scheduling boundary

Daily generation is scheduler-independent. `bin/todo generate` owns creation
and carry-forward; `bin/create-daily-todo` is only a thin entry point. Schedulers
may invoke that entry point but must not duplicate generation logic. Codex
scheduled check-ins read and render existing files; they do not generate them.

## Natural-language requests

For requests such as “add X to Household as Must,” translate the configured
display names to their slugs and run `bin/todo add`. Resolve a parent by stable
ID before adding a subtask. If a name matches multiple tasks, ask which one.

Examples:

```text
bin/todo add --type household --priority Must "Replace furnace filter"
bin/todo add --type health --priority Must --due-date 2026-08-03 \
  --due-time 10:30 --due-kind hard "Submit quarterly report"
bin/todo add --type someday "Learn woodworking"
bin/todo add --parent abc123def456 "Buy replacement filter"
bin/todo complete abc123def456
```

## Verification

The repository is temporarily between storage models. The JSON schemas describe
canonical task definitions with task-level `priority` and `dependencies`, plus
separate category definitions and memberships. The current Markdown validator
and generator still emit recursive `subtasks` and derive category and priority
from filenames and headings.

During this transition, `bin/validate-todos` validates canonical JSON documents
and is safe to run independently. Do not run `bin/todo generate` or
`bin/create-daily-todo`; those legacy paths still target Markdown. The
conversion phase must restore generation verification before scheduling is
enabled.

Canonical validation commands are:

```text
bin/validate-todos path/to/todo-list.json
bin/validate-todos --strict path/to/todo-list.json
python3 tests/test_schema_validation.py
python3 tests/test_markdown_conversion.py
python3 tests/test_markdown_rendering.py
```

Legacy verification commands, to be restored after migration, are:

```text
bin/todo list --date YYYY-MM-DD
python3 tests/test_generation_independent.py
```

When changing the scheduler template, also run:

```text
plutil -lint launchd/local.daily-todo.plist
```

Never install or enable `launchd`, create or modify a scheduled Codex task, make
a Git commit, or disable another task without explicit user approval.

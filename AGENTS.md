# Repository guidance

This repository contains software for managing daily TODO lists. User data under
`todos/` and `backlog/` is local and ignored by Git.

## Source of truth

- `todos/YYYY-MM-DD/todo.json` is the canonical daily list.
- Category Markdown files are deterministic, ID-free views generated from JSON.
- Only checkbox markers may be edited directly in generated Markdown.
- Run `bin/sync-todos` after checkbox edits. It fails on structural changes or
  conflicting states across repeated appearances.
- For structural task changes, edit canonical JSON, validate it, and rerender.
- Never infer shared task identity from matching names.

## Canonical model

- Every task has a unique 12-character hexadecimal ID, completion state, and
  dependency list.
- Priority is optional and ordered by `schema/priority.schema.json`.
- A dependency may have the same or lower priority than the task that depends on
  it, never a higher priority.
- A completed task may not have an incomplete dependency.
- Categories are explicit named collections through category memberships.
- Category membership and dependency relationships are independent.
- Ambiguities are validation errors. `--strict` promotes advisory warnings to
  errors.

## Commands

```text
bin/validate-todos todos/YYYY-MM-DD/todo.json
bin/convert-todos todos/YYYY-MM-DD
bin/render-todos --replace todos/YYYY-MM-DD/todo.json
bin/sync-todos todos/YYYY-MM-DD/todo.json
bin/generate-todos --date YYYY-MM-DD
bin/generate-todos --date YYYY-MM-DD --previous PATH --output PATH
bin/create-daily-todo --date YYYY-MM-DD
```

`bin/generate-todos` owns scheduler-independent canonical creation and
carry-forward. `bin/create-daily-todo` is the thin render-enabled entry point for
schedulers. Schedulers must not duplicate generation logic.

Input and output paths are configurable. Alternate outputs never overwrite
existing files unless the relevant command explicitly receives `--replace`.
Combined Markdown is presentation-only and cannot be synchronized. `--strict`
promotes warnings for conversion, validation, rendering, synchronization, and
generation.

Canonical generation reads daily category definitions from
`config/task-types.conf`. The legacy priority and due-kind configuration files
do not define canonical schema values.

The old `bin/todo` implementation remains only as migration reference. Do not
use its Markdown validator, generator, exporter, or mutation commands with
canonical data. Those commands are guarded against accidental execution.
`bin/todo-config add-type` remains usable for canonical daily categories; its
priority and due-kind operations affect only the legacy implementation.

## Verification

```text
python3 tests/test_schema_validation.py
python3 tests/test_markdown_conversion.py
python3 tests/test_markdown_rendering.py
python3 tests/test_checkbox_sync.py
python3 tests/test_canonical_generation.py
python3 tests/test_generation_independent.py
python3 tests/test_legacy_guard.py
python3 tests/test_repository_privacy.py
plutil -lint launchd/local.daily-todo.plist.in
```

Never install or enable `launchd`, create or modify a scheduled Codex task, make
a Git commit, or disable another task without explicit user approval.

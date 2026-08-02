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

Tasks and subtasks share the same recursive structure. Category comes from the
filename and priority comes from the second-level heading. Backlog task types do
not use priorities.

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

After changing task data or implementation, run:

```text
bin/validate-todos --fix
bin/todo list --date YYYY-MM-DD
python3 tests/test_generation_independent.py
python3 tests/test_schema_validation.py
```

`bin/validate-todos` is scheduler-independent. It parses Markdown into recursive
task objects, validates them directly against `schema/task.schema.json`, and
also enforces configured deadline kinds and hierarchy rules.

Generation validates the previous daily directory against both the task schema
and referenced `schema/due.schema.json` before creating the new directory, then
validates the generated files again after writing them.

When changing the scheduler template, also run:

```text
plutil -lint launchd/local.daily-todo.plist
```

Never install or enable `launchd`, create or modify a scheduled Codex task, make
a Git commit, or disable another task without explicit user approval.

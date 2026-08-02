# Repository guidance

This repository is a Markdown-first task system. Markdown under `todos/` and
`backlog/` is authoritative; JSON is only an export and validation model.

## Before changing tasks

- Read `config/task-types.conf` and `config/priorities.conf`; never hard-code
  category or priority names.
- Use `bin/todo` when practical. Direct Markdown edits are supported.
- Preserve task IDs in `<!-- task:xxxxxxxxxxxx -->` comments.
- If a manually added task lacks an ID, run `bin/todo validate --fix`.
- Do not overwrite an existing daily directory or remove historical tasks.

## Task syntax

```markdown
- [ ] **Short name** <!-- task:12-hex-digits -->
  Optional description.
  - [ ] **Subtask name** <!-- task:12-hex-digits -->
    Optional subtask description.
```

Tasks and subtasks share the same recursive structure. Category comes from the
filename and priority comes from the second-level heading. Backlog task types do
not use priorities.

Do not mark a parent complete while it contains an unchecked subtask. The daily
carry-forward operation copies unchecked tasks, descriptions, and unchecked
descendants; completed tasks remain only in historical files.

## Natural-language requests

For requests such as “add X to Household as Must,” translate the configured
display names to their slugs and run `bin/todo add`. Resolve a parent by stable
ID before adding a subtask. If a name matches multiple tasks, ask which one.

Examples:

```text
bin/todo add --type household --priority Must "Replace furnace filter"
bin/todo add --type someday "Learn woodworking"
bin/todo add --parent abc123def456 "Buy replacement filter"
bin/todo complete abc123def456
```

## Verification

After changing task data or implementation, run:

```text
bin/todo validate --fix
bin/todo list --date YYYY-MM-DD
```

When changing the scheduler template, also run:

```text
plutil -lint launchd/local.daily-todo.plist
```

Never install or enable `launchd`, create or modify a scheduled Codex task, make
a Git commit, or disable another task without explicit user approval.

# Daily TODO

Daily TODO is a local canonical-JSON task system with ID-free Markdown views,
schema and semantic validation, checkbox synchronization, carry-forward, and an
optional macOS schedule. Personal list data under `todos/` and `backlog/` is
ignored by Git.

Run `bin/setup`, then either invoke `bin/todo` directly or source `activate.sh`
to make `todo` available in the current shell. Every data-transforming command
prints to standard output by default. Pass `--output PATH` to persist a result;
an existing destination requires `--replace`. Commands never discover list
storage implicitly.

## Commands

Create or inspect tasks:

```text
todo task add todo.json "Draft proposal" --category work --priority should
todo task add todo.json "Write section" --category work --dependency-of "Draft proposal"
todo task edit todo.json "Draft proposal" --name "Draft project proposal"
todo task complete todo.json "Draft project proposal"
todo task reopen todo.json "Draft project proposal"
todo task remove todo.json "Draft project proposal"
todo task show todo.json "Draft project proposal"
todo task list todo.json
```

Mutating task commands still print the prospective JSON unless `--output` is
provided. To replace the input explicitly, use `--output todo.json --replace`.
Task and category selectors match an ID first, then an exact unique name.
`--depends-on` makes the new task depend on an existing task;
`--dependency-of` adds the new task as a dependency of an existing task.
Priority choices come from `schema/priority.schema.json`.

Create and validate lists:

```text
todo list create --date 2026-08-03
todo list create --date 2026-08-03 --previous prior.json --output next.json
todo list validate todo.json
todo list validate --strict path/to/lists
```

`todo list create` carries incomplete tasks from an explicitly supplied prior
list. It does not render Markdown or inspect a scheduler.

Render and synchronize ID-free Markdown views:

```text
todo view render todo.json
todo view render todo.json --output combined.md
todo view render todo.json --output-dir review
todo view sync todo.json --view-dir review
todo view sync todo.json --view-dir review --output todo.json --replace
```

Only checkbox markers may be edited in generated category views. Structural
edits and conflicting states across repeated task appearances fail. Combined
Markdown is presentation-only and cannot be synchronized.

Import legacy Markdown, and manage category configuration:

```text
todo import markdown path/to/dated-markdown
todo category list
todo category add travel "Travel"
todo category rename travel "Trips and Travel"
todo category remove travel
```

Category configuration changes affect future list creation only; they do not
rewrite existing canonical documents.

## Canonical model and validation

Every task has a UUIDv4 ID, completion state, dependency list, explicit category
membership, and optional priority, description, and deadline. Dependencies may
have the same or lower priority than tasks that depend on them. Completed tasks
cannot have incomplete dependencies. Validation detects invalid schemas,
unresolved or duplicate references, cycles, completion inconsistency, priority
inversions, invalid dates, and conflicting repeated checkboxes. Advisory issues
become errors under `--strict`.

## Optional macOS schedule

The scheduler adapter runs at 5:55 AM, computes explicit current- and
previous-day paths, creates canonical JSON, then renders category views as a
separate operation. Manage it with:

```text
todo schedule install
todo schedule status
todo schedule uninstall
```

Installation writes and loads
`~/Library/LaunchAgents/local.daily-todo.plist`. Use `--replace` to replace an
existing installation. Scheduling is optional; all list and view commands work
without it.

## Development

```text
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mypy
plutil -lint launchd/local.daily-todo.plist.in
```

See `INSTALL.md` for setup details and `AGENTS.md` for repository invariants.

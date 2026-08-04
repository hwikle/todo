# Daily TODO

Daily TODO is a local canonical-JSON task system with ID-free Markdown views,
schema and semantic validation, checkbox synchronization, carry-forward, and an
editable browser checklist, plus an optional macOS schedule. Personal list data
under `todos/` and `backlog/` is ignored by Git.

Run `bin/setup`, then either invoke `bin/todo` directly or source `activate.sh`
to make `todo` available in the current shell. Every data-transforming command
prints to standard output by default. Pass `--output PATH` to persist a result;
an existing destination requires `--replace`. Commands never discover list
storage implicitly.

Run `todo --help` or `todo COMMAND --help` to explore the interface. If a
command is incomplete or an argument is invalid, `todo` prints the relevant
command help together with the error so the invocation can be corrected in
place.

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
todo list create --date 2026-08-03 --category work=Work --category learning=Learning
todo list create --date 2026-08-03 --previous prior.json --output next.json
todo list validate todo.json
todo list validate --strict path/to/lists
```

`todo list create` carries incomplete tasks and categories from an explicitly
supplied prior list. A first list instead requires one or more explicit
`--category ID=NAME` arguments. It does not render Markdown or inspect a
scheduler.

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

Import legacy Markdown:

```text
todo import markdown path/to/dated-markdown
```

## Browser checklist

Open one explicitly selected canonical-list path in the local checklist editor:

```text
todo serve path/to/todo.json
```

Then visit `http://127.0.0.1:8000`. If the file does not exist, the browser
asks for the date and initial categories; no CLI creation step is required.
Starting the server alone does not create the file. The
command does not search for a list or generate Markdown, and it edits only the
explicit path named on the command line.

The checklist autosaves task names, descriptions, completion state, categories,
priorities, deadlines, ordering, and nesting. Press Enter in a task name to create a new
sibling, Tab to make it a subtask of the preceding task, Shift+Tab to move it
out one level, Shift+Enter to add or focus its description, and Option+Up or
Option+Down to reorder it in manual sort mode. Empty categories
contain a blank editable line for their first task. Blank new lines remain local
to the browser; named new tasks are created when Enter is pressed or focus
leaves the line. Empty description editors disappear without creating a
description. Categories can be added, renamed, reordered, and
removed from the checklist; a category must be empty before removal. Category
and priority filters can be combined;
matching tasks are the primary results, while all of their transitive
dependencies remain visible.

In manual sort mode, hover over a task and drag its handle to move it. Drop near
the top or bottom of another task to place it before or after that task, or drop
in the center to make it a dependency. While dragging within a nested branch,
an explicit target appears for moving the task out one level. Deadline-sorted
views are read-only with respect to ordering; switch back to manual sorting to
drag or use Option+Up and Option+Down.

Task priority is visible alongside each task. Deadlines use an explicit year,
month, or day precision; time is available only for day-precision deadlines.
Sorting by deadline leaves undated tasks last and treats a partial deadline as
the end of its stated period without changing the stored precision. Text inside
backticks is displayed in monospace and remains editable as ordinary text.

Distinct tasks may have the same name. The editor identifies them by their
canonical IDs internally, so editing or deleting one does not select another by
name. If a task cannot be deleted because other tasks depend on it, the editor
identifies those parent tasks and leaves the file unchanged.

Every save includes the revision originally loaded by the browser. If another
program changes the JSON file first, autosave stops and reports a conflict
instead of overwriting that change. Invalid edits likewise remain unsaved and
display the canonical validation error.

The server listens only on `127.0.0.1` by default. Flask identifies it as a
development server because this command is intended for a single-user local
workflow, not deployment on a shared or public network. `--host` and `--port`
are available when an explicit alternative is needed.

## Canonical model and validation

Every task has a UUIDv4 ID, completion state, dependency list, explicit category
membership, and optional priority, description, and deadline. Dependencies may
have the same or lower priority than tasks that depend on them. Completed tasks
cannot have incomplete dependencies. Validation detects invalid schemas,
unresolved or duplicate references, cycles, completion inconsistency, priority
inversions, invalid dates, and conflicting repeated checkboxes. Advisory issues
become errors under `--strict`.

## Optional macOS schedule

Scheduling uses an ignored, machine-local `config/schedule.json`. It records
the repository and list-storage directories and the local generation time.
Create it with explicit values before installing:

```text
todo schedule configure \
  --lists-dir /absolute/path/to/lists \
  --generation-time HH:MM
todo schedule show
todo schedule install
todo schedule status
todo schedule uninstall
```

The launchd job computes explicit current- and previous-day paths, creates
canonical JSON, and then renders category views as a separate operation.
The first scheduled run therefore requires an existing prior list; create the
initial list explicitly in the browser or with `todo list create --category`.
Notification delivery and Codex integration are deliberately outside this
program's responsibilities. Installation writes and loads
`~/Library/LaunchAgents/local.daily-todo.plist`. Use `--replace` when replacing
existing configuration or installation files. Scheduling is optional; all list
and view commands work without it.

## Development

```text
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mypy
```

See `INSTALL.md` for setup details and `AGENTS.md` for repository invariants.

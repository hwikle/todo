# Repository guidance

This repository contains software for managing TODO lists. User data under
`todos/` and `backlog/` is local, ignored by Git, and must not be added to
repository history.

## Source of truth

- Canonical lists are JSON documents; Markdown files are deterministic, ID-free views.
- Never infer shared task identity from matching names.
- Only checkbox markers may be edited in generated Markdown.
- Synchronization must reject structural edits and conflicting repeated states.
- Priority and deadline-kind values come from canonical schemas.
- Each canonical list's `categories` array is the only category source of truth.
- Machine-local scheduling configuration lives in ignored `config/schedule.json`.

## Command boundaries

- `todo task` owns canonical task inspection and mutation.
- `todo list` owns list creation and validation.
- `todo view` owns Markdown rendering and checkbox synchronization.
- `todo import` owns conversion from external formats.
- `todo schedule` owns the optional local `launchd` lifecycle.
- `todo serve` owns the explicit-file local HTTP adapter and browser checklist.
- `bin/setup` owns local dependency installation.

Commands must not discover list storage. Data transformations print to stdout
unless `--output` is explicit, and must not overwrite without `--replace`.
List creation must remain independent from rendering and scheduling. The
scheduler adapter may compose those commands using explicit paths but must not
duplicate their domain logic.

The browser adapter must use the shared application operations, validate every
prospective canonical document, and write atomically. Browser saves must carry
a revision token and reject stale writes. Filtering, grouping, contextual
dependency display, and transient blank lines are view concerns and must not be
persisted in canonical JSON.

The browser owns in-list category management, ordering and deadline-sort views,
and display-only inline-code formatting. Sorting must not rewrite manual order;
partial deadlines retain their original precision in storage.
Drag-and-drop and keyboard movement must call the same application-layer move
operations, identify occurrences by task ID plus displayed parent and category,
and remain disabled in non-manual sort views.
Drag feedback must be an overlay and must not insert layout-affecting targets or
move checklist content while the pointer is choosing a destination.
Necessary rerenders must preserve the active task occurrence, unsaved editor
value, selection range, and the user's newer focus. Placeholder text must never
be promoted into canonical task content.

The browser must remain independently usable: an explicitly named missing list
path enters a first-run state and is created only after an explicit browser
action with explicit categories. Empty categories must expose an in-place
first-task line. Client-side
identity, focus restoration, edits, nesting, and deletion must use canonical
task IDs and occurrence context, never task names or whole-document ID-set
inference.
Schema-valid lists with representable semantic errors are opened only through
explicit repair mode. Repair edits remain in memory until the entire document
is valid, then save atomically. Malformed, schema-invalid, or ambiguously
identifiable documents must fail with actionable source-file diagnostics rather
than being partially rendered.
Browser presentation configuration is explicit, schema-validated, and separate
from canonical TODO data. Priority colors must remain textual badges as well as
color cues; validation errors use a separate visual treatment and identify
every affected canonical task occurrence.

## Canonical invariants

- Task IDs are unique canonical UUIDv4 strings.
- Dependency and category references resolve uniquely.
- Dependencies are acyclic and must have the same or higher urgency than their
  parents. Unprioritized dependencies are valid only for Could or unprioritized
  parents.
- Completed tasks have no incomplete dependencies.
- Category assignment is explicit and independent of dependency relationships.
- Global task deletion atomically removes all incoming dependency references;
  occurrence-specific detachment removes only the displayed parent edge.
- Ambiguity is an error; `--strict` promotes advisory warnings to errors.

## Verification

```text
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mypy
```

Never install or remove the `launchd` job, modify an external scheduled Codex
task, commit changes, or rewrite history without explicit user approval.

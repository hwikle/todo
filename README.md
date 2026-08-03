# Daily TODO

A local, version-controlled, Markdown-first daily task system. Each day has a
directory of category files. Unchecked tasks carry forward with their optional
descriptions and recursively nested subtasks.

## Layout

```text
backlog/someday.md             Persistent unprioritized ideas
bin/todo                       Task CLI and validator
bin/create-daily-todo          Daily generator entry point
bin/generate-todos             Scheduler-independent canonical generator
bin/convert-todos             Markdown-to-canonical-JSON converter
bin/render-todos              Canonical-JSON-to-Markdown renderer
bin/sync-todos                Checkbox-only Markdown synchronizer
bin/todo-config                Configuration helper entry point
bin/validate-todos             Standalone schema validator
bin/setup                      Local dependency setup
config/task-types.conf         Flexible category definitions
config/priorities.conf         Flexible ordered priorities
config/due-kinds.conf          Flexible deadline classifications
launchd/*.plist                Optional macOS scheduler template
schema/due-date.schema.json    Partial-precision deadline contract
schema/category.schema.json    Category identity and display-name contract
schema/priority.schema.json    Must/Should/Could priority contract
schema/task.schema.json        Canonical task definition contract
schema/todo-list.schema.json   Canonical daily-list contract
todos/YYYY-MM-DD/*.md          Authoritative daily checklists
```

See `INSTALL.md` for initial setup and dependency-management instructions.

The initial daily categories are Work, Learning, Software Projects, Finance,
Health, Household, and Errands. Someday is a persistent backlog. Initial
priorities are Must, Should, and Could. These names are configuration, not code.

## Generation is independent from scheduling

Daily-list creation is a standalone operation:

```text
bin/create-daily-todo
bin/create-daily-todo --date 2026-08-03
```

The first command uses the current local date. The second supports testing,
backfilling, or use by another automation system. Neither command checks for or
depends on `launchd`, Codex, or any scheduler state.

`bin/generate-todos` owns canonical creation and carry-forward without reading
any scheduler state. `bin/create-daily-todo` is a thin entry point that requests
both canonical generation and Markdown rendering. Scheduler configurations only
decide when to invoke that entry point. The 6:00 AM Codex check-in is
intentionally read-only with respect to generation.

## Markdown format

```markdown
# Work — 2026-08-02

## Must

- [ ] Prepare quarterly report <!-- task:abc123def456 due:2026-08-03 time:10:30 due-kind:hard -->
    Due: August 3, 2026 at 10:30 AM — Hard deadline.
    Assemble final financial and operational results.
    - [ ] Collect department figures <!-- task:def456abc123 -->
        Request final figures from accounting.
```

You may edit these files directly. IDs are stable identifiers used for
carry-forward and conversational changes. Omit an ID when editing manually, then
run `bin/todo validate --fix` to assign one.

## Common commands

Validate canonical JSON independently of generation or scheduling:

```text
bin/validate-todos path/to/todo-list.json
bin/validate-todos --strict path/to/todo-list.json
```

Convert one legacy daily Markdown directory without reusing embedded task IDs:

```text
bin/convert-todos --stdout todos/2026-08-02
bin/convert-todos todos/2026-08-02
```

Each Markdown occurrence becomes a distinct canonical task with a fresh ID.
Four-space nesting becomes dependency references, and nested tasks inherit the
priority of their Markdown section. Conversion validates the complete document
and refuses to overwrite an existing `todo.json`.

Render validated canonical JSON as ID-free category Markdown:

```text
bin/render-todos --output-dir /path/to/review todos/2026-08-02/todo.json
bin/render-todos --replace todos/2026-08-02/todo.json
```

Every category member appears in its own priority section. Dependencies are also
rendered recursively beneath tasks that depend on them, so one canonical task
may appear more than once. A nested task displays its priority when it differs
from the surrounding section.

Synchronize checkbox-only edits back into canonical JSON:

```text
bin/sync-todos todos/2026-08-02/todo.json
```

Synchronization rerenders the expected view in memory and requires every file,
line, task name, description, deadline, and indentation character to match.
Only checkbox markers may differ. Conflicting states across repeated appearances
are errors, and canonical JSON is updated atomically only after validation.

> **Schema transition:** The schemas now describe the forthcoming canonical JSON
> model. The current Markdown validator and generator still emit the legacy
> recursive `subtasks` model, so do not run them until the validation and
> conversion phase is complete.

The standalone canonical validator is available during this transition. It
performs Draft 2020-12 schema validation, reference and dependency-graph checks,
calendar validation, category-membership checks, and priority-order checks.
Ambiguities are errors. Advisory conditions are warnings unless `--strict`
promotes them to errors.

In the canonical model, priority is an optional property of each task. Category
definitions contain stable IDs and display names, while separate category
memberships associate categories with tasks. Categories and memberships do not
imply files, hierarchy, root tasks, or any particular rendering. A Markdown view
may group tasks within category files under Must, Should, and Could headings;
tasks without a priority may render in an unprioritized section.

Add tasks:

```text
bin/todo add --type work --priority Must "Prepare quarterly report"
bin/todo add --type health --priority Should \
  --description "Call the clinic before noon." "Schedule annual physical"
bin/todo add --type health --priority Must --due-date 2026-08-03 \
  --due-time 10:30 --due-kind hard "Submit quarterly report"
bin/todo add --type someday "Learn woodworking"
bin/todo add --parent abc123def456 "Write executive summary"
bin/todo complete abc123def456
bin/todo reopen abc123def456
```

Inspect tasks and configuration:

```text
bin/todo list
bin/todo types
bin/todo priorities
bin/todo due-kinds
bin/todo export
```

Add configuration without changing code:

```text
bin/todo-config add-type travel "Travel"
bin/todo-config add-priority 15 "Time-sensitive"
bin/todo-config add-due-kind 75 firm "Firm commitment"
```

The numeric priority value controls display order. Due-kind weights allow more
classifications without changing task data or code. Backlog types can be added
with `--behavior backlog`.

Due dates are optional. A due time requires a date, and every dated task must
reference a configured due kind. Times are interpreted in the Mac's local time.

## Carry-forward rules

- Existing canonical lists are never overwritten by generation.
- The latest prior canonical list is schema- and semantics-validated first.
- Incomplete tasks retain IDs, metadata, priority, category memberships, and
  still-relevant dependency references.
- Completed tasks remain historical and do not carry forward.
- Newly configured daily categories are added without dropping prior category
  definitions.
- The complete generated document is validated before being written atomically.
- Rendering is optional and does not contain generation logic.

Run the scheduler-independence regression test with:

```text
python3 tests/test_generation_independent.py
python3 tests/test_schema_validation.py
```

## Optional launchd schedule (5:55 AM)

The version-controlled template is
`launchd/local.daily-todo.plist`. Installation is intentionally manual and
requires explicit approval because it writes outside this repository.

Before installation, create the log directory and validate the template:

```text
mkdir -p $TODO_REPO/.logs
plutil -lint $TODO_REPO/launchd/local.daily-todo.plist
```

Install a copy and enable it for the current user:

```text
cp $TODO_REPO/launchd/local.daily-todo.plist \
  $HOME/Library/LaunchAgents/local.daily-todo.plist
launchctl bootstrap gui/$(id -u) \
  $HOME/Library/LaunchAgents/local.daily-todo.plist
```

Run it immediately for verification:

```text
launchctl kickstart -k gui/$(id -u)/local.daily-todo
```

Disable it before changing the installed file:

```text
launchctl bootout gui/$(id -u)/local.daily-todo
```

After disabling it, the installed plist may be removed. The repository template
and generated TODO history are unaffected. Logs live under `.logs/` and are
ignored by Git.

## Scheduled Codex check-in (6:00 AM)

Use a scheduled task inside one persistent conversation associated with this
local project. Its responsibility is to read—not generate—today's Markdown,
render the checklist in the conversation, and report a missing or invalid daily
directory. Conversational requests can then update the repository.

The rendered checklist is a snapshot. Toggling a rendered checkbox is not a
reliable synchronization mechanism. Ask Codex to complete a task by name or ID,
or edit the Markdown file directly. ChatGPT desktop completion notifications can
alert you when the 6:00 AM message is ready if notifications are enabled.

Do not run a second daily generator from Codex while `launchd` is enabled. Keep
the Mac on for both schedules; keep ChatGPT desktop running for the Codex task.

Suggested scheduled prompt:

```text
At 6:00 AM local time, return to this conversation. In $TODO_REPO, validate
today's TODO directory without changing task content. If it is missing or
invalid, report the problem clearly and stop. Otherwise read every configured
daily category file and post one concise rendered Markdown checklist, grouped by
category and then priority. Include each task's short ID. Treat repository
Markdown as authoritative and do not run the daily generator.
```

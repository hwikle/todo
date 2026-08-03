# Daily TODO

A local canonical-JSON task system with ID-free Markdown views, validation,
checkbox synchronization, daily carry-forward, and optional macOS scheduling.
The repository contains software only; personal data under `todos/` and
`backlog/` is ignored by Git.

## Layout

```text
bin/convert-todos              Legacy Markdown-to-JSON migration
bin/render-todos               ID-free Markdown rendering
bin/sync-todos                 Checkbox-only view synchronization
bin/validate-todos             Canonical schema and semantic validation
bin/generate-todos             Scheduler-independent daily generation
bin/create-daily-todo           Render-enabled scheduler entry point
bin/setup                       Local dependency setup
bin/install-launchd             Render and install the optional macOS schedule
lib/                            Canonical implementation
schema/                         JSON Schema contracts
tests/                          Synthetic regression tests
launchd/                        Optional macOS scheduler template
todos/YYYY-MM-DD/todo.json      Ignored canonical user data
todos/YYYY-MM-DD/*.md           Ignored generated category views
```

See `INSTALL.md` for setup instructions.

All transformation commands accept explicit input paths. Alternative output
paths are supported where a command writes data; existing alternate outputs are
not overwritten unless `--replace` is explicitly available and supplied.

## Canonical workflow

Validate a daily list:

```text
bin/validate-todos todos/2026-08-02/todo.json
bin/validate-todos --strict todos/2026-08-02/todo.json
```

Render ID-free Markdown views:

```text
bin/render-todos --output-dir /path/to/review todos/2026-08-02/todo.json
bin/render-todos --replace todos/2026-08-02/todo.json
```

Without `--output-dir`, category files are written beside the input JSON.
Existing category files require `--replace`.

Every explicit category member appears in its own priority section.
Dependencies are also rendered recursively, so one canonical task may appear
more than once. Nested tasks display their priority when it differs from the
surrounding section.

Render all categories into one presentation document:

```text
bin/render-todos --combined-output /path/to/todo.md path/to/todo.json
bin/render-todos --stdout path/to/todo.json
```

Combined views preserve canonical category order and separate categories with
Markdown horizontal rules. They are presentation outputs and are not
synchronization inputs. An existing `--combined-output` file requires
`--replace`.

After editing checkbox markers in Markdown, synchronize them into JSON:

```text
bin/sync-todos todos/2026-08-02/todo.json
bin/sync-todos --output /path/to/updated.json todos/2026-08-02/todo.json
bin/sync-todos --stdout todos/2026-08-02/todo.json
bin/sync-todos --dry-run todos/2026-08-02/todo.json
```

Synchronization requires every non-checkbox character to match a fresh
canonical render. Structural edits and conflicting states across repeated
appearances fail without changing JSON. By default, category views are read from
the input JSON's directory and the JSON is updated in place. `--view-dir`
selects another category-view directory. `--output` refuses existing files and
must differ from the input; `--stdout` and `--dry-run` never write.

## Daily generation

Generate canonical JSON without involving a scheduler:

```text
bin/generate-todos
bin/generate-todos --date 2026-08-03
bin/generate-todos --date 2026-08-03 --previous /path/to/prior.json \
  --output /path/to/generated.json
```

Without `--previous`, generation discovers the latest earlier `todo.json`
beneath `--data-dir` (default: `todos/`). Without `--output`, it writes
`<data-dir>/<date>/todo.json`. An explicit output path does not change where an
implicit previous list is discovered. `--render` writes category views beside
the selected JSON output. Explicit previous lists must predate the target.

Generate JSON and category views through the scheduler entry point:

```text
bin/create-daily-todo
bin/create-daily-todo --date 2026-08-03
```

This entry point accepts the generator's path options and always enables
rendering. If the target JSON already exists, generation exits successfully
without changing JSON or Markdown.

Generation validates the latest prior canonical list, carries incomplete tasks
with stable IDs and live dependency references, retains explicit memberships,
adds newly configured daily categories, validates the new document, and writes
atomically. Existing canonical lists are never overwritten.

## One-time Markdown migration

Convert a dated directory of legacy category Markdown:

```text
bin/convert-todos --stdout todos/2026-08-02
bin/convert-todos todos/2026-08-02
```

The converter does not rely on Markdown IDs. Every occurrence receives a fresh
ID, four-space nesting becomes dependencies, every category assignment is
explicit, and identical names remain distinct. Output defaults to
`<source>/todo.json`; `--output` selects another path, `--stdout` writes
nothing, and existing output is never replaced.

## Validation policy

Validation combines Draft 2020-12 schemas with whole-document checks for:

- Unique task and category IDs.
- Resolved dependency and category references.
- Dependency cycles and self-dependencies.
- Completion consistency.
- Ordered dependency priorities.
- Real calendar dates.
- Duplicate category/task memberships.
- Conflicting repeated checkbox states during synchronization.

Missing priorities, uncategorized tasks, empty categories, multiple-category
membership, and duplicate category display names are warnings. `--strict`
promotes them to errors. Structural ambiguity is always an error.

The same `--strict` policy is available during conversion, rendering,
synchronization, and generation. Due dates support year, optional month,
optional day, and optional time in progressively specific order.

## Category configuration

Canonical generation reads daily categories from `config/task-types.conf`.
Add a category without changing code with:

```text
bin/todo-config add-type travel "Travel"
```

The legacy priority and due-kind configuration commands do not change the
canonical `must`/`should`/`could` and `hard`/`soft` schema values.

## Optional launchd schedule

The neutral template `launchd/local.daily-todo.plist.in` invokes
`bin/create-daily-todo` at 5:55 AM. The installer substitutes the current
repository path when it creates a machine-local property list. Review the
rendered file before enabling it:

```text
bin/install-launchd
plutil -lint "$HOME/Library/LaunchAgents/local.daily-todo.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/local.daily-todo.plist"
```

Do not enable a second daily generator in Codex while `launchd` is active.

## Scheduled Codex check-in

A 6:00 AM Codex task can return to one persistent conversation, validate the
canonical JSON, and display the generated Markdown. It should not generate the
day itself. ChatGPT-rendered checkboxes are snapshots; synchronize local
Markdown checkbox edits with `bin/sync-todos`.

Suggested prompt:

```text
At 6:00 AM local time, return to this conversation. In the Daily TODO
repository, locate today's todos/YYYY-MM-DD/todo.json and validate it without
modifying task data.
If it is missing or invalid, report the problem and stop. Otherwise read the
generated category Markdown files and post one concise checklist grouped by
category and priority. Do not expose task IDs and do not run generation.
```

## Legacy implementation

`bin/todo` retains the earlier Markdown-first generator and mutation code as a
migration reference. It is incompatible with canonical data and must not be
used for current lists, and its data commands are guarded against accidental
execution. Configuration inspection remains available. Remove the legacy code
only after canonical parity is considered complete.

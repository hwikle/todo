# Daily TODO

A local, version-controlled, Markdown-first daily task system. Each day has a
directory of category files. Unchecked tasks carry forward with their optional
descriptions and recursively nested subtasks.

## Layout

```text
backlog/someday.md             Persistent unprioritized ideas
bin/todo                       Task CLI and validator
bin/create-daily-todo          Daily generator entry point
bin/todo-config                Configuration helper entry point
config/task-types.conf         Flexible category definitions
config/priorities.conf         Flexible ordered priorities
launchd/*.plist                Optional macOS scheduler template
schema/task.schema.json        Recursive task data contract
todos/YYYY-MM-DD/*.md          Authoritative daily checklists
```

The initial daily categories are Work, Learning, Software Projects, Finance,
Health, Household, and Errands. Someday is a persistent backlog. Initial
priorities are Must, Should, and Could. These names are configuration, not code.

## Markdown format

```markdown
# Work — 2026-08-02

## Must

- [ ] **Prepare quarterly report** <!-- task:abc123def456 -->
  Assemble final financial and operational results.
  - [ ] **Collect department figures** <!-- task:def456abc123 -->
    Request final figures from accounting.
```

You may edit these files directly. IDs are stable identifiers used for
carry-forward and conversational changes. Omit an ID when editing manually, then
run `bin/todo validate --fix` to assign one.

## Common commands

Create or validate today's files:

```text
bin/create-daily-todo
bin/todo validate --fix
```

Add tasks:

```text
bin/todo add --type work --priority Must "Prepare quarterly report"
bin/todo add --type health --priority Should \
  --description "Call the clinic before noon." "Schedule annual physical"
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
bin/todo export
```

Add configuration without changing code:

```text
bin/todo-config add-type travel "Travel"
bin/todo-config add-priority 15 "Time-sensitive"
```

The numeric priority value controls display order. Backlog types can be added
with `--behavior backlog`.

## Carry-forward rules

- Existing files for today are never overwritten by generation.
- Unchecked tasks carry into the same category and priority.
- Descriptions and unchecked subtasks carry with their parent.
- Completed tasks and completed subtasks remain in historical files.
- A completed parent with an unchecked descendant fails validation.
- A removed category or priority is preserved while it still has unchecked work.

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

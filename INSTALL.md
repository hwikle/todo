# Installation

Daily TODO requires Python 3.9 or newer. macOS is required only for the optional
`launchd` integration.

From the repository root, create the local virtual environment and install the
locked dependencies:

```text
bin/setup
```

Either run `bin/todo` directly or add it to the current shell:

```text
source activate.sh
todo --help
```

The same installation includes the local browser checklist. Start it with an
explicit canonical file and open the displayed loopback address:

```text
todo serve path/to/todo.json
```

The path may be new. In that case, create the list from the browser's first-run
screen; running a separate CLI creation command is not required.

No separate JavaScript toolchain or production web server is required for the
single-user local workflow.

`activate.sh` changes only the current shell's `PATH`. It does not modify shell
startup files or install anything globally. Command wrappers select the
repository-local environment regardless of the current working directory.

To recreate the environment, remove `.venv/` and rerun `bin/setup`. Dependency
intent is recorded in `pyproject.toml`; exact versions are in
`requirements.lock`.

Run development checks with:

```text
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mypy
```

Optional scheduling is installed only by an explicit command:

```text
todo schedule configure \
  --lists-dir /absolute/path/to/lists \
  --generation-time HH:MM
todo schedule show
todo schedule install
todo schedule status
```

The configuration is stored locally in ignored `config/schedule.json`; no time
or user-specific storage path is embedded in the software. Installation writes
and loads `~/Library/LaunchAgents/local.daily-todo.plist`. Remove it with
`todo schedule uninstall`. The ordinary task, list, view, import, category, and
serve commands neither inspect nor modify scheduler state. The application does
not send notifications or invoke Codex.

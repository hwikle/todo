# Installation

Daily TODO requires macOS or another Unix-like system, Python 3.9 or newer, and
Git. Dependencies are installed in a repository-local virtual environment; the
setup process does not modify the system Python installation.

## Initial setup

From the repository root, run:

```text
bin/setup
```

This creates `.venv/` and installs the exact dependency versions recorded in
`requirements.lock`. The environment is local to this repository and is not
committed to Git.

Validate a canonical TODO-list JSON document with:

```text
bin/validate-todos path/to/todo-list.json
```

Warnings are reported without causing failure. To promote warnings to errors:

```text
bin/validate-todos --strict path/to/todo-list.json
```

The `todos/` and `backlog/` directories are created by commands as needed and
are ignored by Git. No user task data is installed or version-controlled.

Run any repository command from another directory by using its absolute path;
input and output paths themselves may also be absolute. Command wrappers locate
the repository-local environment independently of the current directory.

## Recreate the environment

Remove `.venv/` and run `bin/setup` again. No global package cleanup is needed.

## Update dependencies

Dependency intent is recorded in `pyproject.toml`; exact resolved versions are
recorded in `requirements.lock`. Update dependencies deliberately in a fresh
environment. Install the dependency constraint recorded in `pyproject.toml`,
test the validator, and regenerate the lock file with:

```text
.venv/bin/python -m pip install 'jsonschema>=4,<5'
.venv/bin/python -m pip freeze > requirements.lock
```

Review both the dependency changes and validation results before committing an
updated lock file.

## Scheduling note

The optional `launchd` workflow invokes `bin/create-daily-todo`, not a global
Python executable. Repository commands select the local environment and keep
scheduled behavior consistent with interactive use. Installing or enabling the
scheduler remains an explicit manual step because it writes outside the
repository.

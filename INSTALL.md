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

## Recreate the environment

Remove `.venv/` and run `bin/setup` again. No global package cleanup is needed.

## Update dependencies

Dependency intent is recorded in `pyproject.toml`; exact resolved versions are
recorded in `requirements.lock`. Update dependencies deliberately in a fresh
environment. Install the dependency constraint recorded in `pyproject.toml`,
test the validator, and regenerate the lock file with:

```text
.venv/bin/python -m pip freeze > requirements.lock
```

Review both the dependency changes and validation results before committing an
updated lock file.

## Scheduling note

The optional `launchd` workflow should invoke repository commands such as
`bin/create-daily-todo` and `bin/validate-todos`, rather than a global Python
executable. These commands can select the repository-local environment and keep
scheduled behavior consistent with interactive use. Do not install or enable
the scheduler until canonical generation and validation are fully integrated.

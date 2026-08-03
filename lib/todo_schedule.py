"""Validated scheduling configuration and launchd rendering."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import plistlib


class ScheduleConfigurationError(ValueError):
    """The local scheduling configuration is missing or invalid."""


@dataclass(frozen=True)
class ScheduleConfig:
    repository_directory: Path
    lists_directory: Path
    generation_time: dt.time
    codex_time: dt.time
    notifications: bool

    def to_json(self) -> str:
        document = {
            "repository_directory": str(self.repository_directory),
            "lists_directory": str(self.lists_directory),
            "generation_time": self.generation_time.strftime("%H:%M"),
            "codex_time": self.codex_time.strftime("%H:%M"),
            "notifications": self.notifications,
        }
        return json.dumps(document, indent=2) + "\n"


def parse_time(value: object, field: str) -> dt.time:
    if not isinstance(value, str):
        raise ScheduleConfigurationError(f"{field} must be a string in HH:MM format")
    try:
        parsed = dt.datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ScheduleConfigurationError(f"{field} must use 24-hour HH:MM format") from exc
    return parsed


def _absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ScheduleConfigurationError(f"{field} must be a non-empty path string")
    path = Path(value)
    if not path.is_absolute():
        raise ScheduleConfigurationError(f"{field} must be an absolute path")
    return path


def from_document(document: object) -> ScheduleConfig:
    if not isinstance(document, dict):
        raise ScheduleConfigurationError("schedule configuration must be a JSON object")
    expected = {
        "repository_directory", "lists_directory", "generation_time", "codex_time", "notifications"
    }
    keys = set(document)
    missing = expected - keys
    extra = keys - expected
    if missing:
        raise ScheduleConfigurationError(f"missing schedule fields: {', '.join(sorted(missing))}")
    if extra:
        raise ScheduleConfigurationError(f"unknown schedule fields: {', '.join(sorted(extra))}")
    notifications = document["notifications"]
    if not isinstance(notifications, bool):
        raise ScheduleConfigurationError("notifications must be true or false")
    return ScheduleConfig(
        repository_directory=_absolute_path(document["repository_directory"], "repository_directory"),
        lists_directory=_absolute_path(document["lists_directory"], "lists_directory"),
        generation_time=parse_time(document["generation_time"], "generation_time"),
        codex_time=parse_time(document["codex_time"], "codex_time"),
        notifications=notifications,
    )


def load(path: Path) -> ScheduleConfig:
    try:
        return from_document(json.loads(path.read_text()))
    except FileNotFoundError as exc:
        raise ScheduleConfigurationError(f"schedule configuration does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScheduleConfigurationError(f"invalid JSON in schedule configuration {path}: {exc}") from exc
    except OSError as exc:
        raise ScheduleConfigurationError(f"cannot read schedule configuration {path}: {exc}") from exc


def render_launchd(config: ScheduleConfig, label: str) -> str:
    root = config.repository_directory
    document = {
        "Label": label,
        "ProgramArguments": [str(root / "libexec" / "create-daily-todo")],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "TODO_LISTS_DIR": str(config.lists_directory),
            "TODO_NOTIFY": "1" if config.notifications else "0",
        },
        "StartCalendarInterval": {
            "Hour": config.generation_time.hour,
            "Minute": config.generation_time.minute,
        },
        "StandardOutPath": str(root / ".logs" / "daily-todo.out.log"),
        "StandardErrorPath": str(root / ".logs" / "daily-todo.err.log"),
    }
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=False).decode()

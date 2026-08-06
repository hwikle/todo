"""Schema-validated presentation configuration for the browser checklist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast

from yatl.schema import CanonicalSchemaBundle
from yatl.validation import json_path


class ColorPair(TypedDict):
    light: str
    dark: str


class BrowserConfig(TypedDict):
    priority_colors: dict[str, ColorPair]


DEFAULT_PRIORITY_COLORS: dict[str, ColorPair] = {
    "must": {"light": "#A65A00", "dark": "#F0A23A"},
    "should": {"light": "#245AA5", "dark": "#78A9E8"},
    "could": {"light": "#27705B", "dark": "#73BFA6"},
}


class BrowserConfigError(ValueError):
    """The explicitly selected browser configuration is unreadable or invalid."""


def load_browser_config(
    path: Path | None, bundle: CanonicalSchemaBundle
) -> BrowserConfig:
    configured: object = {}
    if path is not None:
        try:
            configured = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise BrowserConfigError(
                f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        except OSError as exc:
            raise BrowserConfigError(f"{path}: {exc}") from exc
    validator = bundle.validator_for("browser-config.schema.json")
    errors = sorted(
        validator.iter_errors(configured),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        details = "\n".join(
            f"{json_path(error.absolute_path)}: {error.message}" for error in errors
        )
        raise BrowserConfigError(f"invalid browser configuration:\n{details}")
    value = cast(dict[str, Any], configured)
    colors: dict[str, ColorPair] = {
        key: {"light": pair["light"], "dark": pair["dark"]}
        for key, pair in DEFAULT_PRIORITY_COLORS.items()
    }
    colors.update(cast(dict[str, ColorPair], value.get("priority_colors", {})))
    return {"priority_colors": colors}

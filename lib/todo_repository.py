"""Filesystem discovery and configuration adapters for canonical TODO workflows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

from todo_model import Category


class RepositoryError(Exception):
    """Local TODO repository state cannot be read safely."""


@dataclass(frozen=True)
class CategoryDefinition:
    id: str
    display_name: str
    behavior: str


def category_definitions(path: Path) -> list[CategoryDefinition]:
    definitions: list[CategoryDefinition] = []
    seen: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise RepositoryError(f"cannot read category configuration {path}: {exc}") from exc
    for line_number, raw in enumerate(lines, 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        parts = [part.strip() for part in value.split("|")]
        if len(parts) != 3:
            raise RepositoryError(f"{path}:{line_number}: expected slug|display name|behavior")
        category_id, display_name, behavior = parts
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", category_id):
            raise RepositoryError(f"{path}:{line_number}: invalid category ID {category_id!r}")
        if category_id in seen:
            raise RepositoryError(f"{path}:{line_number}: duplicate category ID {category_id!r}")
        if not display_name:
            raise RepositoryError(f"{path}:{line_number}: empty category display name")
        if behavior not in {"daily", "backlog"}:
            raise RepositoryError(f"{path}:{line_number}: invalid behavior {behavior!r}")
        seen.add(category_id)
        definitions.append(CategoryDefinition(category_id, display_name, behavior))
    return definitions


def configured_daily_categories(path: Path) -> list[Category]:
    return [
        {"id": item.id, "display_name": item.display_name}
        for item in category_definitions(path)
        if item.behavior == "daily"
    ]


def latest_previous_list(data_dir: Path, target_date: str) -> Optional[Path]:
    candidates: list[tuple[str, Path]] = []
    if not data_dir.exists():
        return None
    for child in data_dir.iterdir():
        if not child.is_dir() or child.name >= target_date:
            continue
        try:
            dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        candidate = child / "todo.json"
        if candidate.is_file():
            candidates.append((child.name, candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]

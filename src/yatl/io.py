"""Filesystem adapters shared by command-line entry points."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_markdown_directory(path: Path) -> dict[str, str]:
    return {source.name: source.read_text() for source in sorted(path.glob("*.md"))}


def write_text_atomic(
    path: Path,
    content: str,
    *,
    create_parents: bool = True,
    replace: bool = True,
) -> None:
    if not replace and path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {path}")
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def create_text_atomic(path: Path, content: str, *, create_parents: bool = True) -> None:
    """Atomically create a complete file without replacing an existing path."""
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def emit_text(content: str, output: Path | None, replace: bool) -> None:
    if output is None:
        print(content, end="")
        return
    write_text_atomic(output.resolve(), content, replace=replace)

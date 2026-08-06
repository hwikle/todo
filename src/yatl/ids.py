"""Canonical UUIDv4 task-identity generation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import uuid

class TaskIdGenerationError(Exception):
    """A unique canonical task ID could not be generated."""


def is_canonical_task_id(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == value


class TaskIdSource:
    def __init__(self, generator: Callable[[], str] | None = None) -> None:
        self.generator = generator or (lambda: str(uuid.uuid4()))
        self.seen: set[str] = set()

    def next(self, excluded: Iterable[str] = ()) -> str:
        occupied = set(excluded)
        for _ in range(1000):
            candidate = self.generator()
            if not is_canonical_task_id(candidate):
                raise TaskIdGenerationError(
                    f"task ID generator produced non-canonical UUIDv4 {candidate!r}"
                )
            if candidate not in occupied and candidate not in self.seen:
                self.seen.add(candidate)
                return candidate
        raise TaskIdGenerationError("could not generate a unique UUIDv4 task ID")

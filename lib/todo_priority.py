"""Canonical priority ordering shared across domain operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from todo_model import Priority


class PriorityConfigurationError(ValueError):
    """The canonical priority schema does not define a usable ordering."""


@dataclass(frozen=True)
class PriorityPolicy:
    order: tuple[Priority, ...]

    @property
    def ranks(self) -> dict[Priority, int]:
        return {name: rank for rank, name in enumerate(self.order)}

    def rank(self, priority: Priority) -> int:
        return self.ranks[priority]


def priority_policy_from_schema(schema: dict[str, Any]) -> PriorityPolicy:
    values = schema.get("enum")
    ordered = schema.get("x-order")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise PriorityConfigurationError("priority.schema.json: enum must contain strings")
    if not isinstance(ordered, list) or not all(isinstance(item, str) for item in ordered):
        raise PriorityConfigurationError("priority.schema.json: x-order must contain strings")
    if len(ordered) != len(set(ordered)) or set(ordered) != set(values):
        raise PriorityConfigurationError(
            "priority.schema.json: x-order must contain each enum value exactly once"
        )
    return PriorityPolicy(tuple(ordered))

"""Shared diagnostic policy for Daily TODO command-line adapters."""

from __future__ import annotations

import sys
from typing import Iterable

from yatl.validation import Issue


def print_issues(issues: Iterable[Issue], strict: bool, prefix: str = "") -> bool:
    failed = False
    for issue in issues:
        effective = "error" if strict and issue.severity == "warning" else issue.severity
        suffix = " (strict)" if effective != issue.severity else ""
        print(
            f"{prefix}{issue.location}: {effective}{suffix}: {issue.message}",
            file=sys.stderr,
        )
        failed = failed or effective == "error"
    return failed

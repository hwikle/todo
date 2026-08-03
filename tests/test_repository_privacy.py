#!/usr/bin/env python3
"""Guard version-controlled project content against local personal data."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "macOS user path": re.compile(b"/" + rb"Users/[^/\s]+/"),
    "Linux user path": re.compile(b"/" + rb"home/[^/\s]+/"),
    "email address": re.compile(
        rb"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
}


def tracked_paths() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / Path(item) for item in output.decode().split("\0") if item]


def reachable_blobs() -> list[str]:
    objects = subprocess.check_output(
        ["git", "rev-list", "--objects", "--all"], cwd=ROOT, text=True
    )
    object_ids = [line.split(" ", 1)[0] for line in objects.splitlines()]
    blobs: list[str] = []
    for object_id in object_ids:
        object_type = subprocess.check_output(
            ["git", "cat-file", "-t", object_id], cwd=ROOT, text=True
        ).strip()
        if object_type == "blob":
            blobs.append(object_id)
    return blobs


def find_forbidden(data: bytes) -> list[str]:
    return [label for label, pattern in FORBIDDEN.items() if pattern.search(data)]


def main() -> int:
    failures: list[str] = []
    paths = tracked_paths()
    for path in paths:
        data = path.read_bytes()
        for label in find_forbidden(data):
            failures.append(f"{path.relative_to(ROOT)}: contains {label}")

    blobs = reachable_blobs()
    for object_id in blobs:
        data = subprocess.check_output(
            ["git", "cat-file", "blob", object_id], cwd=ROOT
        )
        for label in find_forbidden(data):
            failures.append(f"historical blob {object_id}: contains {label}")

    if failures:
        print("Repository privacy validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        "Repository privacy validation passed "
        f"({len(paths)} files, {len(blobs)} historical blobs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

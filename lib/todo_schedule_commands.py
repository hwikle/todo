"""Install, inspect, and uninstall the optional macOS launchd job."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from todo_io import write_text_atomic


ROOT = Path(__file__).resolve().parent.parent
LABEL = "local.daily-todo"


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser("schedule", help="manage the optional macOS schedule")
    commands = group.add_subparsers(dest="schedule_command", required=True)
    install = commands.add_parser("install")
    install.add_argument("--replace", action="store_true")
    commands.add_parser("status")
    commands.add_parser("uninstall")


def _destination() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def run(args: argparse.Namespace) -> int:
    destination = _destination()
    service = f"{_domain()}/{LABEL}"
    try:
        if args.schedule_command == "status":
            if not destination.exists():
                print("not installed")
                return 1
            result = subprocess.run(["launchctl", "print", service], capture_output=True, text=True)
            print("installed and loaded" if result.returncode == 0 else "installed but not loaded")
            return 0
        if args.schedule_command == "uninstall":
            if not destination.exists():
                print("not installed")
                return 0
            subprocess.run(["launchctl", "bootout", service], capture_output=True, check=False)
            destination.unlink()
            print(f"removed {destination}")
            return 0
        template = (ROOT / "launchd" / f"{LABEL}.plist.in").read_text()
        content = template.replace("__TODO_ROOT__", str(ROOT))
        write_text_atomic(destination, content, replace=args.replace)
        check = subprocess.run(["plutil", "-lint", str(destination)], capture_output=True, text=True)
        if check.returncode != 0:
            destination.unlink(missing_ok=True)
            raise OSError(check.stderr.strip() or "invalid launchd property list")
        subprocess.run(["launchctl", "bootout", service], capture_output=True, check=False)
        loaded = subprocess.run(["launchctl", "bootstrap", _domain(), str(destination)], capture_output=True, text=True)
        if loaded.returncode != 0:
            raise OSError(loaded.stderr.strip() or "launchctl bootstrap failed")
        print(f"installed and loaded {destination}")
        return 0
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

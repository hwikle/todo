"""Install, inspect, and uninstall the optional macOS launchd job."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from todo_io import write_text_atomic
from todo_schedule import ScheduleConfigurationError, from_document, load, render_launchd


ROOT = Path(__file__).resolve().parent.parent
LABEL = "local.daily-todo"
DEFAULT_CONFIG = ROOT / "config" / "schedule.json"


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    group = subparsers.add_parser(
        "schedule", help="manage automatic daily list creation",
        description="Install, inspect, or remove the optional macOS launchd schedule.",
    )
    commands = group.add_subparsers(
        dest="schedule_command", required=True, metavar="ACTION", help="schedule operation to perform"
    )
    configure_command = commands.add_parser(
        "configure", help="configure scheduling",
        description="Write an explicit local configuration for launchd list generation.",
    )
    configure_command.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, metavar="FILE",
        help="write configuration to FILE (default: config/schedule.json)",
    )
    configure_command.add_argument(
        "--repository-dir", type=Path, default=ROOT, metavar="DIR",
        help="absolute repository directory containing bin/todo (default: this repository)",
    )
    configure_command.add_argument(
        "--lists-dir", type=Path, required=True, metavar="DIR",
        help="absolute directory where dated TODO-list directories are stored",
    )
    configure_command.add_argument(
        "--generation-time", required=True, metavar="HH:MM",
        help="local 24-hour time when launchd creates and renders the list",
    )
    configure_command.add_argument("--replace", action="store_true", help="replace an existing configuration file")
    show = commands.add_parser(
        "show", help="show scheduling configuration",
        description="Validate and print the local scheduling configuration.",
    )
    show.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, metavar="FILE",
        help="configuration to read (default: config/schedule.json)",
    )
    install = commands.add_parser(
        "install", help="install and load the schedule",
        description="Install and load the macOS launchd job for automatic daily list creation.",
    )
    install.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, metavar="FILE",
        help="validated configuration to install (default: config/schedule.json)",
    )
    install.add_argument("--replace", action="store_true", help="replace an existing launchd property list")
    commands.add_parser(
        "status", help="show schedule status",
        description="Report whether the macOS schedule is installed and loaded.",
    )
    commands.add_parser(
        "uninstall", help="remove the schedule",
        description="Unload and remove the macOS launchd job.",
    )


def _destination() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def run(args: argparse.Namespace) -> int:
    destination = _destination()
    service = f"{_domain()}/{LABEL}"
    try:
        if args.schedule_command == "configure":
            config = from_document({
                "repository_directory": str(args.repository_dir),
                "lists_directory": str(args.lists_dir),
                "generation_time": args.generation_time,
            })
            write_text_atomic(args.config.resolve(), config.to_json(), replace=args.replace)
            print(f"wrote {args.config.resolve()}")
            return 0
        if args.schedule_command == "show":
            print(load(args.config.resolve()).to_json(), end="")
            return 0
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
        config = load(args.config.resolve())
        content = render_launchd(config, LABEL)
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
    except (OSError, ScheduleConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

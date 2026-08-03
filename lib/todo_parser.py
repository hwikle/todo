"""User-facing argument parser behavior shared by every TODO command."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn


class TodoArgumentParser(argparse.ArgumentParser):
    """Show actionable command help whenever command-line parsing fails."""

    def error(self, message: str) -> NoReturn:
        self.print_help(sys.stderr)
        self.exit(2, f"\n{self.prog}: {message}\n")

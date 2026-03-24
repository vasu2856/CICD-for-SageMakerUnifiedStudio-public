"""Checker protocol and base types for dry-run validation phases."""

from __future__ import annotations

from typing import List, Protocol

from smus_cicd.commands.dry_run.models import DryRunContext, Finding


class Checker(Protocol):
    """Protocol that all dry-run phase checkers must implement."""

    def check(self, context: DryRunContext) -> List[Finding]: ...  # noqa: E704

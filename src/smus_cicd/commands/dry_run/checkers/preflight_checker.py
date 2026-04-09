"""Preflight checker (Phase 2b).

Validates that shared preconditions are met before running individual
phase checkers.  Runs after ManifestChecker and BundleChecker have
populated the DryRunContext.  If any ERROR findings are produced here,
the engine should fail-fast and skip all subsequent phases.

Checks:
- target_config is populated (manifest was parsed and target resolved)
- config dict is populated (domain/region configuration available)
"""

from __future__ import annotations

from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity


class PreflightChecker:
    """Validates shared preconditions required by all downstream checkers."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="Preflight failed: target configuration not loaded from manifest",
                )
            )

        if context.config is None:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="Preflight failed: domain/region configuration not resolved",
                )
            )

        if not findings:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="Preflight checks passed: target and config available",
                )
            )

        return findings

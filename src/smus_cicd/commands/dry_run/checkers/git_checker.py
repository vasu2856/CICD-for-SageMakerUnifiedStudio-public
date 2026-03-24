"""Git deployment simulation checker (Phase 8).

Simulates git deployment for each git item in
``deployment_configuration``. Reports target connection, repository,
and file count per item.

- Uses ``context.bundle_files`` to count files matching each git item
  (files under ``repositories/{name}/``).
- Git items have: name, connectionName, targetDirectory.

Requirements: 5.3
"""

from __future__ import annotations

import logging
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class GitChecker:
    """Simulates git deployment and reports planned actions per item."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping git deployment check: " "manifest/target not loaded"
                    ),
                )
            )
            return findings

        dep_cfg = getattr(context.target_config, "deployment_configuration", None)
        git_items = getattr(dep_cfg, "git", None) if dep_cfg else None

        if not git_items:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No git items configured; skipping.",
                    service="git",
                )
            )
            return findings

        for item in git_items:
            name = getattr(item, "name", str(item))
            connection = getattr(item, "connectionName", None) or ""
            target_dir = getattr(item, "targetDirectory", None) or ""

            # Count matching files in the bundle under repositories/{name}/
            repo_prefix = f"repositories/{name}/"
            matching_files = [
                f for f in context.bundle_files if f.startswith(repo_prefix)
            ]
            file_count = len(matching_files)

            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=(
                        f"Git item '{name}': "
                        f"connection '{connection}', "
                        f"repository '{target_dir}', "
                        f"{file_count} file(s) to deploy"
                    ),
                    resource=name,
                    service="git",
                    details={
                        "connection": connection,
                        "repository": target_dir,
                        "file_count": file_count,
                    },
                )
            )

        return findings

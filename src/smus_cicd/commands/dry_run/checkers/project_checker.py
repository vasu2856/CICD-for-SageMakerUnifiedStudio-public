"""Project initialization simulation checker (Phase 5).

Simulates project initialization: reports whether the target project exists
or would be created.

- Uses ``get_project_by_name()`` from the datazone helper.
- Returns OK if project exists.
- Returns OK if project not found but ``create=True``.
- Returns ERROR if project not found and ``create=False``.

Requirements: 5.1, 6.2
"""

from __future__ import annotations

import logging
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class ProjectChecker:
    """Simulates project initialization and reports project status."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None or context.config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping project initialization check: "
                        "manifest/target not loaded"
                    ),
                )
            )
            return findings

        config = context.config
        region = config.get("region", "us-east-1")

        # Resolve domain_id — may come from config directly, or via
        # domain name/tags lookup when the manifest uses tags.
        domain_id = config.get("domain_id")
        if not domain_id:
            try:
                from smus_cicd.helpers.utils import _resolve_domain_id

                domain_id = _resolve_domain_id(config, region)
            except Exception:
                pass

        # Extract project name and create flag from target_config
        project_cfg = getattr(context.target_config, "project", None)
        if project_cfg is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "No project configuration in target; "
                        "skipping project initialization check"
                    ),
                    service="datazone",
                )
            )
            return findings

        project_name = getattr(project_cfg, "name", None)
        create_flag = getattr(project_cfg, "create", False)

        if not project_name or not domain_id:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "No project_name or domain_id available; "
                        "skipping project initialization check"
                    ),
                    service="datazone",
                )
            )
            return findings

        try:
            from smus_cicd.helpers.datazone import get_project_by_name

            project = get_project_by_name(project_name, domain_id, region)

            if project is not None:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Project '{project_name}' exists in domain "
                            f"'{domain_id}'. No creation needed."
                        ),
                        resource=project_name,
                        service="datazone",
                    )
                )
            elif create_flag:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Project '{project_name}' not found in domain "
                            f"'{domain_id}', but create=True — "
                            f"project would be created during deployment."
                        ),
                        resource=project_name,
                        service="datazone",
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Project '{project_name}' not found in domain "
                            f"'{domain_id}' and create=False. "
                            f"Deployment would fail."
                        ),
                        resource=project_name,
                        service="datazone",
                    )
                )
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(
                        f"Failed to check project '{project_name}' "
                        f"in domain '{domain_id}': {exc}"
                    ),
                    resource=project_name,
                    service="datazone",
                )
            )

        return findings

"""QuickSight deployment simulation checker (Phase 6).

Simulates QuickSight deployment if configured in the manifest.
Reports which dashboards would be exported and imported.

- Reuses ``helpers/quicksight.py`` for read-only checks
  (``lookup_dashboard_by_name``).
- If no QuickSight config in target, returns OK with
  "no QuickSight configured" message.

Requirements: 5.5
"""

from __future__ import annotations

import logging
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class QuickSightChecker:
    """Simulates QuickSight dashboard deployment and reports planned actions."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None or context.config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping QuickSight check: " "manifest/target not loaded"
                    ),
                )
            )
            return findings

        # Collect dashboards from manifest content
        dashboards = []
        manifest = context.manifest
        if manifest is not None:
            content = getattr(manifest, "content", None)
            if content is not None:
                qs_list = getattr(content, "quicksight", None)
                if qs_list:
                    dashboards.extend(qs_list)

        # Also check stage-level quicksight config
        stage_qs = getattr(context.target_config, "quicksight", None)
        if stage_qs:
            dashboards.extend(stage_qs)

        if not dashboards:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No QuickSight dashboards configured; skipping.",
                    service="quicksight",
                )
            )
            return findings

        config = context.config
        region = getattr(
            getattr(context.target_config, "domain", None), "region", None
        ) or config.get("region", "us-east-1")
        aws_account_id = config.get("aws", {}).get("account_id")

        if not aws_account_id:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "AWS account ID not available; "
                        "cannot verify QuickSight dashboards."
                    ),
                    service="quicksight",
                )
            )
            # Still report what would be deployed
            for dashboard_cfg in dashboards:
                name = getattr(dashboard_cfg, "name", str(dashboard_cfg))
                asset_bundle = getattr(dashboard_cfg, "assetBundle", "export")
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Dashboard '{name}' would be imported "
                            f"(source: {asset_bundle})."
                        ),
                        resource=name,
                        service="quicksight",
                    )
                )
            return findings

        for dashboard_cfg in dashboards:
            name = getattr(dashboard_cfg, "name", str(dashboard_cfg))
            asset_bundle = getattr(dashboard_cfg, "assetBundle", "export")

            if asset_bundle == "export":
                # For export mode, verify the source dashboard exists
                try:
                    from smus_cicd.helpers.quicksight import (
                        lookup_dashboard_by_name,
                    )

                    dashboard_id = lookup_dashboard_by_name(
                        name, aws_account_id, region
                    )
                    findings.append(
                        Finding(
                            severity=Severity.OK,
                            message=(
                                f"Dashboard '{name}' found (ID: {dashboard_id}). "
                                f"Would be exported and imported."
                            ),
                            resource=name,
                            service="quicksight",
                        )
                    )
                except Exception as exc:
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=(
                                f"Dashboard '{name}' not found or "
                                f"inaccessible for export: {exc}"
                            ),
                            resource=name,
                            service="quicksight",
                        )
                    )
            else:
                # For local asset bundle, check if file exists in bundle
                if context.bundle_files and asset_bundle in context.bundle_files:
                    findings.append(
                        Finding(
                            severity=Severity.OK,
                            message=(
                                f"Dashboard '{name}' would be imported "
                                f"from bundle file '{asset_bundle}'."
                            ),
                            resource=name,
                            service="quicksight",
                        )
                    )
                elif context.bundle_files:
                    # Also check quicksight/ prefixed path
                    qs_path = f"quicksight/{asset_bundle}"
                    if qs_path in context.bundle_files:
                        findings.append(
                            Finding(
                                severity=Severity.OK,
                                message=(
                                    f"Dashboard '{name}' would be imported "
                                    f"from bundle file '{qs_path}'."
                                ),
                                resource=name,
                                service="quicksight",
                            )
                        )
                    else:
                        findings.append(
                            Finding(
                                severity=Severity.WARNING,
                                message=(
                                    f"Dashboard '{name}' asset bundle "
                                    f"'{asset_bundle}' not found in bundle."
                                ),
                                resource=name,
                                service="quicksight",
                            )
                        )
                else:
                    findings.append(
                        Finding(
                            severity=Severity.OK,
                            message=(
                                f"Dashboard '{name}' would be imported "
                                f"from local file '{asset_bundle}'."
                            ),
                            resource=name,
                            service="quicksight",
                        )
                    )

        return findings

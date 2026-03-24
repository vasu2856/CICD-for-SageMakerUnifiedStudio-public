"""Storage deployment simulation checker (Phase 7).

Simulates storage deployment for each storage item in
``deployment_configuration``. Reports target S3 bucket, prefix,
and file count per item.

- Uses ``context.bundle_files`` to count files matching each storage item.
- Storage items have: name, connectionName (derives bucket),
  targetDirectory (prefix).

Requirements: 5.2
"""

from __future__ import annotations

import logging
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class StorageChecker:
    """Simulates storage deployment and reports planned actions per item."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping storage deployment check: "
                        "manifest/target not loaded"
                    ),
                )
            )
            return findings

        dep_cfg = getattr(context.target_config, "deployment_configuration", None)
        storage_items = getattr(dep_cfg, "storage", None) if dep_cfg else None

        if not storage_items:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No storage items configured; skipping.",
                    service="s3",
                )
            )
            return findings

        config = context.config or {}
        region = config.get("region", "us-east-1")

        # Resolve real bucket names via DataZone project connections
        project_connections = self._get_project_connections(context, region)

        for item in storage_items:
            name = getattr(item, "name", str(item))
            connection = getattr(item, "connectionName", None) or ""
            target_dir = getattr(item, "targetDirectory", None) or ""

            # Resolve bucket name from DataZone connection
            bucket = None
            if connection and project_connections:
                conn_info = project_connections.get(connection)
                if conn_info:
                    s3_uri = conn_info.get("s3Uri", "")
                    if s3_uri:
                        bucket = s3_uri.replace("s3://", "").rstrip("/").split("/")[0]

            if not bucket:
                # Fallback: show connection name as-is
                bucket = f"<unresolved:{connection}>" if connection else "<unknown>"

            # Count matching files in the bundle
            matching_files = [
                f for f in context.bundle_files if f.startswith(f"{name}/") or f == name
            ]
            file_count = len(matching_files)

            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=(
                        f"Storage item '{name}': "
                        f"target bucket '{bucket}', "
                        f"prefix '{target_dir}', "
                        f"{file_count} file(s) to deploy"
                    ),
                    resource=name,
                    service="s3",
                    details={
                        "bucket": bucket,
                        "prefix": target_dir,
                        "file_count": file_count,
                    },
                )
            )

        return findings

    @staticmethod
    def _get_project_connections(context: DryRunContext, region: str) -> dict | None:
        """Attempt to fetch project connections from DataZone.

        Returns the connections dict or ``None`` if resolution fails.
        """
        config = context.config or {}
        project_name = config.get("project_name")
        if not project_name:
            project_cfg = getattr(context.target_config, "project", None)
            project_name = getattr(project_cfg, "name", None) if project_cfg else None

        if not project_name:
            return None

        try:
            from smus_cicd.helpers.utils import get_datazone_project_info

            info = get_datazone_project_info(project_name, config)
            if "error" in info:
                return None
            return info.get("connections")
        except Exception:
            return None

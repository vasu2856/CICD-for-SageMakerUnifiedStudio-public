"""Manifest and target stage validation checker (Phase 1)."""

from __future__ import annotations

import logging
import os
import re
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class ManifestChecker:
    """Loads the manifest, resolves the target stage, and validates env var references."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        # --- Step 1: Load and parse the manifest ---
        manifest = self._load_manifest(context, findings)
        if manifest is None:
            return findings

        context.manifest = manifest

        # --- Step 2: Resolve the target stage ---
        target_config = self._resolve_target_stage(context, findings)
        if target_config is None:
            return findings

        # --- Step 3: Build domain config ---
        try:
            from smus_cicd.helpers.utils import build_domain_config

            context.config = build_domain_config(target_config)
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="Domain configuration built successfully",
                )
            )
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to build domain configuration: {exc}",
                )
            )
            return findings

        # --- Step 4: Validate environment variable references ---
        self._validate_env_vars(context, findings)

        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_manifest(
        self, context: DryRunContext, findings: List[Finding]
    ) -> object | None:
        """Attempt to load the manifest; append findings and return the manifest or None."""
        from smus_cicd.application.application_manifest import ApplicationManifest

        try:
            manifest = ApplicationManifest.from_file(context.manifest_file)
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=f"Manifest loaded successfully from {context.manifest_file}",
                    resource=context.manifest_file,
                )
            )
            return manifest
        except FileNotFoundError:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Manifest file not found: {context.manifest_file}",
                    resource=context.manifest_file,
                )
            )
            return None
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to parse manifest '{context.manifest_file}': {exc}",
                    resource=context.manifest_file,
                )
            )
            return None

    def _resolve_target_stage(
        self, context: DryRunContext, findings: List[Finding]
    ) -> object | None:
        """Resolve the target stage from the manifest; append findings and return config or None."""
        manifest = context.manifest

        if manifest is None:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="Cannot resolve target stage: manifest not loaded",
                )
            )
            return None

        # Use the same logic as deploy.py _get_target_name
        if not context.stage_name:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="No target stage specified. Use --targets to specify a target.",
                )
            )
            return None

        target_list = [t.strip() for t in context.stage_name.split(",")]
        stage_name = target_list[0]

        target_config = manifest.get_stage(stage_name)
        if not target_config:
            available = ", ".join(manifest.stages.keys())
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(
                        f"Target stage '{stage_name}' not found in manifest. "
                        f"Available stages: {available}"
                    ),
                    details={"available_stages": list(manifest.stages.keys())},
                )
            )
            return None

        # Populate default deployment_configuration if needed (mirrors deploy.py logic)
        if (
            not target_config.deployment_configuration
            and manifest.content
            and manifest.content.storage
        ):
            from smus_cicd.application.application_manifest import (
                DeploymentConfiguration,
                StorageConfig,
            )

            storage_configs = [
                StorageConfig(
                    name=item.name,
                    connectionName="default.s3_shared",
                    targetDirectory=f"bundle/{item.name}",
                )
                for item in manifest.content.storage
            ]
            target_config.deployment_configuration = DeploymentConfiguration(
                storage=storage_configs
            )

        context.stage_name = stage_name
        context.target_config = target_config

        findings.append(
            Finding(
                severity=Severity.OK,
                message=f"Target stage '{stage_name}' resolved successfully",
            )
        )
        return target_config

    def _validate_env_vars(
        self, context: DryRunContext, findings: List[Finding]
    ) -> None:
        """Scan the raw manifest file for env var references and warn about unresolved ones."""
        try:
            with open(context.manifest_file, "r") as fh:
                raw_content = fh.read()
        except Exception:
            # If we can't re-read the file, skip env var validation
            return

        # Collect all ${VAR_NAME} and $VAR_NAME references
        braced = set(re.findall(r"\$\{([^}]+)\}", raw_content))
        bare = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", raw_content))
        all_refs = braced | bare

        if not all_refs:
            return

        # Build the set of known variables
        env_vars: dict = {}
        if context.target_config and context.target_config.environment_variables:
            env_vars = context.target_config.environment_variables

        unresolved = [
            name
            for name in sorted(all_refs)
            if name not in env_vars and name not in os.environ
        ]

        if unresolved:
            for var_name in unresolved:
                findings.append(
                    Finding(
                        severity=Severity.WARNING,
                        message=(
                            f"Unresolved environment variable reference: ${var_name}"
                        ),
                        details={"variable": var_name},
                    )
                )
        else:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="All environment variable references are resolved",
                )
            )

"""Bundle artifact exploration checker (Phase 2).

Opens the bundle ZIP, enumerates files, cross-references storage and git items
from deployment_configuration, and validates catalog_export.json if present.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import json
import logging
import zipfile
from typing import List

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity
from smus_cicd.helpers.catalog_import import CREATION_ORDER, REQUIRED_TOP_LEVEL_KEYS

logger = logging.getLogger(__name__)

CATALOG_EXPORT_PATH = "catalog/catalog_export.json"


class BundleChecker:
    """Opens the bundle ZIP, enumerates files, and validates bundle contents."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        # --- Step 1: Resolve bundle path ---
        bundle_path = self._resolve_bundle_path(context, findings)
        if bundle_path is None:
            return findings

        context.bundle_path = bundle_path

        # --- Step 2: Open ZIP and enumerate files ---
        if not self._enumerate_bundle_files(context, findings):
            return findings

        # --- Step 3: Cross-reference storage items ---
        self._check_storage_items(context, findings)

        # --- Step 4: Cross-reference git items ---
        self._check_git_items(context, findings)

        # --- Step 5: Validate catalog export if present ---
        self._check_catalog_export(context, findings)

        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_bundle_path(
        self, context: DryRunContext, findings: List[Finding]
    ) -> str | None:
        """Resolve the bundle path, falling back to ./artifacts directory.

        When no bundle is found and the deployment configuration does not
        require one (no storage items with a connectionName, no git items),
        the checker reports a WARNING instead of an ERROR so that
        bundle-less workflows (e.g. ML Training) are not blocked.
        """
        if context.bundle_path:
            return context.bundle_path

        # Attempt to locate the bundle in ./artifacts using the same logic as deploy.py
        if context.manifest is None:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="Cannot locate bundle: manifest not loaded",
                )
            )
            return None

        try:
            from smus_cicd.helpers.bundle_storage import find_bundle_file

            bundle_path = find_bundle_file(
                "./artifacts",
                context.manifest.application_name,
                context.config.get("region") if context.config else None,
            )
            if bundle_path:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=f"Bundle resolved from ./artifacts: {bundle_path}",
                        resource=bundle_path,
                    )
                )
                return bundle_path
            else:
                # Check whether the deployment actually requires a bundle.
                # Uses the same logic as deploy_command().
                from smus_cicd.helpers.bundle_storage import manifest_requires_bundle

                needs_bundle = manifest_requires_bundle(context.manifest)
                if needs_bundle:
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=(
                                "No bundle archive found. Provide "
                                "--bundle-archive-path or place a ZIP "
                                "in ./artifacts"
                            ),
                        )
                    )
                return None
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to locate bundle in ./artifacts: {exc}",
                )
            )
            return None

    def _enumerate_bundle_files(
        self, context: DryRunContext, findings: List[Finding]
    ) -> bool:
        """Open the ZIP and populate context.bundle_files. Returns True on success."""
        if not context.bundle_path:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="No bundle path available for enumeration",
                )
            )
            return False
        try:
            with zipfile.ZipFile(context.bundle_path, "r") as zf:
                context.bundle_files = set(zf.namelist())
            file_count = len(context.bundle_files)
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=f"Bundle contains {file_count} file(s)",
                    resource=context.bundle_path,
                    details={"file_count": file_count},
                )
            )
            return True
        except zipfile.BadZipFile:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Invalid ZIP archive: {context.bundle_path}",
                    resource=context.bundle_path,
                )
            )
            return False
        except FileNotFoundError:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Bundle file not found: {context.bundle_path}",
                    resource=context.bundle_path,
                )
            )
            return False
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to open bundle: {exc}",
                    resource=context.bundle_path,
                )
            )
            return False

    def _check_storage_items(
        self, context: DryRunContext, findings: List[Finding]
    ) -> None:
        """Cross-reference storage items from deployment_configuration against bundle."""
        if (
            not context.target_config
            or not context.target_config.deployment_configuration
        ):
            return

        storage_configs = context.target_config.deployment_configuration.storage or []
        if not storage_configs:
            return

        # Build a map of content items to check for local-only items
        content_map = {}
        if (
            context.manifest
            and context.manifest.content
            and context.manifest.content.storage
        ):
            for item in context.manifest.content.storage:
                content_map[item.name] = item

        for storage_config in storage_configs:
            name = storage_config.name
            content_item = content_map.get(name)

            # If the content item has no connectionName, it's a local-only item
            # and doesn't need to be in the bundle
            if content_item and not content_item.connectionName:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Storage item '{name}' uses local filesystem "
                            "(not expected in bundle)"
                        ),
                        resource=name,
                    )
                )
                continue

            # Storage items are stored under their name in the bundle
            matching_files = [
                f for f in context.bundle_files if f.startswith(f"{name}/") or f == name
            ]

            if matching_files:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Storage item '{name}' found in bundle "
                            f"({len(matching_files)} file(s))"
                        ),
                        resource=name,
                        details={"file_count": len(matching_files)},
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Storage item '{name}' not found in bundle. "
                            f"Expected files under '{name}/' in the archive"
                        ),
                        resource=name,
                    )
                )

    def _check_git_items(self, context: DryRunContext, findings: List[Finding]) -> None:
        """Cross-reference git items from deployment_configuration against bundle."""
        if (
            not context.target_config
            or not context.target_config.deployment_configuration
        ):
            return

        git_configs = context.target_config.deployment_configuration.git or []
        if not git_configs:
            return

        for git_config in git_configs:
            name = git_config.name

            # Git items are stored under repositories/{name}/ in the bundle
            repo_prefix = f"repositories/{name}/"
            matching_files = [
                f for f in context.bundle_files if f.startswith(repo_prefix)
            ]

            if matching_files:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Git item '{name}' found in bundle "
                            f"({len(matching_files)} file(s))"
                        ),
                        resource=name,
                        details={"file_count": len(matching_files)},
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Git item '{name}' not found in bundle. "
                            f"Expected files under 'repositories/{name}/' "
                            "in the archive"
                        ),
                        resource=name,
                    )
                )

    def _check_catalog_export(
        self, context: DryRunContext, findings: List[Finding]
    ) -> None:
        """Validate catalog/catalog_export.json if present in the bundle."""
        if CATALOG_EXPORT_PATH not in context.bundle_files:
            return

        if not context.bundle_path:
            return

        try:
            with zipfile.ZipFile(context.bundle_path, "r") as zf:
                raw = zf.read(CATALOG_EXPORT_PATH)
            catalog_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(f"Invalid JSON in {CATALOG_EXPORT_PATH}: {exc}"),
                    resource=CATALOG_EXPORT_PATH,
                )
            )
            return
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to read {CATALOG_EXPORT_PATH}: {exc}",
                    resource=CATALOG_EXPORT_PATH,
                )
            )
            return

        # Validate top-level structure
        if not isinstance(catalog_data, dict):
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(
                        f"{CATALOG_EXPORT_PATH} must be a JSON object, "
                        f"got {type(catalog_data).__name__}"
                    ),
                    resource=CATALOG_EXPORT_PATH,
                )
            )
            return

        missing_keys = sorted(REQUIRED_TOP_LEVEL_KEYS - set(catalog_data.keys()))

        if missing_keys:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(
                        f"{CATALOG_EXPORT_PATH} missing required key(s): "
                        f"{', '.join(missing_keys)}"
                    ),
                    resource=CATALOG_EXPORT_PATH,
                    details={"missing_keys": missing_keys},
                )
            )
            return

        # Populate context for downstream checkers
        context.catalog_data = catalog_data

        # Count all catalog resources across resource-type keys
        resource_count = sum(len(catalog_data.get(k, [])) for k in CREATION_ORDER)
        findings.append(
            Finding(
                severity=Severity.OK,
                message=(
                    f"Catalog export validated: {resource_count} resource(s) found"
                ),
                resource=CATALOG_EXPORT_PATH,
                details={"resource_count": resource_count},
            )
        )

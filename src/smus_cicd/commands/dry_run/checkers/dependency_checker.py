"""Pre-existing resource dependency validation checker (Phase 9b).

Validates that pre-existing AWS resources and DataZone types referenced by
catalog export data exist in the target environment. Runs after CatalogChecker
and uses ``context.catalog_data`` populated by BundleChecker.

Checks:
- Glue Data Catalog resource validation (tables, views, databases)
- Data source validation
- Custom form type validation
- Custom asset type validation
- Form type revision validation
- Managed resource skipping (``amazon.datazone.`` prefix)
- Caching for all API calls

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9,
              13.10, 13.11, 13.12, 13.13
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity
from smus_cicd.helpers.catalog_import import (
    DATA_SOURCE_REF_FORM_TYPE,
    DATA_SOURCE_VALID_STATUSES,
    GLUE_TABLE_FORM_TYPE,
    _is_managed_resource,
    extract_database_name_from_forms,
    get_form_type_ref,
    parse_form_content,
)

logger = logging.getLogger(__name__)


class DependencyChecker:
    """Validates pre-existing AWS resources and DataZone types."""

    def __init__(self) -> None:
        # Caches keyed by resource identifiers
        self._db_cache: Dict[str, bool] = {}
        self._table_cache: Dict[Tuple[str, str], bool] = {}
        self._partition_cache: Dict[Tuple[str, str], bool] = {}
        self._data_source_cache: Dict[Tuple[str, str], bool] = {}
        self._form_type_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._asset_type_cache: Dict[str, bool] = {}

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.catalog_data is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=("Skipping dependency checks: no catalog data available"),
                    service="datazone",
                )
            )
            return findings

        if context.target_config is None or context.config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping dependency checks: " "manifest/target not loaded"
                    ),
                )
            )
            return findings

        config = context.config
        region = config.get("region", "us-east-1")
        domain_id = config.get("domain_id", "")
        project_id = config.get("project_id", "")

        resources = context.catalog_data.get("resources", [])
        # Support both the real catalog format (keyed by resource type)
        # and the legacy flat format (single "resources" list)
        if not resources:
            # Real format: collect assets/assetTypes from their own keys
            assets = [
                r for r in context.catalog_data.get("assets", []) if isinstance(r, dict)
            ]
            asset_types = [
                r
                for r in context.catalog_data.get("assetTypes", [])
                if isinstance(r, dict)
            ]
            all_resources = assets + asset_types
        else:
            all_resources = resources
            assets = None  # sentinel — will be derived below
            asset_types = None

        if not all_resources:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No catalog resources to check dependencies for.",
                    service="datazone",
                )
            )
            return findings

        # Separate resources by type (only needed for legacy flat format)
        if assets is None:
            assets = [
                r
                for r in resources
                if isinstance(r, dict) and r.get("type") == "assets"
            ]
        if asset_types is None:
            asset_types = [
                r
                for r in resources
                if isinstance(r, dict) and r.get("type") == "assetTypes"
            ]

        # 1. Glue Data Catalog resource validation (Req 13.1, 13.2, 13.3, 13.13)
        self._check_glue_resources(assets, region, findings)

        # 2. Data source validation (Req 13.4, 13.5)
        self._check_data_sources(assets, domain_id, project_id, region, findings)

        # 3. Custom form type validation (Req 13.6, 13.7, 13.12)
        self._check_custom_form_types(asset_types, domain_id, region, findings)

        # 4. Custom asset type validation (Req 13.8, 13.9, 13.12)
        self._check_custom_asset_types(assets, domain_id, region, findings)

        # 5. Form type revision validation (Req 13.10, 13.11)
        self._check_form_type_revisions(assets, domain_id, region, findings)

        return findings

    # ------------------------------------------------------------------
    # 1. Glue Data Catalog resource validation
    # ------------------------------------------------------------------

    def _check_glue_resources(
        self,
        assets: List[Dict[str, Any]],
        region: str,
        findings: List[Finding],
    ) -> None:
        """Validate Glue tables, views, and databases referenced by assets."""
        try:
            glue = boto3.client("glue", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create Glue client: {exc}",
                    service="glue",
                )
            )
            return

        for asset in assets:
            asset_name = asset.get("name", "unknown")
            forms_input = asset.get("formsInput", [])
            if not isinstance(forms_input, list):
                continue

            for form in forms_input:
                if not isinstance(form, dict):
                    continue
                type_id = get_form_type_ref(form)
                if GLUE_TABLE_FORM_TYPE not in type_id:
                    continue

                content = parse_form_content(form.get("content"))
                if content is None:
                    continue

                db_name = content.get("databaseName")
                table_name = content.get("tableName")
                table_type = content.get("tableType", "")

                if not db_name or not table_name:
                    continue

                # Check database existence (cached)
                self._check_glue_database(glue, db_name, asset_name, findings)

                # Check table/view existence (cached)
                self._check_glue_table(
                    glue, db_name, table_name, table_type, asset_name, findings
                )

    def _check_glue_database(
        self,
        glue: Any,
        db_name: str,
        asset_name: str,
        findings: List[Finding],
    ) -> None:
        """Verify Glue database existence with caching."""
        if db_name in self._db_cache:
            if not self._db_cache[db_name]:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Glue database '{db_name}' not found "
                            f"(referenced by asset '{asset_name}')"
                        ),
                        resource=db_name,
                        service="glue",
                        details={
                            "database_name": db_name,
                            "resource_type": "database",
                            "asset": asset_name,
                        },
                    )
                )
            return

        try:
            glue.get_database(Name=db_name)
            self._db_cache[db_name] = True
            logger.debug("Glue database '%s' exists", db_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "EntityNotFoundException":
                self._db_cache[db_name] = False
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Glue database '{db_name}' not found "
                            f"(referenced by asset '{asset_name}')"
                        ),
                        resource=db_name,
                        service="glue",
                        details={
                            "database_name": db_name,
                            "resource_type": "database",
                            "asset": asset_name,
                            "error_code": error_code,
                        },
                    )
                )
            else:
                self._db_cache[db_name] = False
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Failed to check Glue database '{db_name}': "
                            f"{error_code} — {exc}"
                        ),
                        resource=db_name,
                        service="glue",
                        details={"error_code": error_code},
                    )
                )
        except Exception as exc:
            self._db_cache[db_name] = False
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(f"Failed to check Glue database '{db_name}': {exc}"),
                    resource=db_name,
                    service="glue",
                )
            )

    def _check_glue_table(
        self,
        glue: Any,
        db_name: str,
        table_name: str,
        table_type: str,
        asset_name: str,
        findings: List[Finding],
    ) -> None:
        """Verify Glue table/view existence and partition accessibility with caching."""
        cache_key = (db_name, table_name)
        is_view = table_type.upper() in ("VIRTUAL_VIEW", "VIEW")
        resource_type = "view" if is_view else "table"

        if cache_key in self._table_cache:
            if not self._table_cache[cache_key]:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Glue {resource_type} '{db_name}.{table_name}' "
                            f"not found (referenced by asset '{asset_name}')"
                        ),
                        resource=f"{db_name}.{table_name}",
                        service="glue",
                        details={
                            "database_name": db_name,
                            "table_name": table_name,
                            "resource_type": resource_type,
                            "asset": asset_name,
                        },
                    )
                )
            else:
                # Table exists — check partitions for non-view tables
                if not is_view:
                    self._check_partitions(
                        glue, db_name, table_name, asset_name, findings
                    )
            return

        try:
            glue.get_table(DatabaseName=db_name, Name=table_name)
            self._table_cache[cache_key] = True
            logger.debug("Glue %s '%s.%s' exists", resource_type, db_name, table_name)
            # Check partitions for non-view tables
            if not is_view:
                self._check_partitions(glue, db_name, table_name, asset_name, findings)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "EntityNotFoundException":
                self._table_cache[cache_key] = False
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Glue {resource_type} '{db_name}.{table_name}' "
                            f"not found (referenced by asset '{asset_name}')"
                        ),
                        resource=f"{db_name}.{table_name}",
                        service="glue",
                        details={
                            "database_name": db_name,
                            "table_name": table_name,
                            "resource_type": resource_type,
                            "asset": asset_name,
                            "error_code": error_code,
                        },
                    )
                )
            else:
                self._table_cache[cache_key] = False
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Failed to check Glue {resource_type} "
                            f"'{db_name}.{table_name}': {error_code} — {exc}"
                        ),
                        resource=f"{db_name}.{table_name}",
                        service="glue",
                        details={"error_code": error_code},
                    )
                )
        except Exception as exc:
            self._table_cache[cache_key] = False
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=(
                        f"Failed to check Glue {resource_type} "
                        f"'{db_name}.{table_name}': {exc}"
                    ),
                    resource=f"{db_name}.{table_name}",
                    service="glue",
                )
            )

    def _check_partitions(
        self,
        glue: Any,
        db_name: str,
        table_name: str,
        asset_name: str,
        findings: List[Finding],
    ) -> None:
        """Check partition accessibility for Glue tables (not views)."""
        cache_key = (db_name, table_name)
        if cache_key in self._partition_cache:
            if not self._partition_cache[cache_key]:
                findings.append(
                    Finding(
                        severity=Severity.WARNING,
                        message=(
                            f"Partitions for Glue table '{db_name}.{table_name}' "
                            f"are inaccessible (referenced by asset '{asset_name}')"
                        ),
                        resource=f"{db_name}.{table_name}",
                        service="glue",
                        details={
                            "database_name": db_name,
                            "table_name": table_name,
                            "asset": asset_name,
                        },
                    )
                )
            return

        try:
            glue.get_partitions(
                DatabaseName=db_name, TableName=table_name, MaxResults=1
            )
            self._partition_cache[cache_key] = True
            logger.debug("Partitions for '%s.%s' are accessible", db_name, table_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            self._partition_cache[cache_key] = False
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Partitions for Glue table '{db_name}.{table_name}' "
                        f"are inaccessible: {error_code} "
                        f"(referenced by asset '{asset_name}')"
                    ),
                    resource=f"{db_name}.{table_name}",
                    service="glue",
                    details={
                        "database_name": db_name,
                        "table_name": table_name,
                        "asset": asset_name,
                        "error_code": error_code,
                    },
                )
            )
        except Exception as exc:
            self._partition_cache[cache_key] = False
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Partitions for Glue table '{db_name}.{table_name}' "
                        f"are inaccessible: {exc} "
                        f"(referenced by asset '{asset_name}')"
                    ),
                    resource=f"{db_name}.{table_name}",
                    service="glue",
                )
            )

    # ------------------------------------------------------------------
    # 2. Data source validation
    # ------------------------------------------------------------------

    def _check_data_sources(
        self,
        assets: List[Dict[str, Any]],
        domain_id: str,
        project_id: str,
        region: str,
        findings: List[Finding],
    ) -> None:
        """Validate data source references in assets."""
        if not domain_id or not project_id:
            return

        try:
            dz = boto3.client("datazone", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create DataZone client: {exc}",
                    service="datazone",
                )
            )
            return

        for asset in assets:
            asset_name = asset.get("name", "unknown")
            forms_input = asset.get("formsInput", [])
            if not isinstance(forms_input, list):
                continue

            # Extract database name from GlueTableFormType if present
            db_name_for_asset = extract_database_name_from_forms(forms_input)

            for form in forms_input:
                if not isinstance(form, dict):
                    continue
                type_id = get_form_type_ref(form)
                if DATA_SOURCE_REF_FORM_TYPE not in type_id:
                    continue

                content = parse_form_content(form.get("content"))
                if content is None:
                    continue

                ds_type = content.get("dataSourceType", "GLUE")
                db_name = db_name_for_asset or ""

                cache_key = (ds_type, db_name)
                if cache_key in self._data_source_cache:
                    if not self._data_source_cache[cache_key]:
                        findings.append(
                            Finding(
                                severity=Severity.WARNING,
                                message=(
                                    f"No matching data source found for "
                                    f"type '{ds_type}' and database "
                                    f"'{db_name}' in target project "
                                    f"(referenced by asset '{asset_name}')"
                                ),
                                resource=asset_name,
                                service="datazone",
                                details={
                                    "data_source_type": ds_type,
                                    "database_name": db_name,
                                    "asset": asset_name,
                                },
                            )
                        )
                    continue

                found = self._find_data_source(
                    dz, domain_id, project_id, ds_type, db_name
                )
                self._data_source_cache[cache_key] = found

                if not found:
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"No matching data source found for "
                                f"type '{ds_type}' and database "
                                f"'{db_name}' in target project "
                                f"(referenced by asset '{asset_name}')"
                            ),
                            resource=asset_name,
                            service="datazone",
                            details={
                                "data_source_type": ds_type,
                                "database_name": db_name,
                                "asset": asset_name,
                            },
                        )
                    )

    def _find_data_source(
        self,
        dz: Any,
        domain_id: str,
        project_id: str,
        ds_type: str,
        db_name: str,
    ) -> bool:
        """Check if a matching data source exists in the target project."""
        try:
            resp = dz.list_data_sources(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                maxResults=25,
            )
            candidates = [
                ds
                for ds in resp.get("items", [])
                if ds.get("type") == ds_type
                and ds.get("status") in DATA_SOURCE_VALID_STATUSES
            ]
            if not candidates:
                return False

            if not db_name:
                return True

            # Check if any candidate covers the database
            for ds in candidates:
                ds_name = ds.get("name", "")
                if db_name in ds_name:
                    return True

            # Fallback: any candidate of the right type counts
            return len(candidates) > 0
        except Exception as exc:
            logger.warning(
                "Failed to list data sources (type=%s, db=%s): %s",
                ds_type,
                db_name,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # 3. Custom form type validation
    # ------------------------------------------------------------------

    def _check_custom_form_types(
        self,
        asset_types: List[Dict[str, Any]],
        domain_id: str,
        region: str,
        findings: List[Finding],
    ) -> None:
        """Validate custom form types referenced by asset types."""
        if not domain_id:
            return

        try:
            dz = boto3.client("datazone", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create DataZone client: {exc}",
                    service="datazone",
                )
            )
            return

        for asset_type in asset_types:
            at_name = asset_type.get("name", "unknown")
            forms_input = asset_type.get("formsInput", {})
            if not isinstance(forms_input, dict):
                continue

            for form_name, form_config in forms_input.items():
                if not isinstance(form_config, dict):
                    continue
                type_id = get_form_type_ref(form_config)
                if not type_id:
                    continue

                # Skip managed form types (Req 13.12)
                if _is_managed_resource(type_id):
                    logger.debug("Skipping managed form type '%s'", type_id)
                    continue

                if type_id in self._form_type_cache:
                    if self._form_type_cache[type_id] is None:
                        findings.append(
                            Finding(
                                severity=Severity.ERROR,
                                message=(
                                    f"Custom form type '{type_id}' not found "
                                    f"in target domain (referenced by asset "
                                    f"type '{at_name}')"
                                ),
                                resource=type_id,
                                service="datazone",
                                details={
                                    "form_type": type_id,
                                    "asset_type": at_name,
                                },
                            )
                        )
                    continue

                result = self._get_form_type(dz, domain_id, type_id)
                self._form_type_cache[type_id] = result

                if result is None:
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=(
                                f"Custom form type '{type_id}' not found "
                                f"in target domain (referenced by asset "
                                f"type '{at_name}')"
                            ),
                            resource=type_id,
                            service="datazone",
                            details={
                                "form_type": type_id,
                                "asset_type": at_name,
                            },
                        )
                    )

    # ------------------------------------------------------------------
    # 4. Custom asset type validation
    # ------------------------------------------------------------------

    def _check_custom_asset_types(
        self,
        assets: List[Dict[str, Any]],
        domain_id: str,
        region: str,
        findings: List[Finding],
    ) -> None:
        """Validate custom asset types referenced by assets."""
        if not domain_id:
            return

        try:
            dz = boto3.client("datazone", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create DataZone client: {exc}",
                    service="datazone",
                )
            )
            return

        for asset in assets:
            asset_name = asset.get("name", "unknown")
            type_id = asset.get("typeIdentifier", "")
            if not type_id:
                continue

            # Skip managed asset types (Req 13.12)
            if _is_managed_resource(type_id):
                logger.debug("Skipping managed asset type '%s'", type_id)
                continue

            if type_id in self._asset_type_cache:
                if not self._asset_type_cache[type_id]:
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=(
                                f"Custom asset type '{type_id}' not found "
                                f"in target domain (referenced by asset "
                                f"'{asset_name}')"
                            ),
                            resource=type_id,
                            service="datazone",
                            details={
                                "asset_type_identifier": type_id,
                                "asset": asset_name,
                            },
                        )
                    )
                continue

            found = self._search_asset_type(dz, domain_id, type_id)
            self._asset_type_cache[type_id] = found

            if not found:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Custom asset type '{type_id}' not found "
                            f"in target domain (referenced by asset "
                            f"'{asset_name}')"
                        ),
                        resource=type_id,
                        service="datazone",
                        details={
                            "asset_type_identifier": type_id,
                            "asset": asset_name,
                        },
                    )
                )

    # ------------------------------------------------------------------
    # 5. Form type revision validation
    # ------------------------------------------------------------------

    def _check_form_type_revisions(
        self,
        assets: List[Dict[str, Any]],
        domain_id: str,
        region: str,
        findings: List[Finding],
    ) -> None:
        """Validate form type revisions referenced by assets."""
        if not domain_id:
            return

        try:
            dz = boto3.client("datazone", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create DataZone client: {exc}",
                    service="datazone",
                )
            )
            return

        for asset in assets:
            asset_name = asset.get("name", "unknown")
            forms_input = asset.get("formsInput", [])
            if not isinstance(forms_input, list):
                continue

            for form in forms_input:
                if not isinstance(form, dict):
                    continue
                type_id = get_form_type_ref(form)
                type_revision = form.get("typeRevision")

                if not type_id or not type_revision:
                    continue

                # Skip managed form types (Req 13.12)
                if _is_managed_resource(type_id):
                    continue

                # Get form type info (uses cache)
                if type_id not in self._form_type_cache:
                    result = self._get_form_type(dz, domain_id, type_id)
                    self._form_type_cache[type_id] = result

                form_type_info = self._form_type_cache[type_id]
                if form_type_info is None:
                    # Form type doesn't exist — already reported by
                    # _check_custom_form_types; skip revision check
                    continue

                target_revision = form_type_info.get("revision")
                if target_revision is None:
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"Form type '{type_id}' revision "
                                f"'{type_revision}' cannot be resolved in "
                                f"target domain (referenced by asset "
                                f"'{asset_name}')"
                            ),
                            resource=type_id,
                            service="datazone",
                            details={
                                "form_type": type_id,
                                "expected_revision": type_revision,
                                "asset": asset_name,
                            },
                        )
                    )
                elif str(type_revision) != str(target_revision):
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"Form type '{type_id}' revision "
                                f"'{type_revision}' does not match target "
                                f"revision '{target_revision}' "
                                f"(referenced by asset '{asset_name}')"
                            ),
                            resource=type_id,
                            service="datazone",
                            details={
                                "form_type": type_id,
                                "expected_revision": type_revision,
                                "target_revision": target_revision,
                                "asset": asset_name,
                            },
                        )
                    )

    # ------------------------------------------------------------------
    # AWS API helpers
    # ------------------------------------------------------------------

    def _get_form_type(
        self,
        dz: Any,
        domain_id: str,
        form_type_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Call ``datazone:GetFormType`` and return the response or None."""
        try:
            resp = dz.get_form_type(
                domainIdentifier=domain_id,
                formTypeIdentifier=form_type_id,
            )
            return {
                "name": resp.get("name"),
                "revision": resp.get("revision"),
            }
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            logger.debug("GetFormType failed for '%s': %s", form_type_id, error_code)
            return None
        except Exception as exc:
            logger.debug("GetFormType failed for '%s': %s", form_type_id, exc)
            return None

    def _search_asset_type(
        self,
        dz: Any,
        domain_id: str,
        type_identifier: str,
    ) -> bool:
        """Call ``datazone:SearchTypes`` to verify asset type existence."""
        try:
            resp = dz.search_types(
                domainIdentifier=domain_id,
                managed=False,
                searchScope="ASSET_TYPE",
                searchIn=[{"attribute": "DESCRIPTION"}],
                filters={
                    "and": [
                        {
                            "filter": {
                                "attribute": "typeName",
                                "value": type_identifier,
                            }
                        }
                    ]
                },
                maxResults=1,
            )
            items = resp.get("items", [])
            return len(items) > 0
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            logger.debug("SearchTypes failed for '%s': %s", type_identifier, error_code)
            return False
        except Exception as exc:
            logger.debug("SearchTypes failed for '%s': %s", type_identifier, exc)
            return False

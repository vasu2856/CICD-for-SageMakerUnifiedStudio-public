"""IAM permission verification checker (Phase 3).

Uses ``iam:SimulatePrincipalPolicy`` to verify the caller has the required
permissions for every deployment feature enabled in the manifest.  Builds a
permissions map from the deployment configuration (S3, DataZone, catalog, IAM,
QuickSight) plus ``BOOTSTRAP_PERMISSION_MAP`` for each bootstrap action type,
plus Glue permissions when catalog assets contain Glue references.

Falls back to WARNING (not ERROR) if ``SimulatePrincipalPolicy`` itself is
denied.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11,
              4.12, 4.13
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError as BotocoreClientError

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity
from smus_cicd.helpers.catalog_import import has_glue_references

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bootstrap action type → required IAM actions
# ---------------------------------------------------------------------------
BOOTSTRAP_PERMISSION_MAP: Dict[str, List[str]] = {
    "workflow.create": [
        "airflow-serverless:CreateWorkflow",
        "airflow-serverless:GetWorkflow",
    ],
    "workflow.run": [
        "airflow-serverless:CreateWorkflowRun",
    ],
    "workflow.logs": [
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
    ],
    "workflow.monitor": [
        "airflow-serverless:GetWorkflow",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
    ],
    "quicksight.refresh_dataset": [
        "quicksight:CreateIngestion",
        "quicksight:DescribeIngestion",
        "quicksight:ListDataSets",
    ],
    "eventbridge.put_events": [
        "events:PutEvents",
    ],
    "project.create_environment": [
        "datazone:CreateEnvironment",
    ],
    "project.create_connection": [
        "datazone:CreateConnection",
    ],
    "catalog.dependency_check": [
        "glue:GetTable",
        "glue:GetDatabase",
        "glue:GetPartitions",
    ],
}

# Glue permissions needed when catalog assets reference Glue Data Catalog
# resources (tables, views, databases).
_GLUE_PERMISSIONS: List[str] = [
    "glue:GetTable",
    "glue:GetDatabase",
    "glue:GetPartitions",
]

# DataZone policy grant → catalog resource types that require it.
# A grant is only checked when at least one of its resource types is present.
_GRANT_RESOURCE_TYPES: Dict[str, List[str]] = {
    "CREATE_GLOSSARY": ["glossaries", "glossaryTerms"],
    "CREATE_FORM_TYPE": ["formTypes"],
    "CREATE_ASSET_TYPE": ["assetTypes"],
}


class PermissionChecker:
    """Verifies IAM permissions via ``iam:SimulatePrincipalPolicy``."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.target_config is None or context.config is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "Skipping permission verification: "
                        "manifest/target not loaded"
                    ),
                )
            )
            return findings

        region = context.config.get("region", "us-east-1")

        # --- Step 1: Get caller identity ---
        caller_arn = self._get_caller_arn(region, findings)
        if caller_arn is None:
            return findings

        # --- Step 2: Build permissions map ---
        permissions_map = self._build_permissions_map(context, region)

        if not permissions_map:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No permissions to verify (empty deployment config)",
                )
            )
            return findings

        # --- Step 3: Simulate permissions ---
        self._simulate_permissions(caller_arn, permissions_map, region, findings)

        # --- Step 4: Check DataZone policy grants ---
        self._check_datazone_policy_grants(context, region, findings)

        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_caller_arn(self, region: str, findings: List[Finding]) -> Optional[str]:
        """Retrieve the caller ARN via STS ``get_caller_identity``.

        ``SimulatePrincipalPolicy`` requires an IAM principal ARN, not an STS
        assumed-role ARN.  When the caller is an assumed role
        (``arn:aws:sts::ACCT:assumed-role/ROLE/SESSION``) we convert it to the
        corresponding IAM role ARN (``arn:aws:iam::ACCT:role/ROLE``).
        """
        try:
            sts = boto3.client("sts", region_name=region)
            identity = sts.get_caller_identity()
            caller_arn = identity["Arn"]
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=f"Caller identity: {caller_arn}",
                    resource=caller_arn,
                    service="sts",
                )
            )
            # SimulatePrincipalPolicy needs an IAM principal ARN, not STS.
            # Convert arn:aws:sts::ACCT:assumed-role/ROLE/SESSION
            #      → arn:aws:iam::ACCT:role/ROLE
            if ":assumed-role/" in caller_arn:
                parts = caller_arn.split(":")
                # parts = ['arn','aws','sts','','ACCT','assumed-role/ROLE/SESSION']
                account_id = parts[4]
                role_path = parts[5]  # 'assumed-role/ROLE/SESSION'
                role_name = role_path.split("/")[1]  # 'ROLE'
                caller_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
                logger.debug("Converted STS ARN to IAM role ARN: %s", caller_arn)
            return caller_arn
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Failed to get caller identity: {exc}",
                    service="sts",
                )
            )
            return None

    def _resolve_datazone_arn(self, config: Dict[str, Any], region: str) -> str:
        """Build a DataZone resource ARN for ``SimulatePrincipalPolicy``.

        When the real *domain_id* and *account_id* are available we construct a
        fully-qualified ARN.  When either value is unknown (wildcard ``"*"``),
        we return ``"*"`` because ``SimulatePrincipalPolicy`` treats
        partial-wildcard ARNs like ``arn:aws:datazone:…:*:domain/*``
        differently from a plain ``"*"`` — the former causes ``implicitDeny``
        for most DataZone actions even when the caller has ``*`` permissions.
        """
        account_id = config.get("account_id", "*")
        domain_id = config.get("domain_id", "*")

        # Attempt to resolve domain_id via DataZone if still a wildcard
        if domain_id == "*":
            try:
                from smus_cicd.helpers.utils import _resolve_domain_id

                resolved = _resolve_domain_id(config, region)
                if resolved:
                    domain_id = resolved
            except Exception:
                pass  # keep wildcard

        if domain_id == "*" or account_id == "*":
            return "*"

        return f"arn:aws:datazone:{region}:{account_id}:domain/{domain_id}"

    def _build_permissions_map(
        self, context: DryRunContext, region: str
    ) -> Dict[str, List[str]]:
        """Build ``{resource_arn: [iam_action, ...]}`` from the deployment config."""
        permissions: Dict[str, List[str]] = {}
        target = context.target_config
        config = context.config or {}
        account_id = config.get("account_id", "*")

        # Resolve a DataZone resource ARN that SimulatePrincipalPolicy handles
        # correctly (plain "*" when real IDs are unavailable).
        dz_arn = self._resolve_datazone_arn(config, region)

        # --- S3 storage permissions (Req 4.1) ---
        self._add_s3_permissions(context, permissions, account_id, region)

        # --- DataZone permissions (Req 4.2) ---
        self._add_datazone_permissions(target, permissions, dz_arn)

        # --- Catalog import permissions (Req 4.3, 4.7) ---
        self._add_catalog_permissions(context, permissions, dz_arn)

        # --- IAM permissions (Req 4.4) ---
        self._add_iam_permissions(target, permissions, account_id)

        # --- QuickSight permissions (Req 4.5) ---
        self._add_quicksight_permissions(
            target, permissions, account_id, region, context
        )

        # --- Bootstrap action permissions (Req 4.8–4.12) ---
        self._add_bootstrap_permissions(target, permissions)

        # --- Glue permissions for catalog Glue references (Req 4.13) ---
        self._add_glue_permissions_for_catalog(context, permissions, account_id, region)

        return permissions

    def _add_s3_permissions(
        self,
        context: DryRunContext,
        permissions: Dict[str, List[str]],
        account_id: str,
        region: str,
    ) -> None:
        """Add ``s3:PutObject`` and ``s3:GetObject`` per target S3 bucket.

        Bucket names are resolved through DataZone project connections when
        possible.  Unresolved connections fall back to a wildcard S3 ARN so
        that the permission check still runs (with reduced specificity).

        Skipped when the bundle contains no files for any declared storage
        item — there is nothing to upload so S3 permissions are irrelevant.
        """
        target = context.target_config
        if not target or not target.deployment_configuration:
            return

        storage_items = target.deployment_configuration.storage or []
        if not storage_items:
            return

        # Skip if the bundle has no files matching any storage item
        if context.bundle_files:
            has_storage_files = any(
                any(
                    f.startswith(f"{item.name}/") or f == item.name
                    for f in context.bundle_files
                )
                for item in storage_items
                if getattr(item, "name", None)
            )
            if not has_storage_files:
                return

        # Collect connection names
        connection_names: set = set()
        for item in storage_items:
            conn = getattr(item, "connectionName", None)
            if conn:
                connection_names.add(conn)

        if not connection_names:
            return

        # Resolve real bucket names via DataZone project connections
        project_connections = self._get_project_connections(context, region)

        seen_buckets: set = set()
        for conn_name in connection_names:
            conn_info = (
                project_connections.get(conn_name) if project_connections else None
            )
            bucket_name = None
            if conn_info:
                s3_uri = conn_info.get("s3Uri", "")
                if s3_uri:
                    bucket_name = s3_uri.replace("s3://", "").rstrip("/").split("/")[0]

            if not bucket_name:
                # Fallback: use wildcard ARN so we still check S3 permissions
                bucket_name = "*"

            if bucket_name in seen_buckets:
                continue
            seen_buckets.add(bucket_name)

            arn = f"arn:aws:s3:::{bucket_name}/*"
            permissions.setdefault(arn, []).extend(["s3:PutObject", "s3:GetObject"])

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

    def _add_datazone_permissions(
        self,
        target: Any,
        permissions: Dict[str, List[str]],
        dz_arn: str,
    ) -> None:
        """Add DataZone domain/project permissions."""
        permissions.setdefault(dz_arn, []).extend(
            [
                "datazone:GetDomain",
                "datazone:GetProject",
                "datazone:SearchListings",
            ]
        )

    def _add_catalog_permissions(
        self,
        context: DryRunContext,
        permissions: Dict[str, List[str]],
        dz_arn: str,
    ) -> None:
        """Add catalog import and grant permissions when catalog assets exist."""
        if context.catalog_data is None:
            return

        # Catalog import permissions (Req 4.3)
        permissions.setdefault(dz_arn, []).extend(
            [
                "datazone:CreateAsset",
                "datazone:CreateGlossary",
                "datazone:CreateGlossaryTerm",
                "datazone:CreateFormType",
            ]
        )
        # Catalog grant permissions (Req 4.7)
        permissions.setdefault(dz_arn, []).extend(
            [
                "datazone:CreateSubscriptionGrant",
                "datazone:GetSubscriptionGrant",
                "datazone:CreateSubscriptionRequest",
            ]
        )

    def _add_iam_permissions(
        self,
        target: Any,
        permissions: Dict[str, List[str]],
        account_id: str,
    ) -> None:
        """Add IAM role creation permissions when role config is present."""
        project = getattr(target, "project", None)
        if project is None:
            return
        role_config = getattr(project, "role", None)
        if not role_config:
            return

        arn = f"arn:aws:iam::{account_id}:role/*"
        permissions.setdefault(arn, []).extend(
            [
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "iam:PutRolePolicy",
            ]
        )

    def _add_quicksight_permissions(
        self,
        target: Any,
        permissions: Dict[str, List[str]],
        account_id: str,
        region: str,
        context: DryRunContext,
    ) -> None:
        """Add QuickSight permissions when dashboards are configured.

        Skipped when the bundle contains no QuickSight files — there is
        nothing to deploy so QuickSight permissions are irrelevant.
        """
        qs_dashboards = getattr(target, "quicksight", None) or []
        if not qs_dashboards:
            return

        # Skip if the bundle has no QuickSight files
        if context.bundle_files:
            has_qs_files = any(
                f.startswith("quicksight/") for f in context.bundle_files
            )
            if not has_qs_files:
                return

        arn = f"arn:aws:quicksight:{region}:{account_id}:dashboard/*"
        permissions.setdefault(arn, []).extend(
            [
                "quicksight:DescribeDashboard",
                "quicksight:CreateDashboard",
                "quicksight:UpdateDashboard",
            ]
        )

    def _add_bootstrap_permissions(
        self,
        target: Any,
        permissions: Dict[str, List[str]],
    ) -> None:
        """Add permissions for each bootstrap action type."""
        bootstrap = getattr(target, "bootstrap", None)
        if not bootstrap:
            return

        actions = getattr(bootstrap, "actions", None) or []
        for action in actions:
            action_type = action.type
            required = BOOTSTRAP_PERMISSION_MAP.get(action_type)
            if not required:
                continue
            # Use a wildcard ARN for bootstrap actions since the exact
            # resource ARN depends on runtime parameters.
            arn = "*"
            permissions.setdefault(arn, []).extend(required)

    def _add_glue_permissions_for_catalog(
        self,
        context: DryRunContext,
        permissions: Dict[str, List[str]],
        account_id: str,
        region: str,
    ) -> None:
        """Add Glue permissions when catalog assets contain Glue references."""
        if not context.catalog_data:
            return

        if has_glue_references(context.catalog_data):
            arn = f"arn:aws:glue:{region}:{account_id}:*"
            permissions.setdefault(arn, []).extend(_GLUE_PERMISSIONS)

    def _simulate_permissions(
        self,
        caller_arn: str,
        permissions_map: Dict[str, List[str]],
        region: str,
        findings: List[Finding],
    ) -> None:
        """Call ``iam:SimulatePrincipalPolicy`` and record findings."""
        try:
            iam = boto3.client("iam", region_name=region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Failed to create IAM client: {exc}",
                    service="iam",
                )
            )
            return

        for resource_arn, actions in permissions_map.items():
            # De-duplicate actions for the same resource
            unique_actions = sorted(set(actions))
            try:
                response = iam.simulate_principal_policy(
                    PolicySourceArn=caller_arn,
                    ActionNames=unique_actions,
                    ResourceArns=[resource_arn],
                )
                self._process_simulation_results(response, resource_arn, findings)
            except BotocoreClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in ("AccessDenied", "AccessDeniedException"):
                    # Fall back to WARNING — we cannot verify but that
                    # doesn't mean permissions are missing (Req 4.6 fallback).
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"Could not verify permissions for "
                                f"{resource_arn}: {error_code}"
                            ),
                            resource=resource_arn,
                            service="iam",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"SimulatePrincipalPolicy error for "
                                f"{resource_arn}: {exc}"
                            ),
                            resource=resource_arn,
                            service="iam",
                        )
                    )
            except Exception as exc:
                findings.append(
                    Finding(
                        severity=Severity.WARNING,
                        message=(
                            f"Unexpected error verifying permissions for "
                            f"{resource_arn}: {exc}"
                        ),
                        resource=resource_arn,
                        service="iam",
                    )
                )

    def _process_simulation_results(
        self,
        response: Dict[str, Any],
        resource_arn: str,
        findings: List[Finding],
    ) -> None:
        """Translate SimulatePrincipalPolicy results into findings."""
        for result in response.get("EvaluationResults", []):
            action_name = result.get("EvalActionName", "unknown")
            decision = result.get("EvalDecision", "")

            if decision == "allowed":
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"Permission '{action_name}' allowed on " f"{resource_arn}"
                        ),
                        resource=resource_arn,
                        service=action_name.split(":")[0],
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Permission '{action_name}' denied on " f"{resource_arn}"
                        ),
                        resource=resource_arn,
                        service=action_name.split(":")[0],
                        details={
                            "action": action_name,
                            "resource": resource_arn,
                            "decision": decision,
                        },
                    )
                )

    def _check_datazone_policy_grants(
        self,
        context: DryRunContext,
        region: str,
        findings: List[Finding],
    ) -> None:
        """Check DataZone policy grants on the project's domain unit.

        Only runs when catalog resources exist.  For each required grant type,
        checks whether the corresponding resource types are present in the
        catalog data and, if so, verifies the grant exists via
        ``list_policy_grants``.
        """
        if context.catalog_data is None:
            return

        config = context.config or {}

        # --- Resolve domain_id ---
        try:
            from smus_cicd.helpers.utils import _resolve_domain_id

            domain_id = _resolve_domain_id(config, region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Could not resolve domain ID for grant check: {exc}",
                    service="datazone",
                )
            )
            return

        if not domain_id:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "No domain_id resolved; " "skipping DataZone policy grant check"
                    ),
                    service="datazone",
                )
            )
            return

        # --- Resolve project_id ---
        project_name = config.get("project_name")
        if not project_name:
            # Try to get from target_config
            project_cfg = getattr(context.target_config, "project", None)
            project_name = getattr(project_cfg, "name", None) if project_cfg else None

        if not project_name:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        "No project name available; "
                        "skipping DataZone policy grant check"
                    ),
                    service="datazone",
                )
            )
            return

        try:
            from smus_cicd.helpers.datazone import get_project_id_by_name

            project_id = get_project_id_by_name(project_name, domain_id, region)
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Could not resolve project '{project_name}' "
                        f"for grant check: {exc}"
                    ),
                    service="datazone",
                )
            )
            return

        if not project_id:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Project '{project_name}' not found in domain "
                        f"'{domain_id}'; skipping grant check"
                    ),
                    service="datazone",
                )
            )
            return

        # --- Resolve domain_unit_id ---
        try:
            dz = boto3.client("datazone", region_name=region)
            project_resp = dz.get_project(
                domainIdentifier=domain_id, identifier=project_id
            )
            domain_unit_id = project_resp.get("domainUnitId")
        except Exception as exc:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Could not resolve domain unit for project "
                        f"'{project_id}': {exc}"
                    ),
                    service="datazone",
                )
            )
            return

        if not domain_unit_id:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=(
                        f"Project '{project_id}' has no domainUnitId; "
                        "skipping grant check"
                    ),
                    service="datazone",
                )
            )
            return

        # --- Check each required grant ---
        catalog = context.catalog_data
        for grant_type, resource_types in _GRANT_RESOURCE_TYPES.items():
            # Only check if the catalog actually contains these resource types
            has_resources = any(len(catalog.get(rt, [])) > 0 for rt in resource_types)
            if not has_resources:
                continue

            already_granted = False
            try:
                resp = dz.list_policy_grants(
                    domainIdentifier=domain_id,
                    entityType="DOMAIN_UNIT",
                    entityIdentifier=domain_unit_id,
                    policyType=grant_type,
                )
                if resp.get("grantList"):
                    already_granted = True
            except BotocoreClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in ("AccessDenied", "AccessDeniedException"):
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=(
                                f"Cannot verify {grant_type} grant: "
                                f"access denied on list_policy_grants"
                            ),
                            service="datazone",
                        )
                    )
                    continue
                findings.append(
                    Finding(
                        severity=Severity.WARNING,
                        message=f"Error checking {grant_type} grant: {exc}",
                        service="datazone",
                    )
                )
                continue
            except Exception as exc:
                findings.append(
                    Finding(
                        severity=Severity.WARNING,
                        message=f"Error checking {grant_type} grant: {exc}",
                        service="datazone",
                    )
                )
                continue

            rt_display = ", ".join(resource_types)
            if already_granted:
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=(
                            f"DataZone policy grant '{grant_type}' is present "
                            f"on domain unit '{domain_unit_id}'"
                        ),
                        resource=grant_type,
                        service="datazone",
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"DataZone policy grant '{grant_type}' is MISSING "
                            f"on domain unit '{domain_unit_id}'. "
                            f"Required for catalog resource types: {rt_display}. "
                            f"The catalog import will fail without this grant."
                        ),
                        resource=grant_type,
                        service="datazone",
                        details={
                            "grant_type": grant_type,
                            "domain_unit_id": domain_unit_id,
                            "required_for": resource_types,
                        },
                    )
                )

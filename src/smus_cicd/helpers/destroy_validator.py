"""Validation phase for the destroy command.

Performs read-only discovery of all resources that would be deleted,
detects collisions, and collects errors/warnings without aborting early.
"""

from typing import Dict, List

import boto3
import yaml

from ..helpers.airflow_serverless import (
    generate_workflow_name,
    get_workflow_definition,
    is_workflow_run_active,
    list_workflow_runs,
    list_workflows,
)
from ..helpers.connections import get_project_connections
from ..helpers.datazone import get_domain_from_target_config, get_project_id_by_name
from ..helpers.logger import get_logger
from ..helpers.operator_registry import OPERATOR_REGISTRY
from ..helpers.quicksight import (
    QuickSightDeploymentError,
    list_dashboards,
    list_data_sources,
    list_datasets,
)
from .destroy_models import ResourceToDelete, S3Target, ValidationResult

logger = get_logger("destroy")


# ---------------------------------------------------------------------------
# Pure helper functions (no AWS calls)
# ---------------------------------------------------------------------------


def _resolve_resource_prefix(stage_name: str, qs_config: dict) -> str:
    """
    Resolve the QuickSight resource prefix for a stage.

    Reads overrideParameters.ResourceIdOverrideConfiguration.PrefixForAllResources
    and replaces {stage.name} with stage_name.
    """
    prefix = (
        qs_config.get("overrideParameters", {})
        .get("ResourceIdOverrideConfiguration", {})
        .get("PrefixForAllResources", "")
    )
    return prefix.replace("{stage.name}", stage_name)


def _discover_workflow_created_resources(
    workflow_yaml: dict, stage_name: str
) -> List[ResourceToDelete]:
    """
    Parse a workflow YAML and return ResourceToDelete entries for each task.

    Tasks whose operator is in OPERATOR_REGISTRY produce a typed entry.
    Tasks with template variables in the resource name produce a "skipped" entry.
    Tasks whose operator is not in the registry produce a "skipped" entry.
    """
    resources: List[ResourceToDelete] = []

    for _workflow_key, workflow_body in workflow_yaml.items():
        if not isinstance(workflow_body, dict):
            continue
        tasks = workflow_body.get("tasks", {})
        if not isinstance(tasks, dict):
            continue

        for task_name, task in tasks.items():
            if not isinstance(task, dict):
                continue

            operator = task.get("operator", "")
            registry_entry = OPERATOR_REGISTRY.get(operator)

            if registry_entry is None:
                resources.append(
                    ResourceToDelete(
                        resource_type="skipped",
                        resource_id=task_name,
                        stage=stage_name,
                        metadata={
                            "operator": operator,
                            "reason": "operator not in registry",
                        },
                    )
                )
                continue

            resource_name_field = registry_entry["resource_name_field"]
            resource_name = task.get(resource_name_field, "")

            if "{" in str(resource_name):
                resources.append(
                    ResourceToDelete(
                        resource_type="skipped",
                        resource_id=task_name,
                        stage=stage_name,
                        metadata={
                            "operator": operator,
                            "reason": "template variable in resource name",
                            "field": resource_name_field,
                            "value": resource_name,
                        },
                    )
                )
                continue

            resource_type = registry_entry.get("resource_type", "unknown_resource")
            resources.append(
                ResourceToDelete(
                    resource_type=resource_type,
                    resource_id=resource_name,
                    stage=stage_name,
                    metadata={"operator": operator, "task_name": task_name},
                )
            )

    return resources


def _resolve_s3_targets(stage_config, connections: dict) -> List[S3Target]:
    """
    Build a deduplicated list of S3 prefixes to delete for a stage.

    Reads deployment_configuration.storage and deployment_configuration.git,
    resolves bucket + base prefix from the named connection, and constructs
    the full prefix as {connection_s3_prefix}/{targetDirectory}.

    Deduplication: if one prefix is a subdirectory of another (one starts with
    the other), keep only the parent.
    """
    if not stage_config.deployment_configuration:
        return []

    dc = stage_config.deployment_configuration
    raw_targets: List[S3Target] = []

    # Process storage entries
    for entry in dc.storage or []:
        conn_name = entry.connectionName
        conn = connections.get(conn_name, {})
        s3_uri = conn.get("s3Uri", "")
        bucket = conn.get("bucket_name", "")
        if not bucket and s3_uri:
            parts = s3_uri.replace("s3://", "").split("/", 1)
            bucket = parts[0]

        base_prefix = ""
        if s3_uri:
            parts = s3_uri.replace("s3://", "").split("/", 1)
            base_prefix = parts[1].rstrip("/") if len(parts) > 1 else ""

        target_dir = (entry.targetDirectory or "").strip("/")
        if base_prefix:
            full_prefix = f"{base_prefix}/{target_dir}" if target_dir else base_prefix
        else:
            full_prefix = target_dir

        if bucket:
            raw_targets.append(
                S3Target(bucket=bucket, prefix=full_prefix, connection_name=conn_name)
            )

    # Process git entries
    for entry in dc.git or []:
        conn_name = entry.connectionName
        conn = connections.get(conn_name, {})
        s3_uri = conn.get("s3Uri", "")
        bucket = conn.get("bucket_name", "")
        if not bucket and s3_uri:
            parts = s3_uri.replace("s3://", "").split("/", 1)
            bucket = parts[0]

        base_prefix = ""
        if s3_uri:
            parts = s3_uri.replace("s3://", "").split("/", 1)
            base_prefix = parts[1].rstrip("/") if len(parts) > 1 else ""

        target_dir = (entry.targetDirectory or "").strip("/")
        if base_prefix:
            full_prefix = f"{base_prefix}/{target_dir}" if target_dir else base_prefix
        else:
            full_prefix = target_dir

        if bucket:
            raw_targets.append(
                S3Target(bucket=bucket, prefix=full_prefix, connection_name=conn_name)
            )

    # Deduplicate: remove targets whose prefix is a subdirectory of another target
    deduplicated: List[S3Target] = []
    for i, candidate in enumerate(raw_targets):
        is_subdir = False
        for j, other in enumerate(raw_targets):
            if i == j:
                continue
            if candidate.bucket != other.bucket:
                continue
            other_prefix_with_slash = other.prefix.rstrip("/") + "/"
            if candidate.prefix.rstrip("/") + "/" != other_prefix_with_slash and (
                candidate.prefix.startswith(other_prefix_with_slash)
                or candidate.prefix == other.prefix
                and i > j
            ):
                is_subdir = True
                break
        if not is_subdir:
            deduplicated.append(candidate)

    return deduplicated


# ---------------------------------------------------------------------------
# Validation phase
# ---------------------------------------------------------------------------


def _validate_stage(
    stage_name: str, stage_config, manifest, region: str
) -> ValidationResult:
    """
    Perform read-only discovery for one stage and return a ValidationResult.

    Collects ALL errors and warnings without aborting early.
    """
    errors: List[str] = []
    warnings: List[str] = []
    resources: List[ResourceToDelete] = []
    active_workflow_runs: Dict[str, List[str]] = {}

    effective_region = region or stage_config.domain.region

    # --- Resolve domain + project IDs ---
    try:
        domain_id, domain_name = get_domain_from_target_config(
            stage_config, region=effective_region
        )
    except Exception as e:
        errors.append(f"[{stage_name}] Could not resolve domain: {e}")
        return ValidationResult(
            errors=errors, warnings=warnings, resources=resources,
            active_workflow_runs=active_workflow_runs,
        )

    try:
        project_id = get_project_id_by_name(
            stage_config.project.name, domain_id, effective_region
        )
    except Exception as e:
        errors.append(
            f"[{stage_name}] Could not resolve project '{stage_config.project.name}': {e}"
        )
        project_id = None

    # --- Resolve S3 connections ---
    connections: dict = {}
    if project_id:
        try:
            connections = get_project_connections(
                project_id=project_id, domain_id=domain_id, region=effective_region,
            )
        except Exception as e:
            warnings.append(f"[{stage_name}] Could not resolve S3 connections: {e}")

    # --- QuickSight resources ---
    dc = stage_config.deployment_configuration
    if dc and dc.quicksight:
        qs_config = dc.quicksight
        prefix = _resolve_resource_prefix(stage_name, qs_config)

        try:
            account_id = boto3.client(
                "sts", region_name=effective_region
            ).get_caller_identity()["Account"]
        except Exception as e:
            errors.append(f"[{stage_name}] Could not get AWS account ID: {e}")
            account_id = None

        if account_id and prefix:
            declared_count = len(manifest.content.quicksight)

            # Dashboards
            try:
                all_dashboards = list_dashboards(account_id, effective_region)
                matched_dashboards = [
                    d for d in all_dashboards
                    if d.get("DashboardId", "").startswith(prefix)
                ]
                if len(matched_dashboards) > declared_count:
                    ids = [d["DashboardId"] for d in matched_dashboards]
                    errors.append(
                        f"[{stage_name}] QuickSight dashboard collision: found "
                        f"{len(matched_dashboards)} dashboards with prefix '{prefix}' "
                        f"but manifest declares {declared_count}. IDs: {ids}"
                    )
                else:
                    for d in matched_dashboards:
                        resources.append(ResourceToDelete(
                            resource_type="quicksight_dashboard",
                            resource_id=d["DashboardId"], stage=stage_name,
                            metadata={"name": d.get("Name", "")},
                        ))
            except QuickSightDeploymentError as e:
                errors.append(f"[{stage_name}] QuickSight dashboard list failed: {e}")

            # Datasets
            try:
                all_datasets = list_datasets(account_id, effective_region)
                matched_datasets = [
                    d for d in all_datasets if d.get("DataSetId", "").startswith(prefix)
                ]
                if len(matched_datasets) > declared_count:
                    ids = [d["DataSetId"] for d in matched_datasets]
                    errors.append(
                        f"[{stage_name}] QuickSight dataset collision: found "
                        f"{len(matched_datasets)} datasets with prefix '{prefix}' "
                        f"but manifest declares {declared_count}. IDs: {ids}"
                    )
                else:
                    for d in matched_datasets:
                        resources.append(ResourceToDelete(
                            resource_type="quicksight_dataset",
                            resource_id=d["DataSetId"], stage=stage_name,
                            metadata={"name": d.get("Name", "")},
                        ))
            except QuickSightDeploymentError as e:
                errors.append(f"[{stage_name}] QuickSight dataset list failed: {e}")

            # Data sources
            try:
                all_sources = list_data_sources(account_id, effective_region)
                matched_sources = [
                    d for d in all_sources
                    if d.get("DataSourceId", "").startswith(prefix)
                ]
                if len(matched_sources) > declared_count:
                    ids = [d["DataSourceId"] for d in matched_sources]
                    errors.append(
                        f"[{stage_name}] QuickSight data source collision: found "
                        f"{len(matched_sources)} data sources with prefix '{prefix}' "
                        f"but manifest declares {declared_count}. IDs: {ids}"
                    )
                else:
                    for d in matched_sources:
                        resources.append(ResourceToDelete(
                            resource_type="quicksight_data_source",
                            resource_id=d["DataSourceId"], stage=stage_name,
                            metadata={"name": d.get("Name", "")},
                        ))
            except QuickSightDeploymentError as e:
                errors.append(f"[{stage_name}] QuickSight data source list failed: {e}")

    # --- Airflow workflows ---
    for workflow_entry in manifest.content.workflows or []:
        dag_name = workflow_entry.get("workflowName", "")
        workflow_name = generate_workflow_name(
            bundle_name=manifest.application_name,
            project_name=stage_config.project.name,
            dag_name=dag_name,
        )

        try:
            all_workflows = list_workflows(region=effective_region)
            matched = [wf for wf in all_workflows if wf["name"] == workflow_name]
        except Exception as e:
            warnings.append(
                f"[{stage_name}] Could not list workflows to find '{workflow_name}': {e}"
            )
            matched = []

        if len(matched) > 1:
            arns = [wf["workflow_arn"] for wf in matched]
            errors.append(
                f"[{stage_name}] Airflow workflow collision: {len(matched)} workflows "
                f"match name '{workflow_name}'. ARNs: {arns}"
            )
            continue

        workflow_arn = None
        if len(matched) == 1:
            workflow_arn = matched[0]["workflow_arn"]
            resources.append(ResourceToDelete(
                resource_type="airflow_workflow", resource_id=workflow_arn,
                stage=stage_name, metadata={"workflow_name": workflow_name},
            ))

            try:
                runs = list_workflow_runs(workflow_arn, region=effective_region)
                active_run_ids = [
                    r["run_id"] for r in runs if is_workflow_run_active(r)
                ]
                if active_run_ids:
                    active_workflow_runs[workflow_name] = active_run_ids
            except Exception as e:
                warnings.append(
                    f"[{stage_name}] Could not list runs for workflow "
                    f"'{workflow_name}': {e}"
                )
        else:
            warnings.append(
                f"[{stage_name}] Workflow '{workflow_name}' not found — "
                "will be skipped during destruction"
            )

        # Get workflow definition from MWAA API to discover created resources
        if workflow_arn:
            try:
                definition_str = get_workflow_definition(
                    workflow_arn, region=effective_region
                )
                if definition_str:
                    workflow_yaml = yaml.safe_load(definition_str)
                    if isinstance(workflow_yaml, dict):
                        created = _discover_workflow_created_resources(
                            workflow_yaml, stage_name
                        )
                        resources.extend(created)
                    else:
                        warnings.append(
                            f"[{stage_name}] Workflow definition for "
                            f"'{dag_name}' is not a valid YAML dict"
                        )
                else:
                    warnings.append(
                        f"[{stage_name}] No workflow definition returned for "
                        f"'{dag_name}' — cannot discover workflow-created resources"
                    )
            except Exception as e:
                warnings.append(
                    f"[{stage_name}] Could not get workflow definition for "
                    f"'{dag_name}': {e}"
                )

    # --- S3 targets ---
    if dc:
        try:
            s3_targets = _resolve_s3_targets(stage_config, connections)
            for target in s3_targets:
                resources.append(ResourceToDelete(
                    resource_type="s3_prefix",
                    resource_id=f"s3://{target.bucket}/{target.prefix}",
                    stage=stage_name,
                    metadata={
                        "bucket": target.bucket, "prefix": target.prefix,
                        "connection_name": target.connection_name,
                    },
                ))
        except Exception as e:
            warnings.append(f"[{stage_name}] Could not resolve S3 targets: {e}")

    # --- Catalog resources ---
    if dc and dc.catalog is not None:
        catalog_config = dc.catalog if isinstance(dc.catalog, dict) else {}
        catalog_disabled = catalog_config.get("disable", False)
        if not catalog_disabled and project_id and domain_id:
            try:
                from ..helpers.catalog_import import (
                    _is_managed_resource, _search_target_resources,
                    _search_target_type_resources,
                )
                dz_client = boto3.client("datazone", region_name=effective_region)

                for item in _search_target_resources(dz_client, domain_id, project_id, "GLOSSARY"):
                    g = item.get("glossaryItem", {})
                    if g.get("id"):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_glossary", resource_id=g["id"],
                            stage=stage_name, metadata={"name": g.get("name", ""), "domain_id": domain_id},
                        ))

                for item in _search_target_resources(dz_client, domain_id, project_id, "GLOSSARY_TERM"):
                    t = item.get("glossaryTermItem", {})
                    if t.get("id"):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_glossary_term", resource_id=t["id"],
                            stage=stage_name, metadata={"name": t.get("name", ""), "domain_id": domain_id},
                        ))

                for item in _search_target_type_resources(dz_client, domain_id, project_id, "FORM_TYPE"):
                    ft = item.get("formTypeItem", {})
                    name = ft.get("name", "")
                    if name and not _is_managed_resource(name):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_form_type", resource_id=name,
                            stage=stage_name, metadata={"name": name, "domain_id": domain_id},
                        ))

                for item in _search_target_type_resources(dz_client, domain_id, project_id, "ASSET_TYPE"):
                    at = item.get("assetTypeItem", {})
                    name = at.get("name", "")
                    if name and not _is_managed_resource(name):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_asset_type", resource_id=name,
                            stage=stage_name, metadata={"name": name, "domain_id": domain_id},
                        ))

                for item in _search_target_resources(dz_client, domain_id, project_id, "ASSET"):
                    a = item.get("assetItem", {})
                    if a.get("identifier"):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_asset", resource_id=a["identifier"],
                            stage=stage_name, metadata={"name": a.get("name", ""), "domain_id": domain_id},
                        ))

                for item in _search_target_resources(dz_client, domain_id, project_id, "DATA_PRODUCT"):
                    dp = item.get("dataProductItem", {})
                    if dp.get("id"):
                        resources.append(ResourceToDelete(
                            resource_type="catalog_data_product", resource_id=dp["id"],
                            stage=stage_name, metadata={"name": dp.get("name", ""), "domain_id": domain_id},
                        ))

                if any(r.resource_type.startswith("catalog_") for r in resources):
                    warnings.append(
                        f"[{stage_name}] All project-owned catalog resources will be deleted, "
                        "including any created manually. "
                        "To skip catalog resource deletion, set `disable: true` under "
                        "`deployment_configuration.catalog` in your manifest."
                    )
            except Exception as e:
                warnings.append(f"[{stage_name}] Could not enumerate catalog resources: {e}")
        elif catalog_disabled:
            warnings.append(
                f"[{stage_name}] Catalog deletion is disabled (disable: true) — skipping."
            )

    # --- Bootstrap connections ---
    if not stage_config.project.create and stage_config.bootstrap:
        for action in stage_config.bootstrap.actions or []:
            if action.type != "datazone.create_connection":
                continue
            conn_name = action.parameters.get("name", "")
            if not conn_name:
                continue
            if conn_name.startswith("default."):
                warnings.append(
                    f"[{stage_name}] Skipping built-in connection '{conn_name}' "
                    "(default.* connections are never deleted by destroy)"
                )
                continue
            if conn_name in connections:
                conn_info = connections[conn_name]
                connection_id = conn_info.get("connectionId", "")
                if connection_id:
                    resources.append(ResourceToDelete(
                        resource_type="datazone_connection", resource_id=conn_name,
                        stage=stage_name,
                        metadata={"connection_id": connection_id, "domain_id": domain_id},
                    ))
                else:
                    warnings.append(
                        f"[{stage_name}] Connection '{conn_name}' found but has no ID — skipping"
                    )
            else:
                warnings.append(
                    f"[{stage_name}] Bootstrap connection '{conn_name}' not found in project "
                    "— already deleted or never created"
                )

    return ValidationResult(
        errors=errors, warnings=warnings, resources=resources,
        active_workflow_runs=active_workflow_runs,
    )

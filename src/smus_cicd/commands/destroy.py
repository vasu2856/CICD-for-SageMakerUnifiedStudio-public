"""Destroy command for SMUS CI/CD CLI.

Implements the inverse of deploy: reads a manifest, discovers all deployed
resources for the targeted stage(s), validates for collisions, then deletes
everything in a safe dependency order.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import boto3
import typer
import yaml
from botocore.exceptions import ClientError
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.prompt import Confirm

from ..application import ApplicationManifest
from ..helpers.airflow_serverless import (
    delete_workflow,
    generate_workflow_name,
    is_workflow_run_active,
    list_workflow_runs,
    list_workflows,
    stop_workflow_run,
)
from ..helpers.connections import get_project_connections
from ..helpers.datazone import (
    delete_project,
    get_domain_from_target_config,
    get_project_id_by_name,
)
from ..helpers.logger import get_logger
from ..helpers.operator_registry import OPERATOR_REGISTRY, ResourceNotFoundError
from ..helpers.quicksight import (
    QuickSightDeploymentError,
    list_dashboards,
    list_data_sources,
    list_datasets,
)
from ..helpers import s3 as s3_helper

logger = get_logger("destroy")
console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ResourceToDelete:
    """A single resource that will be deleted during the destroy phase."""

    resource_type: str  # "quicksight_dashboard" | "quicksight_dataset" |
    # "quicksight_data_source" | "airflow_workflow" |
    # "glue_job" | "s3_prefix" | "datazone_project" | "skipped"
    resource_id: str
    stage: str
    metadata: dict = field(default_factory=dict)


@dataclass
class S3Target:
    """An S3 prefix to delete, resolved from a deployment_configuration entry."""

    bucket: str
    prefix: str
    connection_name: str


@dataclass
class ValidationResult:
    """Outcome of the validation phase for a single stage."""

    errors: List[str]
    warnings: List[str]
    resources: List[ResourceToDelete]
    active_workflow_runs: Dict[str, List[str]]  # workflow_name -> [run_ids]


@dataclass
class ResourceResult:
    """Outcome of a single resource deletion attempt."""

    resource_type: str
    resource_id: str
    status: str  # "deleted" | "not_found" | "error" | "skipped"
    message: str


# ---------------------------------------------------------------------------
# Pure helper functions (no AWS calls)
# ---------------------------------------------------------------------------


def _resolve_resource_prefix(stage_name: str, qs_config: dict) -> str:
    """
    Resolve the QuickSight resource prefix for a stage.

    Reads overrideParameters.ResourceIdOverrideConfiguration.PrefixForAllResources
    and replaces {stage.name} with stage_name.

    Args:
        stage_name: The stage key (e.g. "dev", "test")
        qs_config: The deployment_configuration.quicksight dict

    Returns:
        Resolved prefix string (may be empty)
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

    Args:
        workflow_yaml: Parsed workflow YAML dict
        stage_name: Stage key for tagging resources

    Returns:
        List of ResourceToDelete entries
    """
    resources: List[ResourceToDelete] = []

    # Workflow YAML structure: {workflow_key: {tasks: {task_name: {...}}}}
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
                # Operator not in registry — skip
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

            # Extract resource name from the designated field
            resource_name_field = registry_entry["resource_name_field"]
            resource_name = task.get(resource_name_field, "")

            if "{" in str(resource_name):
                # Template variable — cannot resolve statically
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

            # Determine resource_type from registry entry
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

    Args:
        stage_config: StageConfig object
        connections: Dict of connection_name -> connection_info from get_project_connections

    Returns:
        Deduplicated list of S3Target objects
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
            # Extract bucket from s3://bucket/prefix
            parts = s3_uri.replace("s3://", "").split("/", 1)
            bucket = parts[0]

        # Base prefix from connection s3Uri (everything after bucket/)
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
                S3Target(
                    bucket=bucket,
                    prefix=full_prefix,
                    connection_name=conn_name,
                )
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
                S3Target(
                    bucket=bucket,
                    prefix=full_prefix,
                    connection_name=conn_name,
                )
            )

    # Deduplicate: remove targets whose prefix is a subdirectory of another target
    # (i.e. keep only the parent when one prefix starts with another)
    deduplicated: List[S3Target] = []
    for i, candidate in enumerate(raw_targets):
        is_subdir = False
        for j, other in enumerate(raw_targets):
            if i == j:
                continue
            if candidate.bucket != other.bucket:
                continue
            # candidate is a subdirectory of other if candidate.prefix starts with other.prefix/
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


def _parse_workflow_yaml_from_s3(bucket: str, key: str, region: str) -> dict:
    """
    Download and parse a workflow YAML file from S3.

    Returns empty dict on any error (logs warning).

    Args:
        bucket: S3 bucket name
        key: S3 object key
        region: AWS region

    Returns:
        Parsed YAML dict, or {} on error
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        return yaml.safe_load(content) or {}
    except Exception as e:
        logger.warning(
            "Could not fetch/parse workflow YAML from s3://%s/%s: %s", bucket, key, e
        )
        return {}


def _find_workflow_yaml_by_dag_id(
    bucket: str, prefix: str, dag_id: str, region: str
) -> dict:
    """
    Scan all YAML files under an S3 prefix and return the one whose dag_id matches.

    The workflow filename (e.g. covid_etl_workflow.yaml) is not the same as the
    workflowName / dag_id (e.g. covid_dashboard_glue_quick_pipeline), so we must
    scan and inspect each file rather than guessing the filename.

    Args:
        bucket: S3 bucket name
        prefix: S3 prefix to scan (e.g. "shared/dashboard-glue-quick/bundle/workflows/")
        dag_id: The dag_id to match (from manifest content.workflows[].workflowName)
        region: AWS region

    Returns:
        Parsed YAML dict of the matching workflow, or {} if not found
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith((".yaml", ".yml")):
                    continue
                try:
                    response = s3_client.get_object(Bucket=bucket, Key=key)
                    content = yaml.safe_load(response["Body"].read().decode("utf-8"))
                    if not isinstance(content, dict):
                        continue
                    # Match on top-level key == dag_id OR dag_id field inside the workflow
                    for wf_key, wf_body in content.items():
                        if wf_key == dag_id or (
                            isinstance(wf_body, dict)
                            and wf_body.get("dag_id") == dag_id
                        ):
                            logger.info(
                                "Found workflow YAML for dag_id '%s' at s3://%s/%s",
                                dag_id,
                                bucket,
                                key,
                            )
                            return content
                except Exception as e:
                    logger.warning("Could not read s3://%s/%s: %s", bucket, key, e)
                    continue
    except Exception as e:
        logger.warning(
            "Could not scan s3://%s/%s for workflow YAML: %s", bucket, prefix, e
        )
    return {}


def _validate_stage(
    stage_name: str, stage_config, manifest, region: str
) -> ValidationResult:
    """
    Perform read-only discovery for one stage and return a ValidationResult.

    Collects ALL errors and warnings without aborting early.

    Args:
        stage_name: Stage key (e.g. "dev")
        stage_config: StageConfig object
        manifest: ApplicationManifest object
        region: AWS region override (uses domain.region if not provided)

    Returns:
        ValidationResult with errors, warnings, resources, active_workflow_runs
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
            errors=errors,
            warnings=warnings,
            resources=resources,
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
                project_id=project_id,
                domain_id=domain_id,
                region=effective_region,
            )
        except Exception as e:
            warnings.append(f"[{stage_name}] Could not resolve S3 connections: {e}")

    # --- QuickSight resources ---
    dc = stage_config.deployment_configuration
    if dc and dc.quicksight:
        qs_config = dc.quicksight
        prefix = _resolve_resource_prefix(stage_name, qs_config)

        # Get AWS account ID for QuickSight calls
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
                    d
                    for d in all_dashboards
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
                        resources.append(
                            ResourceToDelete(
                                resource_type="quicksight_dashboard",
                                resource_id=d["DashboardId"],
                                stage=stage_name,
                                metadata={"name": d.get("Name", "")},
                            )
                        )
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
                        resources.append(
                            ResourceToDelete(
                                resource_type="quicksight_dataset",
                                resource_id=d["DataSetId"],
                                stage=stage_name,
                                metadata={"name": d.get("Name", "")},
                            )
                        )
            except QuickSightDeploymentError as e:
                errors.append(f"[{stage_name}] QuickSight dataset list failed: {e}")

            # Data sources
            try:
                all_sources = list_data_sources(account_id, effective_region)
                matched_sources = [
                    d
                    for d in all_sources
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
                        resources.append(
                            ResourceToDelete(
                                resource_type="quicksight_data_source",
                                resource_id=d["DataSourceId"],
                                stage=stage_name,
                                metadata={"name": d.get("Name", "")},
                            )
                        )
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

        # Find matching workflows by name
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
            resources.append(
                ResourceToDelete(
                    resource_type="airflow_workflow",
                    resource_id=workflow_arn,
                    stage=stage_name,
                    metadata={"workflow_name": workflow_name},
                )
            )

            # Check for active runs
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

        # Fetch and parse workflow YAML from S3 to discover created resources.
        # We scan all YAML files under the workflows prefix and match by dag_id,
        # since the filename (e.g. covid_etl_workflow.yaml) is not the same as
        # the workflowName (e.g. covid_dashboard_glue_quick_pipeline).
        if dc and connections:
            workflows_storage = None
            for entry in dc.storage or []:
                if entry.name == "workflows":
                    workflows_storage = entry
                    break

            if workflows_storage:
                conn_name = workflows_storage.connectionName
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

                target_dir = (workflows_storage.targetDirectory or "").strip("/")
                if base_prefix:
                    search_prefix = (
                        f"{base_prefix}/{target_dir}/"
                        if target_dir
                        else f"{base_prefix}/"
                    )
                else:
                    search_prefix = f"{target_dir}/" if target_dir else ""

                if bucket:
                    # Scan all YAML files under the prefix and match by dag_id
                    workflow_yaml = _find_workflow_yaml_by_dag_id(
                        bucket, search_prefix, dag_name, effective_region
                    )
                    if workflow_yaml:
                        created = _discover_workflow_created_resources(
                            workflow_yaml, stage_name
                        )
                        resources.extend(created)
                    else:
                        warnings.append(
                            f"[{stage_name}] Workflow YAML with dag_id '{dag_name}' "
                            f"not found under s3://{bucket}/{search_prefix}"
                        )
            else:
                warnings.append(
                    f"[{stage_name}] No 'workflows' storage entry found in "
                    "deployment_configuration — cannot discover workflow-created resources"
                )

    # --- S3 targets ---
    if dc:
        try:
            s3_targets = _resolve_s3_targets(stage_config, connections)
            for target in s3_targets:
                resources.append(
                    ResourceToDelete(
                        resource_type="s3_prefix",
                        resource_id=f"s3://{target.bucket}/{target.prefix}",
                        stage=stage_name,
                        metadata={
                            "bucket": target.bucket,
                            "prefix": target.prefix,
                            "connection_name": target.connection_name,
                        },
                    )
                )
        except Exception as e:
            warnings.append(f"[{stage_name}] Could not resolve S3 targets: {e}")

    if dc and dc.catalog is not None:
        catalog_config = dc.catalog if isinstance(dc.catalog, dict) else {}
        catalog_disabled = catalog_config.get("disable", False)
        if not catalog_disabled and project_id and domain_id:
            # Enumerate all project-owned catalog resources
            try:
                from ..helpers.catalog_import import (
                    _is_managed_resource,
                    _search_target_resources,
                    _search_target_type_resources,
                )

                dz_client = boto3.client("datazone", region_name=effective_region)

                # Glossaries
                for item in _search_target_resources(
                    dz_client, domain_id, project_id, "GLOSSARY"
                ):
                    g = item.get("glossaryItem", {})
                    if g.get("id"):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_glossary",
                                resource_id=g["id"],
                                stage=stage_name,
                                metadata={
                                    "name": g.get("name", ""),
                                    "domain_id": domain_id,
                                },
                            )
                        )

                # Glossary Terms
                for item in _search_target_resources(
                    dz_client, domain_id, project_id, "GLOSSARY_TERM"
                ):
                    t = item.get("glossaryTermItem", {})
                    if t.get("id"):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_glossary_term",
                                resource_id=t["id"],
                                stage=stage_name,
                                metadata={
                                    "name": t.get("name", ""),
                                    "domain_id": domain_id,
                                },
                            )
                        )

                # Form Types (custom only)
                for item in _search_target_type_resources(
                    dz_client, domain_id, project_id, "FORM_TYPE"
                ):
                    ft = item.get("formTypeItem", {})
                    name = ft.get("name", "")
                    if name and not _is_managed_resource(name):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_form_type",
                                resource_id=name,
                                stage=stage_name,
                                metadata={"name": name, "domain_id": domain_id},
                            )
                        )

                # Asset Types (custom only)
                for item in _search_target_type_resources(
                    dz_client, domain_id, project_id, "ASSET_TYPE"
                ):
                    at = item.get("assetTypeItem", {})
                    name = at.get("name", "")
                    if name and not _is_managed_resource(name):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_asset_type",
                                resource_id=name,
                                stage=stage_name,
                                metadata={"name": name, "domain_id": domain_id},
                            )
                        )

                # Assets
                for item in _search_target_resources(
                    dz_client, domain_id, project_id, "ASSET"
                ):
                    a = item.get("assetItem", {})
                    if a.get("identifier"):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_asset",
                                resource_id=a["identifier"],
                                stage=stage_name,
                                metadata={
                                    "name": a.get("name", ""),
                                    "domain_id": domain_id,
                                },
                            )
                        )

                # Data Products
                for item in _search_target_resources(
                    dz_client, domain_id, project_id, "DATA_PRODUCT"
                ):
                    dp = item.get("dataProductItem", {})
                    if dp.get("id"):
                        resources.append(
                            ResourceToDelete(
                                resource_type="catalog_data_product",
                                resource_id=dp["id"],
                                stage=stage_name,
                                metadata={
                                    "name": dp.get("name", ""),
                                    "domain_id": domain_id,
                                },
                            )
                        )

                if any(r.resource_type.startswith("catalog_") for r in resources):
                    warnings.append(
                        f"[{stage_name}] All project-owned catalog resources will be deleted, "
                        "including any created manually. "
                        "To skip catalog resource deletion, set `disable: true` under "
                        "`deployment_configuration.catalog` in your manifest."
                    )

            except Exception as e:
                warnings.append(
                    f"[{stage_name}] Could not enumerate catalog resources: {e}"
                )
        elif catalog_disabled:
            warnings.append(
                f"[{stage_name}] Catalog deletion is disabled (disable: true) — skipping."
            )

    # --- Bootstrap connections ---
    # Only discover if project is NOT being deleted (project deletion cascades to connections)
    if not stage_config.project.create and stage_config.bootstrap:
        for action in stage_config.bootstrap.actions or []:
            if action.type != "datazone.create_connection":
                continue
            conn_name = action.parameters.get("name", "")
            if not conn_name:
                continue
            # Never touch built-in default.* connections
            if conn_name.startswith("default."):
                warnings.append(
                    f"[{stage_name}] Skipping built-in connection '{conn_name}' "
                    "(default.* connections are never deleted by destroy)"
                )
                continue
            # Check if connection exists in the project
            if conn_name in connections:
                conn_info = connections[conn_name]
                connection_id = conn_info.get("connectionId", "")
                if connection_id:
                    resources.append(
                        ResourceToDelete(
                            resource_type="datazone_connection",
                            resource_id=conn_name,
                            stage=stage_name,
                            metadata={
                                "connection_id": connection_id,
                                "domain_id": domain_id,
                            },
                        )
                    )
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
        errors=errors,
        warnings=warnings,
        resources=resources,
        active_workflow_runs=active_workflow_runs,
    )


# ---------------------------------------------------------------------------
# Destruction phase
# ---------------------------------------------------------------------------


def _get_active_workflow_runs(workflow_arn: str, region: str) -> List[str]:
    """
    Re-query live workflow run status and return IDs of currently active runs.

    Args:
        workflow_arn: Workflow ARN
        region: AWS region

    Returns:
        List of active run IDs
    """
    runs = list_workflow_runs(workflow_arn, region=region)
    return [r["run_id"] for r in runs if is_workflow_run_active(r)]


def _destroy_stage(
    stage_name: str,
    stage_config,
    manifest,
    validation_result: ValidationResult,
    region: str,
    output: str,
) -> List[ResourceResult]:
    """
    Execute deletion for one stage in the required dependency order.

    Order:
      a) Stop active workflow runs
      b) Delete workflow-created resources (e.g. Glue jobs)
      c) Delete Airflow workflows
      d) Delete QuickSight (dashboards → datasets → data sources)
      e) Delete S3 objects at declared prefixes
      f) Delete DataZone project (only if project.create=True)

    Args:
        stage_name: Stage key
        stage_config: StageConfig object
        manifest: ApplicationManifest object
        validation_result: ValidationResult from _validate_stage
        region: AWS region
        output: Output format ("TEXT" or "JSON")

    Returns:
        List of ResourceResult objects
    """
    results: List[ResourceResult] = []
    effective_region = region or stage_config.domain.region
    is_json = output.upper() == "JSON"

    def _log(msg: str) -> None:
        if is_json:
            err_console.print(msg)
        else:
            console.print(msg)

    # Track which workflow ARNs should be skipped for deletion
    # (because stop_workflow_run failed)
    skip_delete_workflows: set = set()

    # -----------------------------------------------------------------------
    # Step a: Re-query and stop active workflow runs
    # -----------------------------------------------------------------------
    for workflow_name, _run_ids in validation_result.active_workflow_runs.items():
        # Find the workflow ARN from resources
        workflow_arn = None
        for r in validation_result.resources:
            if (
                r.resource_type == "airflow_workflow"
                and r.metadata.get("workflow_name") == workflow_name
            ):
                workflow_arn = r.resource_id
                break

        if not workflow_arn:
            continue

        try:
            live_run_ids = _get_active_workflow_runs(workflow_arn, effective_region)
        except Exception as e:
            _log(
                f"[yellow]⚠️  Could not re-query runs for workflow "
                f"'{workflow_name}': {e}[/yellow]"
            )
            live_run_ids = []

        for run_id in live_run_ids:
            try:
                stop_workflow_run(
                    workflow_arn=workflow_arn,
                    run_id=run_id,
                    region=effective_region,
                )
                _log(f"  ✅ Stopped workflow run {run_id} for '{workflow_name}'")
                results.append(
                    ResourceResult(
                        resource_type="workflow_run",
                        resource_id=run_id,
                        status="deleted",
                        message=f"Stopped run for workflow '{workflow_name}'",
                    )
                )
            except Exception as e:
                _log(
                    f"[red]  ❌ Failed to stop run {run_id} for "
                    f"'{workflow_name}': {e}[/red]"
                )
                results.append(
                    ResourceResult(
                        resource_type="workflow_run",
                        resource_id=run_id,
                        status="error",
                        message=str(e),
                    )
                )
                skip_delete_workflows.add(workflow_arn)

    # -----------------------------------------------------------------------
    # Step b: Delete workflow-created resources (e.g. Glue jobs)
    # -----------------------------------------------------------------------
    # Derive the set of resource types handled by the registry dynamically
    _registry_resource_types = {
        entry["resource_type"] for entry in OPERATOR_REGISTRY.values()
    }
    # Build a reverse map: resource_type → registry entry for fast lookup
    _resource_type_to_registry = {
        entry["resource_type"]: entry for entry in OPERATOR_REGISTRY.values()
    }

    for resource in validation_result.resources:
        if resource.resource_type not in _registry_resource_types:
            continue

        # Look up registry entry by operator key first, then fall back to resource_type
        operator_key = resource.metadata.get("operator", "")
        registry_entry = OPERATOR_REGISTRY.get(operator_key)
        if not registry_entry:
            registry_entry = _resource_type_to_registry.get(resource.resource_type)

        if not registry_entry:
            results.append(
                ResourceResult(
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    status="skipped",
                    message="No registry entry found",
                )
            )
            continue

        try:
            registry_entry["delete_fn"](resource.resource_id, effective_region)
            _log(f"  ✅ Deleted {resource.resource_type}: {resource.resource_id}")
            results.append(
                ResourceResult(
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    status="deleted",
                    message="Deleted successfully",
                )
            )
        except ResourceNotFoundError:
            _log(
                f"  [yellow]⚠️  {resource.resource_type} not found: "
                f"{resource.resource_id}[/yellow]"
            )
            results.append(
                ResourceResult(
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    status="not_found",
                    message="Resource not found",
                )
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "EntityNotFoundException":
                _log(
                    f"  [yellow]⚠️  {resource.resource_type} not found: "
                    f"{resource.resource_id}[/yellow]"
                )
                results.append(
                    ResourceResult(
                        resource_type=resource.resource_type,
                        resource_id=resource.resource_id,
                        status="not_found",
                        message="Resource not found",
                    )
                )
            else:
                _log(
                    f"  [red]❌ Error deleting {resource.resource_type} "
                    f"{resource.resource_id}: {e}[/red]"
                )
                results.append(
                    ResourceResult(
                        resource_type=resource.resource_type,
                        resource_id=resource.resource_id,
                        status="error",
                        message=str(e),
                    )
                )
        except Exception as e:
            _log(
                f"  [red]❌ Error deleting {resource.resource_type} "
                f"{resource.resource_id}: {e}[/red]"
            )
            results.append(
                ResourceResult(
                    resource_type=resource.resource_type,
                    resource_id=resource.resource_id,
                    status="error",
                    message=str(e),
                )
            )

    # -----------------------------------------------------------------------
    # Step c: Delete Airflow workflows
    # -----------------------------------------------------------------------
    for resource in validation_result.resources:
        if resource.resource_type != "airflow_workflow":
            continue

        workflow_arn = resource.resource_id
        if workflow_arn in skip_delete_workflows:
            _log(
                f"  [yellow]⚠️  Skipping workflow deletion (stop failed): "
                f"{workflow_arn}[/yellow]"
            )
            results.append(
                ResourceResult(
                    resource_type="airflow_workflow",
                    resource_id=workflow_arn,
                    status="error",
                    message="Skipped: stop_workflow_run failed for one or more runs",
                )
            )
            continue

        try:
            delete_workflow(workflow_arn, region=effective_region)
            _log(f"  ✅ Deleted Airflow workflow: {workflow_arn}")
            results.append(
                ResourceResult(
                    resource_type="airflow_workflow",
                    resource_id=workflow_arn,
                    status="deleted",
                    message="Deleted successfully",
                )
            )
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "resourcenotfound" in err_str:
                _log(
                    f"  [yellow]⚠️  Airflow workflow not found: {workflow_arn}[/yellow]"
                )
                results.append(
                    ResourceResult(
                        resource_type="airflow_workflow",
                        resource_id=workflow_arn,
                        status="not_found",
                        message="Workflow not found",
                    )
                )
            else:
                _log(
                    f"  [red]❌ Error deleting Airflow workflow {workflow_arn}: "
                    f"{e}[/red]"
                )
                results.append(
                    ResourceResult(
                        resource_type="airflow_workflow",
                        resource_id=workflow_arn,
                        status="error",
                        message=str(e),
                    )
                )

    # -----------------------------------------------------------------------
    # Step d: Delete Bootstrap_Connections
    # -----------------------------------------------------------------------
    for resource in validation_result.resources:
        if resource.resource_type != "datazone_connection":
            continue

        conn_name = resource.resource_id
        connection_id = resource.metadata.get("connection_id", "")
        domain_id = resource.metadata.get("domain_id", "")

        if not connection_id or not domain_id:
            _log(
                f"  [yellow]⚠️  Skipping connection '{conn_name}' — missing ID or domain[/yellow]"
            )
            results.append(
                ResourceResult(
                    resource_type="datazone_connection",
                    resource_id=conn_name,
                    status="skipped",
                    message="Missing connection ID or domain ID",
                )
            )
            continue

        try:
            dz_client = boto3.client("datazone", region_name=effective_region)
            dz_client.delete_connection(
                domainIdentifier=domain_id,
                identifier=connection_id,
            )
            _log(f"  ✅ Deleted DataZone connection: {conn_name} ({connection_id})")
            results.append(
                ResourceResult(
                    resource_type="datazone_connection",
                    resource_id=conn_name,
                    status="deleted",
                    message="Deleted successfully",
                )
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("ResourceNotFoundException", "EntityNotFoundException"):
                _log(f"  [yellow]⚠️  Connection not found: {conn_name}[/yellow]")
                results.append(
                    ResourceResult(
                        resource_type="datazone_connection",
                        resource_id=conn_name,
                        status="not_found",
                        message="Connection not found",
                    )
                )
            else:
                _log(f"  [red]❌ Error deleting connection '{conn_name}': {e}[/red]")
                results.append(
                    ResourceResult(
                        resource_type="datazone_connection",
                        resource_id=conn_name,
                        status="error",
                        message=str(e),
                    )
                )
        except Exception as e:
            _log(f"  [red]❌ Error deleting connection '{conn_name}': {e}[/red]")
            results.append(
                ResourceResult(
                    resource_type="datazone_connection",
                    resource_id=conn_name,
                    status="error",
                    message=str(e),
                )
            )

    # -----------------------------------------------------------------------
    # Step e: Delete QuickSight (dashboards → datasets → data sources)
    # -----------------------------------------------------------------------
    effective_region_qs = effective_region
    try:
        account_id = boto3.client(
            "sts", region_name=effective_region_qs
        ).get_caller_identity()["Account"]
    except Exception:
        account_id = None

    qs_client = boto3.client("quicksight", region_name=effective_region_qs)

    for qs_type in (
        "quicksight_dashboard",
        "quicksight_dataset",
        "quicksight_data_source",
    ):
        for resource in validation_result.resources:
            if resource.resource_type != qs_type:
                continue

            resource_id = resource.resource_id
            try:
                if qs_type == "quicksight_dashboard":
                    qs_client.delete_dashboard(
                        AwsAccountId=account_id, DashboardId=resource_id
                    )
                elif qs_type == "quicksight_dataset":
                    qs_client.delete_data_set(
                        AwsAccountId=account_id, DataSetId=resource_id
                    )
                elif qs_type == "quicksight_data_source":
                    qs_client.delete_data_source(
                        AwsAccountId=account_id, DataSourceId=resource_id
                    )

                _log(f"  ✅ Deleted {qs_type}: {resource_id}")
                results.append(
                    ResourceResult(
                        resource_type=qs_type,
                        resource_id=resource_id,
                        status="deleted",
                        message="Deleted successfully",
                    )
                )
            except ClientError as e:
                code = e.response["Error"]["Code"]
                if code == "ResourceNotFoundException":
                    _log(f"  [yellow]⚠️  {qs_type} not found: {resource_id}[/yellow]")
                    results.append(
                        ResourceResult(
                            resource_type=qs_type,
                            resource_id=resource_id,
                            status="not_found",
                            message="Resource not found",
                        )
                    )
                else:
                    _log(f"  [red]❌ Error deleting {qs_type} {resource_id}: {e}[/red]")
                    results.append(
                        ResourceResult(
                            resource_type=qs_type,
                            resource_id=resource_id,
                            status="error",
                            message=str(e),
                        )
                    )
            except Exception as e:
                _log(f"  [red]❌ Error deleting {qs_type} {resource_id}: {e}[/red]")
                results.append(
                    ResourceResult(
                        resource_type=qs_type,
                        resource_id=resource_id,
                        status="error",
                        message=str(e),
                    )
                )

    # -----------------------------------------------------------------------
    # Step f: Delete S3 objects (using s3 helper)
    # -----------------------------------------------------------------------
    for resource in validation_result.resources:
        if resource.resource_type != "s3_prefix":
            continue

        bucket = resource.metadata.get("bucket", "")
        prefix = resource.metadata.get("prefix", "")

        if not bucket:
            continue

        try:
            # Use existing s3 helper for list + delete
            object_keys = [
                obj["Key"]
                for obj in s3_helper.list_objects(
                    bucket, prefix, region=effective_region
                )
            ]

            if not object_keys:
                _log(f"  [yellow]⚠️  S3 prefix empty: s3://{bucket}/{prefix}[/yellow]")
                results.append(
                    ResourceResult(
                        resource_type="s3_prefix",
                        resource_id=resource.resource_id,
                        status="not_found",
                        message="S3 prefix is empty or does not exist",
                    )
                )
                continue

            s3_helper.delete_objects(bucket, object_keys, region=effective_region)
            _log(
                f"  ✅ Deleted {len(object_keys)} objects from "
                f"s3://{bucket}/{prefix}"
            )
            results.append(
                ResourceResult(
                    resource_type="s3_prefix",
                    resource_id=resource.resource_id,
                    status="deleted",
                    message=f"Deleted {len(object_keys)} objects",
                )
            )
        except Exception as e:
            _log(
                f"  [red]❌ Error deleting S3 prefix s3://{bucket}/{prefix}: "
                f"{e}[/red]"
            )
            results.append(
                ResourceResult(
                    resource_type="s3_prefix",
                    resource_id=resource.resource_id,
                    status="error",
                    message=str(e),
                )
            )

    # -----------------------------------------------------------------------
    # Step g: Delete catalog resources (reverse dependency order)
    # -----------------------------------------------------------------------
    # Deletion order: data products → assets → asset types → form types →
    #                 glossary terms → glossaries
    CATALOG_DELETION_ORDER = [
        "catalog_data_product",
        "catalog_asset",
        "catalog_asset_type",
        "catalog_form_type",
        "catalog_glossary_term",
        "catalog_glossary",
    ]
    CATALOG_DELETE_API = {
        "catalog_data_product": lambda dz, domain_id, rid: dz.delete_data_product(
            domainIdentifier=domain_id, identifier=rid
        ),
        "catalog_asset": lambda dz, domain_id, rid: dz.delete_asset(
            domainIdentifier=domain_id, identifier=rid
        ),
        "catalog_asset_type": lambda dz, domain_id, rid: dz.delete_asset_type(
            domainIdentifier=domain_id, identifier=rid
        ),
        "catalog_form_type": lambda dz, domain_id, rid: dz.delete_form_type(
            domainIdentifier=domain_id, formTypeIdentifier=rid
        ),
        "catalog_glossary_term": lambda dz, domain_id, rid: dz.delete_glossary_term(
            domainIdentifier=domain_id, identifier=rid
        ),
        "catalog_glossary": lambda dz, domain_id, rid: dz.delete_glossary(
            domainIdentifier=domain_id, identifier=rid
        ),
    }

    for catalog_type in CATALOG_DELETION_ORDER:
        for resource in validation_result.resources:
            if resource.resource_type != catalog_type:
                continue
            resource_id = resource.resource_id
            domain_id_for_catalog = resource.metadata.get("domain_id", "")
            resource_name = resource.metadata.get("name", resource_id)
            if not domain_id_for_catalog:
                _log(
                    f"  [yellow]⚠️  Skipping {catalog_type} '{resource_name}' — missing domain ID[/yellow]"
                )
                results.append(
                    ResourceResult(
                        resource_type=catalog_type,
                        resource_id=resource_id,
                        status="skipped",
                        message="Missing domain ID",
                    )
                )
                continue
            try:
                dz_client = boto3.client("datazone", region_name=effective_region)
                CATALOG_DELETE_API[catalog_type](
                    dz_client, domain_id_for_catalog, resource_id
                )
                _log(f"  ✅ Deleted {catalog_type}: {resource_name} ({resource_id})")
                results.append(
                    ResourceResult(
                        resource_type=catalog_type,
                        resource_id=resource_id,
                        status="deleted",
                        message="Deleted successfully",
                    )
                )
            except ClientError as e:
                code = e.response["Error"]["Code"]
                if code in ("ResourceNotFoundException", "EntityNotFoundException"):
                    _log(
                        f"  [yellow]⚠️  {catalog_type} not found: {resource_name}[/yellow]"
                    )
                    results.append(
                        ResourceResult(
                            resource_type=catalog_type,
                            resource_id=resource_id,
                            status="not_found",
                            message="Resource not found",
                        )
                    )
                else:
                    _log(
                        f"  [red]❌ Error deleting {catalog_type} '{resource_name}': {e}[/red]"
                    )
                    results.append(
                        ResourceResult(
                            resource_type=catalog_type,
                            resource_id=resource_id,
                            status="error",
                            message=str(e),
                        )
                    )
            except Exception as e:
                _log(
                    f"  [red]❌ Error deleting {catalog_type} '{resource_name}': {e}[/red]"
                )
                results.append(
                    ResourceResult(
                        resource_type=catalog_type,
                        resource_id=resource_id,
                        status="error",
                        message=str(e),
                    )
                )

    # -----------------------------------------------------------------------
    # Step h: Delete DataZone project (only if project.create=True)
    # -----------------------------------------------------------------------
    if stage_config.project.create is True:
        try:
            domain_id, domain_name = get_domain_from_target_config(
                stage_config, region=effective_region
            )
            project_id = get_project_id_by_name(
                stage_config.project.name, domain_id, effective_region
            )

            if not project_id:
                _log(
                    f"  [yellow]⚠️  DataZone project not found: "
                    f"'{stage_config.project.name}'[/yellow]"
                )
                results.append(
                    ResourceResult(
                        resource_type="datazone_project",
                        resource_id=stage_config.project.name,
                        status="not_found",
                        message="Project not found",
                    )
                )
            else:
                delete_project(domain_name, project_id, effective_region)
                _log(f"  ✅ Deleted DataZone project: {stage_config.project.name}")
                results.append(
                    ResourceResult(
                        resource_type="datazone_project",
                        resource_id=stage_config.project.name,
                        status="deleted",
                        message="Deleted successfully",
                    )
                )
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "resourcenotfound" in err_str:
                _log(
                    f"  [yellow]⚠️  DataZone project not found: "
                    f"'{stage_config.project.name}'[/yellow]"
                )
                results.append(
                    ResourceResult(
                        resource_type="datazone_project",
                        resource_id=stage_config.project.name,
                        status="not_found",
                        message="Project not found",
                    )
                )
            else:
                _log(
                    f"  [red]❌ Error deleting DataZone project "
                    f"'{stage_config.project.name}': {e}[/red]"
                )
                results.append(
                    ResourceResult(
                        resource_type="datazone_project",
                        resource_id=stage_config.project.name,
                        status="error",
                        message=str(e),
                    )
                )

    # Handle skipped resources from validation
    for resource in validation_result.resources:
        if resource.resource_type == "skipped":
            reason = resource.metadata.get("reason", "")
            _log(f"  [dim]⏭️  Skipped task '{resource.resource_id}': {reason}[/dim]")
            results.append(
                ResourceResult(
                    resource_type="skipped",
                    resource_id=resource.resource_id,
                    status="skipped",
                    message=reason,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------


def destroy_command(
    manifest: str = "manifest.yaml",
    targets: Optional[str] = None,
    force: bool = False,
    output: str = "TEXT",
) -> None:
    """
    Destroy all resources deployed by the manifest.

    Runs a full validation cycle across all targeted stages before any
    destructive action. Prints a destruction plan and prompts for confirmation
    unless --force is set.

    Example: aws-smus-cicd-cli destroy --manifest manifest.yaml --targets dev --force
    """
    is_json = output.upper() == "JSON"

    def _out(msg: str) -> None:
        """Print to stdout (TEXT) or stderr (JSON)."""
        if is_json:
            err_console.print(msg)
        else:
            console.print(msg)

    # -----------------------------------------------------------------------
    # 1. Parse manifest
    # -----------------------------------------------------------------------
    try:
        app_manifest = ApplicationManifest.from_file(manifest)
    except Exception as e:
        if is_json:
            err_console.print(f"[red]Error parsing manifest '{manifest}': {e}[/red]")
        else:
            console.print(f"[red]Error parsing manifest '{manifest}': {e}[/red]")
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 2. Resolve target list
    # -----------------------------------------------------------------------
    if targets:
        target_list = [t.strip() for t in targets.split(",")]
    else:
        target_list = list(app_manifest.stages.keys())

    invalid = [t for t in target_list if t not in app_manifest.stages]
    if invalid:
        valid_names = ", ".join(app_manifest.stages.keys())
        msg = (
            f"[red]Invalid stage name(s): {', '.join(invalid)}. "
            f"Valid stages: {valid_names}[/red]"
        )
        if is_json:
            err_console.print(msg)
        else:
            console.print(msg)
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 3. Skip stages with absent/empty deployment_configuration
    # -----------------------------------------------------------------------
    active_targets: List[str] = []
    for stage_name in target_list:
        sc = app_manifest.stages[stage_name]
        if not sc.deployment_configuration:
            _out(
                f"[yellow]⚠️  Stage '{stage_name}' has no deployment_configuration "
                "— skipping[/yellow]"
            )
            continue
        active_targets.append(stage_name)

    if not active_targets:
        _out("[yellow]No stages with deployment_configuration to destroy.[/yellow]")
        raise typer.Exit(0)

    # -----------------------------------------------------------------------
    # 4. Validation phase — ALL stages before any destructive action
    # -----------------------------------------------------------------------
    _out(f"\n[blue]🔍 Validating {len(active_targets)} stage(s)...[/blue]")

    validation_results: Dict[str, ValidationResult] = {}
    for stage_name in active_targets:
        sc = app_manifest.stages[stage_name]
        region = sc.domain.region
        _out(f"  Validating stage '{stage_name}'...")
        try:
            vr = _validate_stage(stage_name, sc, app_manifest, region)
        except Exception as e:
            vr = ValidationResult(
                errors=[f"[{stage_name}] Unexpected validation error: {e}"],
                warnings=[],
                resources=[],
                active_workflow_runs={},
            )
        validation_results[stage_name] = vr

        for warning in vr.warnings:
            _out(f"  [yellow]⚠️  {_escape_markup(warning)}[/yellow]")

    # -----------------------------------------------------------------------
    # 5. Check for validation errors
    # -----------------------------------------------------------------------
    all_errors: List[str] = []
    for vr in validation_results.values():
        all_errors.extend(vr.errors)

    if all_errors:
        _out("\n[red]❌ Validation errors found — aborting before any deletion:[/red]")
        for err in all_errors:
            _out(f"  [red]• {_escape_markup(err)}[/red]")
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 6. Print destruction plan
    # -----------------------------------------------------------------------
    _out("\n[blue]📋 Destruction plan:[/blue]")
    total_resources = 0
    for stage_name in active_targets:
        vr = validation_results[stage_name]
        _out(f"\n  [bold]Stage: {stage_name}[/bold]")
        by_type: Dict[str, List[ResourceToDelete]] = {}
        for r in vr.resources:
            by_type.setdefault(r.resource_type, []).append(r)

        if not by_type:
            _out("    (no resources found)")
        else:
            for rtype, rlist in by_type.items():
                _out(f"    {rtype}:")
                for r in rlist:
                    _out(f"      - {r.resource_id}")
                    total_resources += 1

        if vr.active_workflow_runs:
            _out("    [yellow]Active workflow runs (will be force-stopped):[/yellow]")
            for wf_name, run_ids in vr.active_workflow_runs.items():
                _out(f"      {wf_name}: {run_ids}")

    _out(f"\n  Total resources to process: {total_resources}")

    # -----------------------------------------------------------------------
    # 7. Confirmation prompt (unless --force)
    # -----------------------------------------------------------------------
    has_active_runs = any(
        bool(vr.active_workflow_runs) for vr in validation_results.values()
    )

    if not force:
        if not is_json:
            console.print()
            if has_active_runs:
                console.print(
                    "[yellow]⚠️  Active workflow runs will be force-stopped "
                    "before deletion.[/yellow]"
                )
            console.print(
                "[yellow]⚠️  WARNING: This will permanently delete the above "
                "resources![/yellow]"
            )
            confirmed = Confirm.ask(
                "Are you sure you want to proceed with destruction?"
            )
            if not confirmed:
                console.print("Destruction cancelled.")
                raise typer.Exit(0)
        else:
            # JSON mode without --force: cannot prompt interactively
            err_console.print(
                "[yellow]Use --force to skip confirmation in JSON output mode.[/yellow]"
            )
            raise typer.Exit(0)

    # -----------------------------------------------------------------------
    # 8. Destruction phase
    # -----------------------------------------------------------------------
    _out("\n[blue]🗑️  Starting destruction...[/blue]")

    all_results: Dict[str, List[ResourceResult]] = {}
    for stage_name in active_targets:
        sc = app_manifest.stages[stage_name]
        region = sc.domain.region
        vr = validation_results[stage_name]

        _out(f"\n[blue]  Stage: {stage_name}[/blue]")
        try:
            stage_results = _destroy_stage(
                stage_name=stage_name,
                stage_config=sc,
                manifest=app_manifest,
                validation_result=vr,
                region=region,
                output=output,
            )
        except Exception as e:
            _out(
                f"  [red]❌ Unexpected error destroying stage '{stage_name}': {e}[/red]"
            )
            stage_results = [
                ResourceResult(
                    resource_type="stage",
                    resource_id=stage_name,
                    status="error",
                    message=str(e),
                )
            ]
        all_results[stage_name] = stage_results

    # -----------------------------------------------------------------------
    # 9. Summary
    # -----------------------------------------------------------------------
    has_errors = False

    if is_json:
        # Build JSON output
        stages_output = {}
        for stage_name, stage_results in all_results.items():
            stages_output[stage_name] = [
                {
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "status": r.status,
                    "message": r.message,
                }
                for r in stage_results
            ]
            if any(r.status == "error" for r in stage_results):
                has_errors = True

        output_data = {
            "application_name": app_manifest.application_name,
            "targets": active_targets,
            "stages": stages_output,
        }
        print(json.dumps(output_data, indent=2))
    else:
        console.print("\n[blue]📊 Destruction Summary[/blue]")
        for stage_name, stage_results in all_results.items():
            counts = {"deleted": 0, "not_found": 0, "skipped": 0, "error": 0}
            for r in stage_results:
                if r.status in counts:
                    counts[r.status] += 1
                if r.status == "error":
                    has_errors = True

            console.print(
                f"  {stage_name}: "
                f"deleted={counts['deleted']} "
                f"not_found={counts['not_found']} "
                f"skipped={counts['skipped']} "
                f"error={counts['error']}"
            )

    if has_errors:
        raise typer.Exit(1)

"""
DataZone catalog import functionality for SMUS CI/CD CLI.

This module provides functions to import catalog resources (Glossaries, GlossaryTerms,
FormTypes, AssetTypes, Assets, and Data Products) into a DataZone project, mapping
identifiers from source to target projects using externalIdentifier (with normalization)
or name as fallback. Supports deletion of resources missing from the bundle and
automatic publishing of assets and data products.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Required top-level keys in catalog export JSON (no metadataForms)
REQUIRED_TOP_LEVEL_KEYS = {
    "metadata",
    "glossaries",
    "glossaryTerms",
    "formTypes",
    "assetTypes",
    "assets",
    "dataProducts",
}

REQUIRED_METADATA_KEYS = {
    "sourceProjectId",
    "sourceDomainId",
    "exportTimestamp",
    "resourceTypes",
}

# Creation order: Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → DataProducts
CREATION_ORDER = [
    "glossaries",
    "glossaryTerms",
    "formTypes",
    "assetTypes",
    "assets",
    "dataProducts",
]

# Deletion order (reverse): DataProducts → Assets → AssetTypes → FormTypes → GlossaryTerms → Glossaries
DELETION_ORDER = list(reversed(CREATION_ORDER))

# Resource types that can be published
PUBLISHABLE_TYPES = {"assets", "dataProducts"}

# Patterns for normalizing externalIdentifier
_AWS_ACCOUNT_PATTERN = re.compile(r"\b\d{12}\b")
_AWS_REGION_PATTERN = re.compile(
    r"\b(us|eu|ap|sa|ca|me|af|il)-(north|south|east|west|central|northeast|southeast|northwest|southwest)-\d\b"
)
_ARN_PREFIX_PATTERN = re.compile(r"arn:aws[^:]*:[^:]*:[^:]*:\d{12}:")


def _get_datazone_client(region: str):
    """
    Create DataZone client with optional custom endpoint from environment.

    Args:
        region: AWS region for the client

    Returns:
        Configured boto3 DataZone client

    Environment Variables:
        DATAZONE_ENDPOINT_URL: Optional custom endpoint URL for testing
    """
    endpoint_url = os.environ.get("DATAZONE_ENDPOINT_URL")
    if endpoint_url:
        return boto3.client("datazone", region_name=region, endpoint_url=endpoint_url)
    return boto3.client("datazone", region_name=region)


def _validate_catalog_json(catalog_data: Dict[str, Any]) -> None:
    """
    Validate that catalog JSON has required structure.

    Args:
        catalog_data: Parsed catalog export JSON

    Raises:
        ValueError: If required keys are missing
    """
    missing_keys = REQUIRED_TOP_LEVEL_KEYS - set(catalog_data.keys())
    if missing_keys:
        raise ValueError(
            f"Catalog JSON missing required top-level keys: {missing_keys}"
        )

    metadata = catalog_data.get("metadata", {})
    missing_metadata = REQUIRED_METADATA_KEYS - set(metadata.keys())
    if missing_metadata:
        raise ValueError(
            f"Catalog JSON metadata missing required keys: {missing_metadata}"
        )


# DataZone policy grants required for full catalog import
_REQUIRED_POLICY_GRANTS = [
    "CREATE_GLOSSARY",
    "CREATE_FORM_TYPE",
    "CREATE_ASSET_TYPE",
]

# Mapping from policyType enum to the detail key expected by add_policy_grant
_POLICY_DETAIL_KEY = {
    "CREATE_GLOSSARY": "createGlossary",
    "CREATE_FORM_TYPE": "createFormType",
    "CREATE_ASSET_TYPE": "createAssetType",
}

# Prefix for managed/system form types that cannot be used in custom asset types
_MANAGED_FORM_TYPE_PREFIX = "amazon.datazone."


def _is_managed_resource(name: str) -> bool:
    """Return True if the resource name belongs to a managed/system type."""
    return name.startswith(_MANAGED_FORM_TYPE_PREFIX) if name else False


def _ensure_import_permissions(client, domain_id: str, project_id: str) -> List[str]:
    """
    Ensure the project's domain unit has the policy grants needed for catalog
    import.  Missing grants are created automatically via AddPolicyGrant.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier

    Returns:
        List of policy type names that could not be added. Empty list means
        all permissions are present.
    """
    # Resolve the project's domain unit — grants live on the domain unit,
    # not on the project itself.
    try:
        project = client.get_project(domainIdentifier=domain_id, identifier=project_id)
        domain_unit_id = project.get("domainUnitId")
    except Exception as e:
        logger.warning(
            "Could not resolve domain unit for project %s: %s", project_id, e
        )
        # Can't verify — let the import proceed and fail naturally
        return []

    if not domain_unit_id:
        logger.warning(
            "Project %s has no domainUnitId, skipping permission check", project_id
        )
        return []

    failed = []
    for policy_type in _REQUIRED_POLICY_GRANTS:
        # Check if grant already exists
        already_granted = False
        try:
            resp = client.list_policy_grants(
                domainIdentifier=domain_id,
                entityType="DOMAIN_UNIT",
                entityIdentifier=domain_unit_id,
                policyType=policy_type,
            )
            if resp.get("grantList"):
                already_granted = True
        except ClientError as e:
            if e.response["Error"]["Code"] != "AccessDeniedException":
                logger.warning("Error checking %s grant: %s", policy_type, e)
        except Exception as e:
            logger.warning("Error checking %s grant: %s", policy_type, e)

        if already_granted:
            continue

        # Grant is missing — warn and attempt to add it
        logger.warning(
            "Policy grant %s is missing on domain unit %s",
            policy_type, domain_unit_id,
        )
        logger.info(
            "Attempting to add %s grant for project %s...",
            policy_type, project_id,
        )
        try:
            client.add_policy_grant(
                domainIdentifier=domain_id,
                entityType="DOMAIN_UNIT",
                entityIdentifier=domain_unit_id,
                policyType=policy_type,
                principal={
                    "project": {
                        "projectDesignation": "OWNER",
                        "projectIdentifier": project_id,
                    }
                },
                detail={_POLICY_DETAIL_KEY[policy_type]: {}},
            )
            logger.info("Added %s policy grant for project %s", policy_type, project_id)
        except Exception as e:
            logger.error("Failed to add %s policy grant: %s", policy_type, e)
            failed.append(policy_type)

    return failed


def _normalize_external_identifier(external_id: str) -> str:
    """
    Normalize an externalIdentifier by removing AWS account ID and region information.

    Strips ARN prefixes (arn:aws:...<account>:<region>:), removes 12-digit account IDs,
    and removes AWS region strings like us-east-1.

    Args:
        external_id: Raw externalIdentifier string

    Returns:
        Normalized identifier with AWS-specific info removed
    """
    if not external_id:
        return external_id

    # Strip ARN prefix pattern
    normalized = _ARN_PREFIX_PATTERN.sub("", external_id)
    # Remove 12-digit account IDs
    normalized = _AWS_ACCOUNT_PATTERN.sub("", normalized)
    # Remove region strings
    normalized = _AWS_REGION_PATTERN.sub("", normalized)
    # Clean up any resulting double separators
    normalized = re.sub(r"[:/_-]{2,}", lambda m: m.group(0)[0], normalized)
    # Strip leading/trailing separators
    normalized = normalized.strip(":/_-")

    return normalized


def _search_target_resources(
    client, domain_id: str, project_id: str, search_scope: str
) -> List[Dict[str, Any]]:
    """Search target project for existing resources of a given type."""
    resources = []
    next_token = None

    search_params = {
        "domainIdentifier": domain_id,
        "searchScope": search_scope,
        "owningProjectIdentifier": project_id,
    }

    while True:
        if next_token:
            search_params["nextToken"] = next_token
        response = client.search(**search_params)
        resources.extend(response.get("items", []))
        next_token = response.get("nextToken")
        if not next_token:
            break

    return resources


def _search_target_type_resources(
    client, domain_id: str, project_id: str, search_scope: str
) -> List[Dict[str, Any]]:
    """Search target project for existing type resources (FormTypes, AssetTypes)."""
    resources = []
    next_token = None

    search_params = {
        "domainIdentifier": domain_id,
        "searchScope": search_scope,
        "managed": False,
    }

    while True:
        if next_token:
            search_params["nextToken"] = next_token
        response = client.search_types(**search_params)
        items = response.get("items", [])
        # Filter by owning project
        for item in items:
            if search_scope == "FORM_TYPE":
                type_item = item.get("formTypeItem", {})
            elif search_scope == "ASSET_TYPE":
                type_item = item.get("assetTypeItem", {})
            else:
                continue
            if type_item.get("owningProjectId") == project_id:
                resources.append(item)
        next_token = response.get("nextToken")
        if not next_token:
            break

    return resources


def _build_identifier_map(
    client,
    domain_id: str,
    project_id: str,
    catalog_data: Dict[str, Any],
) -> Dict[str, Dict[str, str]]:
    """
    Build mapping from source identifiers to target identifiers.

    Uses normalized externalIdentifier as primary key when present,
    falls back to name-based matching.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier
        catalog_data: Parsed catalog export JSON

    Returns:
        Dict mapping resource types to {source_id: target_id} mappings
    """
    id_map: Dict[str, Dict[str, str]] = {rt: {} for rt in CREATION_ORDER}

    # Helper to match by normalized externalIdentifier or name
    def _find_match(
        source_resource, target_items, item_key, id_field, has_external_id=False
    ):
        source_ext_id = source_resource.get("externalIdentifier")
        source_name = source_resource.get("name")

        for item in target_items:
            target_item = item.get(item_key, {})
            # Try externalIdentifier match first
            if source_ext_id and has_external_id:
                target_ext_id = target_item.get("externalIdentifier")
                if target_ext_id:
                    if _normalize_external_identifier(
                        source_ext_id
                    ) == _normalize_external_identifier(target_ext_id):
                        return target_item.get(id_field)
            # Fallback to name match
            if source_name and target_item.get("name") == source_name:
                return target_item.get(id_field)
        return None

    # Map glossaries by name (no externalIdentifier)
    try:
        target_glossaries = _search_target_resources(
            client, domain_id, project_id, "GLOSSARY"
        )
    except Exception as e:
        logger.warning(f"Failed to search target glossaries: {e}")
        target_glossaries = []

    for glossary in catalog_data.get("glossaries", []):
        source_id = glossary.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(glossary, target_glossaries, "glossaryItem", "id")
        if target_id:
            id_map["glossaries"][source_id] = target_id

    # Map glossary terms by name
    try:
        target_terms = _search_target_resources(
            client, domain_id, project_id, "GLOSSARY_TERM"
        )
    except Exception as e:
        logger.warning(f"Failed to search target glossary terms: {e}")
        target_terms = []

    for term in catalog_data.get("glossaryTerms", []):
        source_id = term.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(term, target_terms, "glossaryTermItem", "id")
        if target_id:
            id_map["glossaryTerms"][source_id] = target_id

    # Map form types by name
    try:
        target_form_types = _search_target_type_resources(
            client, domain_id, project_id, "FORM_TYPE"
        )
    except Exception as e:
        logger.warning(f"Failed to search target form types: {e}")
        target_form_types = []

    for form_type in catalog_data.get("formTypes", []):
        source_id = form_type.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(
            form_type, target_form_types, "formTypeItem", "revision"
        )
        if target_id:
            id_map["formTypes"][source_id] = target_id

    # Map asset types by name
    try:
        target_asset_types = _search_target_type_resources(
            client, domain_id, project_id, "ASSET_TYPE"
        )
    except Exception as e:
        logger.warning(f"Failed to search target asset types: {e}")
        target_asset_types = []

    for asset_type in catalog_data.get("assetTypes", []):
        source_id = asset_type.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(
            asset_type, target_asset_types, "assetTypeItem", "revision"
        )
        if target_id:
            id_map["assetTypes"][source_id] = target_id

    # Map assets by externalIdentifier (with normalization) or name
    try:
        target_assets = _search_target_resources(client, domain_id, project_id, "ASSET")
    except Exception as e:
        logger.warning(f"Failed to search target assets: {e}")
        target_assets = []

    for asset in catalog_data.get("assets", []):
        source_id = asset.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(
            asset, target_assets, "assetItem", "identifier", has_external_id=True
        )
        if target_id:
            id_map["assets"][source_id] = target_id

    # Map data products by name
    try:
        target_data_products = _search_target_resources(
            client, domain_id, project_id, "DATA_PRODUCT"
        )
    except Exception as e:
        logger.warning(f"Failed to search target data products: {e}")
        target_data_products = []

    for dp in catalog_data.get("dataProducts", []):
        source_id = dp.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(dp, target_data_products, "dataProductItem", "id")
        if target_id:
            id_map["dataProducts"][source_id] = target_id

    return id_map


def _resolve_cross_references(
    resource: Dict[str, Any],
    resource_type: str,
    id_map: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    """
    Replace source identifiers in cross-reference fields with target identifiers.

    Args:
        resource: Resource dict with source identifiers
        resource_type: Type of resource
        id_map: Mapping from source to target identifiers

    Returns:
        Resource dict with resolved cross-references
    """
    resolved = resource.copy()

    if resource_type == "glossaryTerms":
        # Resolve glossaryId reference
        source_glossary_id = resource.get("glossaryId")
        if source_glossary_id and source_glossary_id in id_map.get("glossaries", {}):
            resolved["glossaryId"] = id_map["glossaries"][source_glossary_id]

        # Resolve termRelations — each relation type maps to a list of term IDs
        term_relations = resource.get("termRelations")
        if term_relations and isinstance(term_relations, dict):
            resolved_relations: Dict[str, Any] = {}
            term_map = id_map.get("glossaryTerms", {})
            for relation_type, term_ids in term_relations.items():
                if isinstance(term_ids, list):
                    resolved_ids = [term_map.get(tid, tid) for tid in term_ids]
                    resolved_relations[relation_type] = resolved_ids
                else:
                    resolved_relations[relation_type] = term_ids
            resolved["termRelations"] = resolved_relations

    elif resource_type == "assets":
        # Resolve typeIdentifier reference
        source_type_id = resource.get("typeIdentifier")
        if source_type_id and source_type_id in id_map.get("assetTypes", {}):
            resolved["typeIdentifier"] = id_map["assetTypes"][source_type_id]

    elif resource_type == "dataProducts":
        # Resolve asset identifiers and glossary term IDs inside items
        items = resource.get("items")
        if items and isinstance(items, list):
            asset_map = id_map.get("assets", {})
            term_map = id_map.get("glossaryTerms", {})
            resolved_items = []
            for item in items:
                item_copy = dict(item)
                src_id = item_copy.get("identifier")
                if src_id and src_id in asset_map:
                    item_copy["identifier"] = asset_map[src_id]
                glossary_terms = item_copy.get("glossaryTerms")
                if glossary_terms and isinstance(glossary_terms, list):
                    item_copy["glossaryTerms"] = [
                        term_map.get(tid, tid) for tid in glossary_terms
                    ]
                resolved_items.append(item_copy)
            resolved["items"] = resolved_items

    return resolved


def _get_form_type_revision(
    client, domain_id: str, form_type_name: str
) -> Optional[str]:
    """Return the current revision of a form type in the target domain."""
    try:
        resp = client.get_form_type(
            domainIdentifier=domain_id,
            formTypeIdentifier=form_type_name,
        )
        return resp.get("revision")
    except Exception:
        return None


def _resolve_target_data_source(
    client,
    domain_id: str,
    project_id: str,
    source_ds_type: str,
    database_name: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Find a data source in the target project that matches the source type and
    covers the asset's database.

    Matching strategy (in priority order):
    1. Same type + Glue filter covers the asset's databaseName
    2. Same type + wildcard ("*") database filter (catch-all data source)
    3. Same type (fallback when no database_name provided or no filter match)

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier
        source_ds_type: Data source type from the source (e.g. GLUE, SAGEMAKER)
        database_name: Database name from the asset's GlueTableForm (optional)

    Returns:
        Dict with 'dataSourceId' and 'dataSourceRunId' if found, else None.
    """
    try:
        resp = client.list_data_sources(
            domainIdentifier=domain_id,
            projectIdentifier=project_id,
            maxResults=25,
        )
        candidates = [
            ds
            for ds in resp.get("items", [])
            if ds.get("type") == source_ds_type
            and ds.get("status") in ("READY", "RUNNING")
        ]

        if not candidates:
            return None

        def _get_latest_run_id(ds_id: str) -> Optional[str]:
            runs = client.list_data_source_runs(
                domainIdentifier=domain_id,
                dataSourceIdentifier=ds_id,
                maxResults=1,
            )
            for run in runs.get("items", []):
                if run.get("status") == "SUCCESS":
                    return run.get("id")
            return None

        def _build_result(ds_id: str) -> Dict[str, str]:
            return {
                "dataSourceId": ds_id,
                "dataSourceRunId": _get_latest_run_id(ds_id),
            }

        # If no database_name, just return the first candidate
        if not database_name:
            return _build_result(candidates[0]["dataSourceId"])

        # Score candidates by how well their filter config matches
        exact_match = None
        wildcard_match = None

        for ds in candidates:
            ds_id = ds["dataSourceId"]
            try:
                detail = client.get_data_source(
                    domainIdentifier=domain_id, identifier=ds_id
                )
            except Exception:
                continue

            config = detail.get("configuration", {})
            glue_config = config.get("glueRunConfiguration", {})
            filters = glue_config.get("relationalFilterConfigurations", [])

            for filt in filters:
                db_filter = filt.get("databaseName", "")
                if db_filter == database_name:
                    exact_match = ds_id
                    break
                if db_filter == "*":
                    wildcard_match = ds_id
            if exact_match:
                break

        matched_id = exact_match or wildcard_match or candidates[0]["dataSourceId"]
        return _build_result(matched_id)

    except Exception as e:
        logger.warning(
            f"Failed to resolve target data source (type={source_ds_type}): {e}"
        )
    return None


def _normalize_forms_input_for_api(
    forms_input,
    resource_type: str,
    client=None,
    domain_id: str = "",
    project_id: str = "",
):
    """
    Normalize formsInput fields for DataZone Create/Update APIs.

    The export captures formsOutput from Get* APIs which uses 'typeName',
    but the Create/Update APIs expect 'typeIdentifier' instead.

    Source-domain typeRevision values are remapped to the current revision
    in the target domain so the API can resolve the form type correctly.

    For asset formsInput (list of dicts): rename typeName → typeIdentifier
    For assetType formsInput (dict of dicts): rename typeName → typeIdentifier

    Args:
        forms_input: The formsInput value from the exported resource
        resource_type: Type of resource (assets, assetTypes)
        client: Optional DataZone boto3 client for revision lookup
        domain_id: Target domain identifier for revision lookup

    Returns:
        Normalized formsInput suitable for the Create/Update API
    """
    if not forms_input:
        return forms_input

    # Cache looked-up revisions to avoid repeated API calls
    revision_cache: Dict[str, Optional[str]] = {}

    def _resolve_revision(
        form_name: str, original_revision: Optional[str]
    ) -> Optional[str]:
        """Look up the target-domain revision for a form type."""
        if not client or not domain_id:
            return original_revision
        if form_name not in revision_cache:
            revision_cache[form_name] = _get_form_type_revision(
                client, domain_id, form_name
            )
        return revision_cache[form_name] or original_revision

    # Cache for resolved target data sources keyed by (type, databaseName)
    _ds_cache: Dict[str, Optional[Dict[str, str]]] = {}

    def _extract_database_name(all_forms: list) -> Optional[str]:
        """Extract databaseName from the asset's GlueTableForm if present."""
        for f in all_forms:
            type_id = f.get("typeIdentifier") or f.get("typeName", "")
            if "GlueTableFormType" in type_id:
                try:
                    content = json.loads(f.get("content", "{}"))
                    return content.get("databaseName")
                except (json.JSONDecodeError, KeyError):
                    pass
        return None

    if resource_type == "assets" and isinstance(forms_input, list):
        # Pre-extract database name for data source matching
        db_name = _extract_database_name(forms_input)

        normalized = []
        for form in forms_input:
            form_copy = dict(form)
            # Rename typeName → typeIdentifier if present
            if "typeName" in form_copy and "typeIdentifier" not in form_copy:
                form_copy["typeIdentifier"] = form_copy.pop("typeName")

            # Remap DataSourceReferenceForm to target domain's data source
            form_type = form_copy.get("typeIdentifier", "")
            if (
                form_type == "amazon.datazone.DataSourceReferenceFormType"
                and client
                and domain_id
                and project_id
            ):
                try:
                    content = json.loads(form_copy.get("content", "{}"))
                    source_ds_type = content.get("dataSourceType", "GLUE")
                    cache_key = f"{source_ds_type}:{db_name or '*'}"

                    if cache_key not in _ds_cache:
                        _ds_cache[cache_key] = _resolve_target_data_source(
                            client,
                            domain_id,
                            project_id,
                            source_ds_type,
                            database_name=db_name,
                        )
                    target_ds = _ds_cache[cache_key]

                    if target_ds:
                        content["dataSourceIdentifier"] = {
                            "id": target_ds["dataSourceId"],
                            "version": "latest",
                        }
                        content["filterableDataSourceId"] = target_ds["dataSourceId"]
                        if target_ds.get("dataSourceRunId"):
                            content["dataSourceRunId"] = target_ds["dataSourceRunId"]
                        form_copy["content"] = json.dumps(content)
                        logger.info(
                            f"Remapped DataSourceReferenceForm to target data source "
                            f"{target_ds['dataSourceId']} (db={db_name})"
                        )
                    else:
                        logger.warning(
                            f"No matching {source_ds_type} data source in target project "
                            f"(db={db_name}), stripping DataSourceReferenceForm"
                        )
                        continue
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        f"Failed to remap DataSourceReferenceForm, stripping: {e}"
                    )
                    continue

            # Remap typeRevision to the target domain's current revision
            form_id = form_copy.get("typeIdentifier", "")
            if "typeRevision" in form_copy:
                resolved = _resolve_revision(form_id, form_copy["typeRevision"])
                if resolved:
                    form_copy["typeRevision"] = resolved
            normalized.append(form_copy)
        return normalized

    if resource_type == "assetTypes" and isinstance(forms_input, dict):
        normalized = {}
        for form_name, form_config in forms_input.items():
            config_copy = dict(form_config)
            if "typeName" in config_copy and "typeIdentifier" not in config_copy:
                config_copy["typeIdentifier"] = config_copy.pop("typeName")
            # Remap typeRevision to the target domain's current revision
            form_id = config_copy.get("typeIdentifier", form_name)
            if "typeRevision" in config_copy:
                resolved = _resolve_revision(form_id, config_copy["typeRevision"])
                if resolved:
                    config_copy["typeRevision"] = resolved
            normalized[form_name] = config_copy
        return normalized

    return forms_input


def _import_resource(
    client,
    domain_id: str,
    project_id: str,
    resource: Dict[str, Any],
    resource_type: str,
    id_map: Dict[str, Dict[str, str]],
) -> Tuple[bool, bool]:
    """
    Create or update a single resource in the target project.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier
        resource: Resource to import
        resource_type: Type of resource
        id_map: Identifier mapping

    Returns:
        Tuple of (success, is_update)
    """
    source_id = resource.get("sourceId")
    name = resource.get("name")

    if not source_id or not name:
        logger.error(f"Resource missing sourceId or name: {resource}")
        return False, False

    # Check if resource already exists in target
    existing_id = id_map.get(resource_type, {}).get(source_id)
    is_update = existing_id is not None

    # Resolve cross-references
    resolved = _resolve_cross_references(resource, resource_type, id_map)

    try:
        if resource_type == "glossaries":
            if is_update:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "identifier": existing_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("status"):
                    kwargs["status"] = resolved["status"]
                client.update_glossary(**kwargs)
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("status"):
                    kwargs["status"] = resolved["status"]
                response = client.create_glossary(**kwargs)
                id_map["glossaries"][source_id] = response.get("id")

        elif resource_type == "glossaryTerms":
            if is_update:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "identifier": existing_id,
                    "name": resolved.get("name"),
                    "glossaryIdentifier": resolved.get("glossaryId"),
                }
                if resolved.get("shortDescription"):
                    kwargs["shortDescription"] = resolved["shortDescription"]
                if resolved.get("longDescription"):
                    kwargs["longDescription"] = resolved["longDescription"]
                if resolved.get("status"):
                    kwargs["status"] = resolved["status"]
                if resolved.get("termRelations"):
                    kwargs["termRelations"] = resolved["termRelations"]
                client.update_glossary_term(**kwargs)
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "glossaryIdentifier": resolved.get("glossaryId"),
                    "name": resolved.get("name"),
                }
                if resolved.get("shortDescription"):
                    kwargs["shortDescription"] = resolved["shortDescription"]
                if resolved.get("longDescription"):
                    kwargs["longDescription"] = resolved["longDescription"]
                if resolved.get("status"):
                    kwargs["status"] = resolved["status"]
                # Skip termRelations during initial creation — other terms
                # may not exist yet.  A second pass in import_catalog will
                # update them once all terms have been created and mapped.
                response = client.create_glossary_term(**kwargs)
                id_map["glossaryTerms"][source_id] = response.get("id")

        elif resource_type == "formTypes":
            # Skip managed/system form types — they already exist in every domain
            if _is_managed_resource(name):
                logger.info(f"Skipping managed FormType {name}")
                return True, False
            if is_update:
                logger.info(f"FormType {name} already exists, skipping (no update API)")
                return True, True
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                    "status": "ENABLED",
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("model"):
                    kwargs["model"] = resolved["model"]
                response = client.create_form_type(**kwargs)
                id_map["formTypes"][source_id] = response.get("revision")

        elif resource_type == "assetTypes":
            # Skip managed/system asset types — they already exist in every domain
            if _is_managed_resource(name):
                logger.info(f"Skipping managed AssetType {name}")
                return True, False
            if is_update:
                logger.info(
                    f"AssetType {name} already exists, skipping (no update API)"
                )
                return True, True
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("formsInput"):
                    normalized = _normalize_forms_input_for_api(
                        resolved["formsInput"],
                        "assetTypes",
                        client=client,
                        domain_id=domain_id,
                    )
                    # Filter out managed/system forms that cannot be used
                    # in custom asset type creation
                    if isinstance(normalized, dict):
                        normalized = {
                            k: v
                            for k, v in normalized.items()
                            if not (
                                v.get("typeIdentifier", "").startswith(
                                    _MANAGED_FORM_TYPE_PREFIX
                                )
                                or v.get("typeName", "").startswith(
                                    _MANAGED_FORM_TYPE_PREFIX
                                )
                            )
                        }
                    if normalized:
                        kwargs["formsInput"] = normalized
                response = client.create_asset_type(**kwargs)
                id_map["assetTypes"][source_id] = response.get("revision")

        elif resource_type == "assets":
            # Normalize formsInput: typeName → typeIdentifier for API compatibility
            normalized_forms = None
            if resolved.get("formsInput"):
                normalized_forms = _normalize_forms_input_for_api(
                    resolved["formsInput"],
                    "assets",
                    client=client,
                    domain_id=domain_id,
                    project_id=project_id,
                )
            if is_update:
                # For asset revisions, merge exported forms with existing
                # managed forms from the target asset.  The API requires
                # all required forms (e.g. GlueTableForm) to be present.
                existing_forms = []
                try:
                    existing_asset = client.get_asset(
                        domainIdentifier=domain_id,
                        identifier=existing_id,
                    )
                    for form in existing_asset.get("formsOutput", []):
                        existing_forms.append(
                            {
                                "formName": form.get("formName"),
                                "typeIdentifier": form.get("typeName"),
                                "typeRevision": form.get("typeRevision"),
                                "content": form.get("content"),
                            }
                        )
                except Exception:
                    pass

                # Build a set of form names we already have from the export
                export_form_names = set()
                if normalized_forms:
                    for f in normalized_forms:
                        export_form_names.add(
                            f.get("formName") or f.get("typeIdentifier", "")
                        )

                # Merge: keep existing managed forms that aren't in the export
                merged = list(normalized_forms) if normalized_forms else []
                for ef in existing_forms:
                    if ef.get("formName") not in export_form_names:
                        merged.append(ef)

                kwargs = {
                    "domainIdentifier": domain_id,
                    "identifier": existing_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if merged:
                    kwargs["formsInput"] = merged
                # DataZone has no update_asset; use create_asset_revision instead
                client.create_asset_revision(**kwargs)
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("typeIdentifier"):
                    kwargs["typeIdentifier"] = resolved["typeIdentifier"]
                if normalized_forms:
                    kwargs["formsInput"] = normalized_forms
                if resolved.get("externalIdentifier"):
                    kwargs["externalIdentifier"] = resolved["externalIdentifier"]
                response = client.create_asset(**kwargs)
                id_map["assets"][source_id] = response.get("id")

        elif resource_type == "dataProducts":
            if is_update:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "identifier": existing_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("items") is not None:
                    kwargs["items"] = resolved["items"]
                # DataZone has no update_data_product; use create_data_product_revision
                client.create_data_product_revision(**kwargs)
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("items") is not None:
                    kwargs["items"] = resolved["items"]
                response = client.create_data_product(**kwargs)
                id_map["dataProducts"][source_id] = response.get("id")

        return True, is_update

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            logger.info(
                f"Resource {name} already exists (ConflictException), treating as update"
            )
            return True, True
        else:
            logger.error(f"Failed to import {resource_type} {name}: {e}")
            return False, False
    except Exception as e:
        logger.error(f"Failed to import {resource_type} {name}: {e}")
        return False, False


def _identify_resources_to_delete(
    client,
    domain_id: str,
    project_id: str,
    catalog_data: Dict[str, Any],
) -> Dict[str, List[Dict[str, str]]]:
    """
    Find resources in target project that are not present in the bundle.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier
        catalog_data: Parsed catalog export JSON

    Returns:
        Dict mapping resource types to lists of {id, name} dicts to delete
    """
    to_delete: Dict[str, List[Dict[str, str]]] = {rt: [] for rt in DELETION_ORDER}

    # Build sets of names from bundle for each resource type
    bundle_names = {}
    for rt in CREATION_ORDER:
        bundle_names[rt] = {
            r.get("name") for r in catalog_data.get(rt, []) if r.get("name")
        }

    # Check glossaries
    try:
        target_glossaries = _search_target_resources(
            client, domain_id, project_id, "GLOSSARY"
        )
        for item in target_glossaries:
            g = item.get("glossaryItem", {})
            if g.get("name") and g["name"] not in bundle_names["glossaries"]:
                to_delete["glossaries"].append({"id": g.get("id"), "name": g["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target glossaries for deletion: {e}")

    # Check glossary terms
    try:
        target_terms = _search_target_resources(
            client, domain_id, project_id, "GLOSSARY_TERM"
        )
        for item in target_terms:
            t = item.get("glossaryTermItem", {})
            if t.get("name") and t["name"] not in bundle_names["glossaryTerms"]:
                to_delete["glossaryTerms"].append(
                    {"id": t.get("id"), "name": t["name"]}
                )
    except Exception as e:
        logger.warning(f"Failed to search target glossary terms for deletion: {e}")

    # Check form types
    try:
        target_form_types = _search_target_type_resources(
            client, domain_id, project_id, "FORM_TYPE"
        )
        for item in target_form_types:
            ft = item.get("formTypeItem", {})
            if ft.get("name") and ft["name"] not in bundle_names["formTypes"]:
                to_delete["formTypes"].append(
                    {"id": ft.get("revision"), "name": ft["name"]}
                )
    except Exception as e:
        logger.warning(f"Failed to search target form types for deletion: {e}")

    # Check asset types
    try:
        target_asset_types = _search_target_type_resources(
            client, domain_id, project_id, "ASSET_TYPE"
        )
        for item in target_asset_types:
            at = item.get("assetTypeItem", {})
            if at.get("name") and at["name"] not in bundle_names["assetTypes"]:
                to_delete["assetTypes"].append(
                    {"id": at.get("revision"), "name": at["name"]}
                )
    except Exception as e:
        logger.warning(f"Failed to search target asset types for deletion: {e}")

    # Check assets
    try:
        target_assets = _search_target_resources(client, domain_id, project_id, "ASSET")
        for item in target_assets:
            a = item.get("assetItem", {})
            if a.get("name") and a["name"] not in bundle_names["assets"]:
                to_delete["assets"].append(
                    {"id": a.get("identifier"), "name": a["name"]}
                )
    except Exception as e:
        logger.warning(f"Failed to search target assets for deletion: {e}")

    # Check data products
    try:
        target_dps = _search_target_resources(
            client, domain_id, project_id, "DATA_PRODUCT"
        )
        for item in target_dps:
            dp = item.get("dataProductItem", {})
            if dp.get("name") and dp["name"] not in bundle_names["dataProducts"]:
                to_delete["dataProducts"].append(
                    {"id": dp.get("id"), "name": dp["name"]}
                )
    except Exception as e:
        logger.warning(f"Failed to search target data products for deletion: {e}")

    return to_delete


def _delete_resource(
    client,
    domain_id: str,
    project_id: str,
    resource_id: str,
    resource_type: str,
) -> bool:
    """
    Delete a resource from the target project.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        project_id: Target project identifier
        resource_id: Resource identifier to delete
        resource_type: Type of resource

    Returns:
        True if deletion succeeded, False otherwise
    """
    try:
        if resource_type == "glossaries":
            client.delete_glossary(domainIdentifier=domain_id, identifier=resource_id)
        elif resource_type == "glossaryTerms":
            client.delete_glossary_term(
                domainIdentifier=domain_id, identifier=resource_id
            )
        elif resource_type == "formTypes":
            client.delete_form_type(
                domainIdentifier=domain_id, formTypeIdentifier=resource_id
            )
        elif resource_type == "assetTypes":
            client.delete_asset_type(
                domainIdentifier=domain_id, assetTypeIdentifier=resource_id
            )
        elif resource_type == "assets":
            client.delete_asset(domainIdentifier=domain_id, identifier=resource_id)
        elif resource_type == "dataProducts":
            client.delete_data_product(
                domainIdentifier=domain_id, identifier=resource_id
            )
        return True
    except Exception as e:
        logger.error(f"Failed to delete {resource_type} {resource_id}: {e}")
        return False


def _publish_resource(
    client,
    domain_id: str,
    resource_id: str,
    resource_type: str,
    max_wait_seconds: int = 30,
    poll_interval: float = 2.0,
) -> bool:
    """
    Publish an asset or data product and verify the listing becomes ACTIVE.

    The create_listing_change_set API is asynchronous — it returns success even
    if the listing ultimately fails (e.g. missing Glue table). This function
    polls the resource after the publish call to verify the listing status.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        resource_id: Resource identifier to publish
        resource_type: Type of resource (assets or dataProducts)
        max_wait_seconds: Maximum seconds to wait for listing to become ACTIVE
        poll_interval: Seconds between polling attempts

    Returns:
        True if listing status is ACTIVE, False otherwise
    """
    if resource_type not in PUBLISHABLE_TYPES:
        return False

    try:
        if resource_type == "assets":
            entity_type = "ASSET"
        elif resource_type == "dataProducts":
            entity_type = "DATA_PRODUCT"
        else:
            return False

        client.create_listing_change_set(
            domainIdentifier=domain_id,
            entityIdentifier=resource_id,
            entityType=entity_type,
            action="PUBLISH",
        )
    except Exception as e:
        logger.error(f"Failed to publish {resource_type} {resource_id}: {e}")
        return False

    # Poll to verify listing status
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        time.sleep(poll_interval)
        elapsed += poll_interval
        try:
            if resource_type == "assets":
                resp = client.get_asset(
                    domainIdentifier=domain_id,
                    identifier=resource_id,
                )
            else:
                resp = client.get_data_product(
                    domainIdentifier=domain_id,
                    identifier=resource_id,
                )

            listing = resp.get("listing", {})
            listing_status = listing.get("listingStatus") or listing.get("status")

            if listing_status == "ACTIVE":
                logger.info(
                    f"Listing verified ACTIVE for {resource_type} {resource_id}"
                )
                return True
            elif listing_status == "FAILED":
                logger.error(f"Listing FAILED for {resource_type} {resource_id}")
                return False
            # Still CREATING / PENDING — keep polling
        except Exception as e:
            logger.warning(
                f"Error polling listing status for {resource_type} {resource_id}: {e}"
            )

    logger.error(
        f"Listing verification timed out after {max_wait_seconds}s "
        f"for {resource_type} {resource_id}"
    )
    return False


def import_catalog(
    domain_id: str,
    project_id: str,
    catalog_data: Dict[str, Any],
    region: str,
    skip_publish: bool = False,
) -> Dict[str, int]:
    """
    Import catalog resources into a target DataZone project.

    Orchestrates: validate → map → create in dependency order → delete in reverse
    order → optionally publish → return summary.

    Publishing behavior: By default, assets and data products are published only
    if they were published (listingStatus == "ACTIVE") in the source project.
    Set skip_publish=True to skip all publishing regardless of source state.

    Args:
        domain_id: Target domain identifier
        project_id: Target project identifier
        catalog_data: Parsed catalog export JSON
        region: AWS region
        skip_publish: When True, skip all publishing regardless of source state

    Returns:
        Dict with counts: {"created": N, "updated": N, "deleted": N, "failed": N, "published": N}
    """
    # Validate JSON structure
    _validate_catalog_json(catalog_data)

    # Initialize client
    client = _get_datazone_client(region)

    # Pre-flight permission check: ensure the project's domain unit has the
    # required policy grants (CREATE_GLOSSARY, CREATE_FORM_TYPE, CREATE_ASSET_TYPE).
    # Missing grants are added automatically. Short-circuit only if grants
    # could not be added.
    failed_grants = _ensure_import_permissions(client, domain_id, project_id)
    if failed_grants:
        failed_str = ", ".join(failed_grants)
        raise PermissionError(
            f"Catalog import aborted — could not add required policy grants: "
            f"{failed_str}. Add these grants manually in the DataZone console "
            f"under the domain unit's policy grants before retrying."
        )

    # Build identifier mapping
    id_map = _build_identifier_map(client, domain_id, project_id, catalog_data)

    # Initialize counters
    created = 0
    updated = 0
    deleted = 0
    failed = 0
    published = 0

    # Track successfully imported resource IDs for publishing
    imported_resource_ids: Dict[str, List[str]] = {rt: [] for rt in PUBLISHABLE_TYPES}

    # Create/update in dependency order
    for resource_type in CREATION_ORDER:
        for resource in catalog_data.get(resource_type, []):
            success, is_update = _import_resource(
                client, domain_id, project_id, resource, resource_type, id_map
            )
            if success:
                if is_update:
                    updated += 1
                else:
                    created += 1
                # Track for publishing only if source was published (ACTIVE)
                if resource_type in PUBLISHABLE_TYPES:
                    source_id = resource.get("sourceId")
                    target_id = id_map.get(resource_type, {}).get(source_id)
                    listing_status = resource.get("listingStatus")
                    if target_id and listing_status == "ACTIVE":
                        imported_resource_ids[resource_type].append(target_id)
            else:
                failed += 1

    # Second pass: update glossary terms with termRelations now that all
    # terms have been created and their IDs are in id_map.
    for term in catalog_data.get("glossaryTerms", []):
        term_relations = term.get("termRelations")
        if not term_relations or not any(term_relations.values()):
            continue
        source_id = term.get("sourceId")
        target_id = id_map.get("glossaryTerms", {}).get(source_id)
        if not target_id:
            continue
        # Resolve term relation IDs from source → target
        resolved_relations: Dict[str, Any] = {}
        term_map = id_map.get("glossaryTerms", {})
        for relation_type, term_ids in term_relations.items():
            if isinstance(term_ids, list):
                resolved_relations[relation_type] = [
                    term_map.get(tid, tid) for tid in term_ids
                ]
            else:
                resolved_relations[relation_type] = term_ids
        # Resolve glossaryId
        glossary_id = term.get("glossaryId")
        target_glossary_id = id_map.get("glossaries", {}).get(glossary_id, glossary_id)
        try:
            client.update_glossary_term(
                domainIdentifier=domain_id,
                identifier=target_id,
                glossaryIdentifier=target_glossary_id,
                name=term.get("name"),
                termRelations=resolved_relations,
            )
        except Exception as e:
            logger.warning(
                "Failed to update termRelations for %s: %s", term.get("name"), e
            )

    # Identify and delete resources not in bundle (reverse dependency order)
    to_delete = _identify_resources_to_delete(
        client, domain_id, project_id, catalog_data
    )
    for resource_type in DELETION_ORDER:
        for resource_info in to_delete.get(resource_type, []):
            resource_id = resource_info.get("id")
            if resource_id:
                if _delete_resource(
                    client, domain_id, project_id, resource_id, resource_type
                ):
                    deleted += 1
                else:
                    failed += 1

    # Publish assets and data products unless skip_publish is set
    if not skip_publish:
        for resource_type in PUBLISHABLE_TYPES:
            for resource_id in imported_resource_ids[resource_type]:
                if _publish_resource(client, domain_id, resource_id, resource_type):
                    published += 1
                else:
                    failed += 1

    logger.info(
        f"Catalog import complete: {created} created, {updated} updated, "
        f"{deleted} deleted, {failed} failed, {published} published"
    )

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "failed": failed,
        "published": published,
    }

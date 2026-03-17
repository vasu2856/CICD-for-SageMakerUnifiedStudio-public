"""
DataZone catalog import functionality for SMUS CI/CD CLI.

This module provides functions to import catalog resources (Glossaries, GlossaryTerms,
FormTypes, AssetTypes, Assets, and Data Products) into a DataZone project, mapping
identifiers from source to target projects using externalIdentifier (with normalization)
or name as fallback. Supports deletion of resources missing from the bundle and
automatic publishing of assets and data products.
"""

import logging
import os
import re
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
_AWS_ACCOUNT_PATTERN = re.compile(r'\b\d{12}\b')
_AWS_REGION_PATTERN = re.compile(
    r'\b(us|eu|ap|sa|ca|me|af|il)-(north|south|east|west|central|northeast|southeast|northwest|southwest)-\d\b'
)
_ARN_PREFIX_PATTERN = re.compile(r'arn:aws[^:]*:[^:]*:[^:]*:\d{12}:')


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
    normalized = _ARN_PREFIX_PATTERN.sub('', external_id)
    # Remove 12-digit account IDs
    normalized = _AWS_ACCOUNT_PATTERN.sub('', normalized)
    # Remove region strings
    normalized = _AWS_REGION_PATTERN.sub('', normalized)
    # Clean up any resulting double separators
    normalized = re.sub(r'[:/_-]{2,}', lambda m: m.group(0)[0], normalized)
    # Strip leading/trailing separators
    normalized = normalized.strip(':/_-')

    return normalized


def _search_target_resources(client, domain_id: str, project_id: str, search_scope: str) -> List[Dict[str, Any]]:
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


def _search_target_type_resources(client, domain_id: str, project_id: str, search_scope: str) -> List[Dict[str, Any]]:
    """Search target project for existing type resources (FormTypes, AssetTypes)."""
    resources = []
    next_token = None

    search_params = {
        "domainIdentifier": domain_id,
        "searchScope": search_scope,
        "managed": False,
        "owningProjectIdentifier": project_id,
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
    id_map = {rt: {} for rt in CREATION_ORDER}

    # Helper to match by normalized externalIdentifier or name
    def _find_match(source_resource, target_items, item_key, id_field, has_external_id=False):
        source_ext_id = source_resource.get("externalIdentifier")
        source_name = source_resource.get("name")

        for item in target_items:
            target_item = item.get(item_key, {})
            # Try externalIdentifier match first
            if source_ext_id and has_external_id:
                target_ext_id = target_item.get("externalIdentifier")
                if target_ext_id:
                    if _normalize_external_identifier(source_ext_id) == _normalize_external_identifier(target_ext_id):
                        return target_item.get(id_field)
            # Fallback to name match
            if source_name and target_item.get("name") == source_name:
                return target_item.get(id_field)
        return None

    # Map glossaries by name (no externalIdentifier)
    try:
        target_glossaries = _search_target_resources(client, domain_id, project_id, "GLOSSARY")
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
        target_terms = _search_target_resources(client, domain_id, project_id, "GLOSSARY_TERM")
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
        target_form_types = _search_target_type_resources(client, domain_id, project_id, "FORM_TYPE")
    except Exception as e:
        logger.warning(f"Failed to search target form types: {e}")
        target_form_types = []

    for form_type in catalog_data.get("formTypes", []):
        source_id = form_type.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(form_type, target_form_types, "formTypeItem", "revision")
        if target_id:
            id_map["formTypes"][source_id] = target_id

    # Map asset types by name
    try:
        target_asset_types = _search_target_type_resources(client, domain_id, project_id, "ASSET_TYPE")
    except Exception as e:
        logger.warning(f"Failed to search target asset types: {e}")
        target_asset_types = []

    for asset_type in catalog_data.get("assetTypes", []):
        source_id = asset_type.get("sourceId")
        if not source_id:
            continue
        target_id = _find_match(asset_type, target_asset_types, "assetTypeItem", "revision")
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
        target_id = _find_match(asset, target_assets, "assetItem", "identifier", has_external_id=True)
        if target_id:
            id_map["assets"][source_id] = target_id

    # Map data products by name
    try:
        target_data_products = _search_target_resources(client, domain_id, project_id, "DATA_PRODUCT")
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

    elif resource_type == "assets":
        # Resolve typeIdentifier reference
        source_type_id = resource.get("typeIdentifier")
        if source_type_id and source_type_id in id_map.get("assetTypes", {}):
            resolved["typeIdentifier"] = id_map["assetTypes"][source_type_id]

    return resolved


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
                if resolved.get("termRelations"):
                    kwargs["termRelations"] = resolved["termRelations"]
                response = client.create_glossary_term(**kwargs)
                id_map["glossaryTerms"][source_id] = response.get("id")

        elif resource_type == "formTypes":
            if is_update:
                logger.info(f"FormType {name} already exists, skipping (no update API)")
                return True, True
            else:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "owningProjectIdentifier": project_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("model"):
                    kwargs["model"] = resolved["model"]
                response = client.create_form_type(**kwargs)
                id_map["formTypes"][source_id] = response.get("revision")

        elif resource_type == "assetTypes":
            if is_update:
                logger.info(f"AssetType {name} already exists, skipping (no update API)")
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
                    kwargs["formsInput"] = resolved["formsInput"]
                response = client.create_asset_type(**kwargs)
                id_map["assetTypes"][source_id] = response.get("revision")

        elif resource_type == "assets":
            if is_update:
                kwargs = {
                    "domainIdentifier": domain_id,
                    "identifier": existing_id,
                    "name": resolved.get("name"),
                }
                if resolved.get("description"):
                    kwargs["description"] = resolved["description"]
                if resolved.get("formsInput"):
                    kwargs["formsInput"] = resolved["formsInput"]
                client.update_asset(**kwargs)
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
                if resolved.get("formsInput"):
                    kwargs["formsInput"] = resolved["formsInput"]
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
                client.update_data_product(**kwargs)
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
            logger.info(f"Resource {name} already exists (ConflictException), treating as update")
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
    to_delete = {rt: [] for rt in DELETION_ORDER}

    # Build sets of names from bundle for each resource type
    bundle_names = {}
    for rt in CREATION_ORDER:
        bundle_names[rt] = {r.get("name") for r in catalog_data.get(rt, []) if r.get("name")}

    # Check glossaries
    try:
        target_glossaries = _search_target_resources(client, domain_id, project_id, "GLOSSARY")
        for item in target_glossaries:
            g = item.get("glossaryItem", {})
            if g.get("name") and g["name"] not in bundle_names["glossaries"]:
                to_delete["glossaries"].append({"id": g.get("id"), "name": g["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target glossaries for deletion: {e}")

    # Check glossary terms
    try:
        target_terms = _search_target_resources(client, domain_id, project_id, "GLOSSARY_TERM")
        for item in target_terms:
            t = item.get("glossaryTermItem", {})
            if t.get("name") and t["name"] not in bundle_names["glossaryTerms"]:
                to_delete["glossaryTerms"].append({"id": t.get("id"), "name": t["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target glossary terms for deletion: {e}")

    # Check form types
    try:
        target_form_types = _search_target_type_resources(client, domain_id, project_id, "FORM_TYPE")
        for item in target_form_types:
            ft = item.get("formTypeItem", {})
            if ft.get("name") and ft["name"] not in bundle_names["formTypes"]:
                to_delete["formTypes"].append({"id": ft.get("revision"), "name": ft["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target form types for deletion: {e}")

    # Check asset types
    try:
        target_asset_types = _search_target_type_resources(client, domain_id, project_id, "ASSET_TYPE")
        for item in target_asset_types:
            at = item.get("assetTypeItem", {})
            if at.get("name") and at["name"] not in bundle_names["assetTypes"]:
                to_delete["assetTypes"].append({"id": at.get("revision"), "name": at["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target asset types for deletion: {e}")

    # Check assets
    try:
        target_assets = _search_target_resources(client, domain_id, project_id, "ASSET")
        for item in target_assets:
            a = item.get("assetItem", {})
            if a.get("name") and a["name"] not in bundle_names["assets"]:
                to_delete["assets"].append({"id": a.get("identifier"), "name": a["name"]})
    except Exception as e:
        logger.warning(f"Failed to search target assets for deletion: {e}")

    # Check data products
    try:
        target_dps = _search_target_resources(client, domain_id, project_id, "DATA_PRODUCT")
        for item in target_dps:
            dp = item.get("dataProductItem", {})
            if dp.get("name") and dp["name"] not in bundle_names["dataProducts"]:
                to_delete["dataProducts"].append({"id": dp.get("id"), "name": dp["name"]})
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
            client.delete_glossary_term(domainIdentifier=domain_id, identifier=resource_id)
        elif resource_type == "formTypes":
            client.delete_form_type(domainIdentifier=domain_id, formTypeIdentifier=resource_id)
        elif resource_type == "assetTypes":
            client.delete_asset_type(domainIdentifier=domain_id, assetTypeIdentifier=resource_id)
        elif resource_type == "assets":
            client.delete_asset(domainIdentifier=domain_id, identifier=resource_id)
        elif resource_type == "dataProducts":
            client.delete_data_product(domainIdentifier=domain_id, identifier=resource_id)
        return True
    except Exception as e:
        logger.error(f"Failed to delete {resource_type} {resource_id}: {e}")
        return False


def _publish_resource(
    client,
    domain_id: str,
    resource_id: str,
    resource_type: str,
) -> bool:
    """
    Publish an asset or data product.

    Args:
        client: DataZone boto3 client
        domain_id: Target domain identifier
        resource_id: Resource identifier to publish
        resource_type: Type of resource (assets or dataProducts)

    Returns:
        True if publish succeeded, False otherwise
    """
    if resource_type not in PUBLISHABLE_TYPES:
        return False

    try:
        if resource_type == "assets":
            client.create_listing_change_set(
                domainIdentifier=domain_id,
                entityIdentifier=resource_id,
                entityType="ASSET",
                action="PUBLISH",
            )
        elif resource_type == "dataProducts":
            client.create_listing_change_set(
                domainIdentifier=domain_id,
                entityIdentifier=resource_id,
                entityType="DATA_PRODUCT",
                action="PUBLISH",
            )
        return True
    except Exception as e:
        logger.error(f"Failed to publish {resource_type} {resource_id}: {e}")
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
    if they were published (listingStatus == "LISTED") in the source project.
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

    # Build identifier mapping
    id_map = _build_identifier_map(client, domain_id, project_id, catalog_data)

    # Initialize counters
    created = 0
    updated = 0
    deleted = 0
    failed = 0
    published = 0

    # Track successfully imported resource IDs for publishing
    imported_resource_ids = {rt: [] for rt in PUBLISHABLE_TYPES}

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
                # Track for publishing only if source was published (LISTED)
                if resource_type in PUBLISHABLE_TYPES:
                    source_id = resource.get("sourceId")
                    target_id = id_map.get(resource_type, {}).get(source_id)
                    listing_status = resource.get("listingStatus")
                    if target_id and listing_status == "LISTED":
                        imported_resource_ids[resource_type].append(target_id)
            else:
                failed += 1

    # Identify and delete resources not in bundle (reverse dependency order)
    to_delete = _identify_resources_to_delete(client, domain_id, project_id, catalog_data)
    for resource_type in DELETION_ORDER:
        for resource_info in to_delete.get(resource_type, []):
            resource_id = resource_info.get("id")
            if resource_id:
                if _delete_resource(client, domain_id, project_id, resource_id, resource_type):
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

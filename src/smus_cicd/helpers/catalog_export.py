"""
DataZone catalog export functionality for SMUS CI/CD CLI.

This module provides functions to export ALL catalog resources (Glossaries, GlossaryTerms,
FormTypes, AssetTypes, Assets, and Data Products) owned by a DataZone project using the
Search and SearchTypes APIs.

The export is controlled by a simple `content.catalog.enabled` boolean in the manifest.
When enabled, ALL project-owned resources are exported. No manifest-based filters are applied.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)

# Resource types that use the Search API
SEARCH_API_RESOURCE_TYPES = {
    "glossaries": "GLOSSARY",
    "glossaryTerms": "GLOSSARY_TERM",
    "assets": "ASSET",
    "dataProducts": "DATA_PRODUCT",
}

# Resource types that use the SearchTypes API
SEARCH_TYPES_API_RESOURCE_TYPES = {
    "formTypes": "FORM_TYPE",
    "assetTypes": "ASSET_TYPE",
}

ALL_RESOURCE_TYPES = list(SEARCH_API_RESOURCE_TYPES.keys()) + list(
    SEARCH_TYPES_API_RESOURCE_TYPES.keys()
)

# Sort clause used for all queries
SORT_CLAUSE = {"attribute": "updatedAt", "order": "DESCENDING"}


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


def _search_resources(
    client,
    domain_id: str,
    project_id: str,
    search_scope: str,
) -> List[Dict[str, Any]]:
    """
    Search for resources using DataZone Search API with pagination.

    Uses owningProjectIdentifier filter to ensure only project-owned resources
    are returned.

    Args:
        client: DataZone boto3 client
        domain_id: DataZone domain identifier
        project_id: DataZone project identifier
        search_scope: Search scope (ASSET, GLOSSARY, GLOSSARY_TERM, DATA_PRODUCT)

    Returns:
        List of resource items from search results

    Raises:
        Exception: If the DataZone Search API returns an error
    """
    resources = []
    next_token = None

    search_params = {
        "domainIdentifier": domain_id,
        "searchScope": search_scope,
        "owningProjectIdentifier": project_id,
        "sort": SORT_CLAUSE,
    }

    while True:
        if next_token:
            search_params["nextToken"] = next_token

        response = client.search(**search_params)
        items = response.get("items", [])
        resources.extend(items)

        next_token = response.get("nextToken")
        if not next_token:
            break

    return resources


def _search_type_resources(
    client,
    domain_id: str,
    project_id: str,
    search_scope: str,
) -> List[Dict[str, Any]]:
    """
    Search for type resources using DataZone SearchTypes API with pagination.

    Uses managed=False to only return custom types, and filters by
    owningProjectId to ensure only project-owned types are returned.

    Args:
        client: DataZone boto3 client
        domain_id: DataZone domain identifier
        project_id: DataZone project identifier
        search_scope: Search scope (FORM_TYPE, ASSET_TYPE)

    Returns:
        List of type resource items from search results

    Raises:
        Exception: If the DataZone SearchTypes API returns an error
    """
    resources = []
    next_token = None

    search_params = {
        "domainIdentifier": domain_id,
        "searchScope": search_scope,
        "managed": False,
        "sort": SORT_CLAUSE,
    }

    while True:
        if next_token:
            search_params["nextToken"] = next_token

        response = client.search_types(**search_params)
        items = response.get("items", [])

        # Filter by owning project (belt-and-suspenders check)
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


def _serialize_resource(resource: Dict[str, Any], resource_type: str) -> Dict[str, Any]:
    """
    Serialize a resource by extracting name, user-configurable fields, sourceId,
    and externalIdentifier (when present).

    Args:
        resource: Raw resource from API response
        resource_type: Type of resource (glossaries, glossaryTerms, formTypes,
                       assetTypes, assets, dataProducts)

    Returns:
        Serialized resource dict with sourceId, name, and configurable fields
    """
    if resource_type == "glossaries":
        glossary = resource.get("glossaryItem", {})
        return {
            "sourceId": glossary.get("id"),
            "name": glossary.get("name"),
            "description": glossary.get("description"),
            "status": glossary.get("status"),
        }

    elif resource_type == "glossaryTerms":
        term = resource.get("glossaryTermItem", {})
        return {
            "sourceId": term.get("id"),
            "name": term.get("name"),
            "shortDescription": term.get("shortDescription"),
            "longDescription": term.get("longDescription"),
            "glossaryId": term.get("glossaryId"),
            "status": term.get("status"),
            "termRelations": term.get("termRelations", {}),
        }

    elif resource_type == "formTypes":
        form_type = resource.get("formTypeItem", {})
        return {
            "sourceId": form_type.get("revision"),
            "name": form_type.get("name"),
            "description": form_type.get("description"),
            "model": form_type.get("model", {}),
        }

    elif resource_type == "assetTypes":
        asset_type = resource.get("assetTypeItem", {})
        return {
            "sourceId": asset_type.get("revision"),
            "name": asset_type.get("name"),
            "description": asset_type.get("description"),
            "formsInput": asset_type.get("formsOutput", {}),
        }

    elif resource_type == "assets":
        asset = resource.get("assetItem", {})
        serialized = {
            "sourceId": asset.get("identifier") or asset.get("id"),
            "name": asset.get("name"),
            "description": asset.get("description"),
            "typeIdentifier": asset.get("typeIdentifier"),
            "formsInput": asset.get("formsOutput", []),
        }
        # Include externalIdentifier when present
        if asset.get("externalIdentifier"):
            serialized["externalIdentifier"] = asset["externalIdentifier"]
        # Capture listing status to determine publish state during import
        # GetAsset nests it under listing.listingStatus; Search API may have it at top level
        listing_status = asset.get("listingStatus") or (
            asset.get("listing", {}).get("listingStatus")
        )
        if listing_status:
            serialized["listingStatus"] = listing_status
        return serialized

    elif resource_type == "dataProducts":
        data_product = resource.get("dataProductItem", {})
        serialized = {
            "sourceId": data_product.get("id"),
            "name": data_product.get("name"),
            "description": data_product.get("description"),
            "items": data_product.get("items", []),
        }
        # Capture listing status to determine publish state during import
        # GetDataProduct may nest it under listing.listingStatus like GetAsset
        listing_status = data_product.get("listingStatus") or (
            data_product.get("listing", {}).get("listingStatus")
        )
        if listing_status:
            serialized["listingStatus"] = listing_status
        return serialized

    return {}


def _enrich_asset_items(
    client, domain_id: str, items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Enrich asset search results with full details from GetAsset API.

    The Search API returns summary data without formsOutput. This function
    calls GetAsset for each item to retrieve the complete asset including
    form data, description, and listing status.

    Args:
        client: DataZone boto3 client
        domain_id: DataZone domain identifier
        items: Asset items from search results

    Returns:
        List of enriched asset items wrapped in {"assetItem": ...} format
    """
    enriched = []
    for item in items:
        asset_summary = item.get("assetItem", {})
        asset_id = asset_summary.get("identifier")
        if not asset_id:
            enriched.append(item)
            continue
        try:
            detail = client.get_asset(domainIdentifier=domain_id, identifier=asset_id)
            # Remove ResponseMetadata from boto3 response
            detail.pop("ResponseMetadata", None)
            enriched.append({"assetItem": detail})
        except Exception as e:
            logger.warning("Failed to get asset %s: %s, using search data", asset_id, e)
            enriched.append(item)
    return enriched


def _enrich_data_product_items(
    client, domain_id: str, items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Enrich data product search results with full details from GetDataProduct API.

    The Search API's DataProductResultItem does not include the `items` field
    (data assets of the product). This function calls GetDataProduct for each
    item to retrieve the complete data product including its items list.

    Args:
        client: DataZone boto3 client
        domain_id: DataZone domain identifier
        items: Data product items from search results

    Returns:
        List of enriched data product items wrapped in {"dataProductItem": ...} format
    """
    enriched = []
    for item in items:
        dp_summary = item.get("dataProductItem", {})
        dp_id = dp_summary.get("id")
        if not dp_id:
            enriched.append(item)
            continue
        try:
            detail = client.get_data_product(
                domainIdentifier=domain_id, identifier=dp_id
            )
            detail.pop("ResponseMetadata", None)
            enriched.append({"dataProductItem": detail})
        except Exception as e:
            logger.warning(
                "Failed to get data product %s: %s, using search data", dp_id, e
            )
            enriched.append(item)
    return enriched


def export_catalog(
    domain_id: str,
    project_id: str,
    region: str,
) -> Dict[str, Any]:
    """
    Export ALL catalog resources owned by a DataZone project.

    When catalog export is enabled (content.catalog.enabled: true), this function
    exports all resource types owned by the project: Glossaries, GlossaryTerms,
    FormTypes, AssetTypes, Assets, and Data Products.

    No manifest-based filters are applied.

    Args:
        domain_id: DataZone domain identifier
        project_id: DataZone project identifier
        region: AWS region

    Returns:
        Dict matching the catalog_export.json schema with metadata and all
        resource type arrays.

    Raises:
        Exception: If DataZone API calls fail during search. No partial JSON
                   is produced on error.
    """
    client = _get_datazone_client(region)

    result: Dict[str, Any] = {
        "metadata": {
            "sourceProjectId": project_id,
            "sourceDomainId": domain_id,
            "exportTimestamp": datetime.now(timezone.utc).isoformat(),
            "resourceTypes": ALL_RESOURCE_TYPES,
        },
        "glossaries": [],
        "glossaryTerms": [],
        "formTypes": [],
        "assetTypes": [],
        "assets": [],
        "dataProducts": [],
    }

    # Export resources using Search API
    for resource_type, search_scope in SEARCH_API_RESOURCE_TYPES.items():
        items = _search_resources(client, domain_id, project_id, search_scope)
        # Enrich assets with full details (search API doesn't return formsOutput)
        if resource_type == "assets" and items:
            items = _enrich_asset_items(client, domain_id, items)
        # Enrich data products with full details (search API doesn't return items)
        if resource_type == "dataProducts" and items:
            items = _enrich_data_product_items(client, domain_id, items)
        result[resource_type] = [
            _serialize_resource(item, resource_type) for item in items
        ]

    # Export resources using SearchTypes API
    for resource_type, search_scope in SEARCH_TYPES_API_RESOURCE_TYPES.items():
        items = _search_type_resources(client, domain_id, project_id, search_scope)
        result[resource_type] = [
            _serialize_resource(item, resource_type) for item in items
        ]

    total_resources = sum(len(result[rt]) for rt in ALL_RESOURCE_TYPES)
    if total_resources == 0:
        logger.info(
            "No catalog resources found for project %s in domain %s",
            project_id,
            domain_id,
        )

    return result

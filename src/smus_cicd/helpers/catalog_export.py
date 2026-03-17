"""
DataZone catalog export functionality for SMUS CI/CD CLI.

This module provides functions to export ALL catalog resources (Glossaries, GlossaryTerms,
FormTypes, AssetTypes, Assets, and Data Products) owned by a DataZone project using the
Search and SearchTypes APIs.

The export is controlled by a simple `content.catalog.enabled` boolean in the manifest.
When enabled, ALL project-owned resources are exported. The only optional filter is the
`--updated-after` CLI flag which filters ALL resource types uniformly by modification
timestamp. No manifest-based filters are applied.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


def _build_updated_after_filter(updated_after: str) -> Dict[str, Any]:
    """
    Build the updatedAfter filter clause for search queries.

    Args:
        updated_after: ISO 8601 timestamp from --updated-after CLI flag

    Returns:
        Filter dict for DataZone search/searchTypes API
    """
    return {
        "filter": {
            "attribute": "updatedAt",
            "value": updated_after,
        }
    }


def _search_resources(
    client,
    domain_id: str,
    project_id: str,
    search_scope: str,
    updated_after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search for resources using DataZone Search API with pagination.

    Uses owningProjectIdentifier filter to ensure only project-owned resources
    are returned. Optionally filters by updatedAt when --updated-after CLI flag
    is provided.

    Args:
        client: DataZone boto3 client
        domain_id: DataZone domain identifier
        project_id: DataZone project identifier
        search_scope: Search scope (ASSET, GLOSSARY, GLOSSARY_TERM, DATA_PRODUCT)
        updated_after: Optional ISO 8601 timestamp from --updated-after CLI flag

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

    if updated_after:
        search_params["filters"] = _build_updated_after_filter(updated_after)

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
    updated_after: Optional[str] = None,
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
        updated_after: Optional ISO 8601 timestamp from --updated-after CLI flag

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
        "owningProjectIdentifier": project_id,
        "sort": SORT_CLAUSE,
    }

    if updated_after:
        search_params["filters"] = _build_updated_after_filter(updated_after)

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


def _serialize_resource(
    resource: Dict[str, Any], resource_type: str
) -> Dict[str, Any]:
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
            "sourceId": asset.get("identifier"),
            "name": asset.get("name"),
            "description": asset.get("description"),
            "typeIdentifier": asset.get("typeIdentifier"),
            "formsInput": asset.get("formsOutput", []),
            "inputForms": asset.get("inputForms", []),
        }
        # Include externalIdentifier when present
        if asset.get("externalIdentifier"):
            serialized["externalIdentifier"] = asset["externalIdentifier"]
        # Capture listing status to determine publish state during import
        if asset.get("listingStatus"):
            serialized["listingStatus"] = asset["listingStatus"]
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
        if data_product.get("listingStatus"):
            serialized["listingStatus"] = data_product["listingStatus"]
        return serialized

    return {}


def export_catalog(
    domain_id: str,
    project_id: str,
    region: str,
    updated_after: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export ALL catalog resources owned by a DataZone project.

    When catalog export is enabled (content.catalog.enabled: true), this function
    exports all resource types owned by the project: Glossaries, GlossaryTerms,
    FormTypes, AssetTypes, Assets, and Data Products.

    No manifest-based filters are applied. The only optional filter is the
    --updated-after CLI flag which filters ALL resource types uniformly.

    Args:
        domain_id: DataZone domain identifier
        project_id: DataZone project identifier
        region: AWS region
        updated_after: Optional ISO 8601 timestamp from --updated-after CLI flag
                       (NOT from manifest). Filters ALL resource types uniformly
                       by updatedAt.

    Returns:
        Dict matching the catalog_export.json schema with metadata and all
        resource type arrays.

    Raises:
        Exception: If DataZone API calls fail during search. No partial JSON
                   is produced on error.
    """
    client = _get_datazone_client(region)

    result = {
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
        items = _search_resources(
            client, domain_id, project_id, search_scope, updated_after
        )
        result[resource_type] = [
            _serialize_resource(item, resource_type) for item in items
        ]

    # Export resources using SearchTypes API
    for resource_type, search_scope in SEARCH_TYPES_API_RESOURCE_TYPES.items():
        items = _search_type_resources(
            client, domain_id, project_id, search_scope, updated_after
        )
        result[resource_type] = [
            _serialize_resource(item, resource_type) for item in items
        ]

    total_resources = sum(
        len(result[rt]) for rt in ALL_RESOURCE_TYPES
    )
    if total_resources == 0:
        logger.info(
            "No catalog resources found for project %s in domain %s",
            project_id,
            domain_id,
        )

    return result

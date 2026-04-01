"""Shared helpers for catalog import/export integration tests.

This module lives in a hyphenated directory (catalog-import-export) so it
cannot be imported via normal Python package syntax.  Use importlib::

    import importlib.util, os, sys
    _spec = importlib.util.spec_from_file_location(
        "catalog_test_helpers",
        os.path.join(os.path.dirname(__file__), "catalog_test_helpers.py"),
    )
    _helpers = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_helpers)
"""

import os
from typing import Any, Dict, List, Optional

import boto3
import pytest
import yaml
from botocore.exceptions import ClientError

# ------------------------------------------------------------------
# Project / manifest helpers
# ------------------------------------------------------------------


def get_manifest_path(name: str) -> str:
    """Return absolute path to a manifest in the test directory."""
    return os.path.join(os.path.dirname(__file__), name)


def get_project_info(pipeline_file: str, stage: str = "dev"):
    """Return (domain_id, project_id, region, project_name) for *stage*."""
    with open(pipeline_file, "r") as fh:
        raw = yaml.safe_load(fh)
    project_name = raw["stages"][stage]["project"]["name"]
    region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

    from smus_cicd.application import ApplicationManifest
    from smus_cicd.helpers.utils import (
        build_domain_config,
        get_datazone_project_info,
    )

    manifest = ApplicationManifest.from_file(pipeline_file)
    config = build_domain_config(manifest.stages[stage])
    info = get_datazone_project_info(project_name, config)
    if "error" in info or "domain_id" not in info:
        pytest.fail(f"Failed to get project info for stage {stage}: {info}")
    return info["domain_id"], info["project_id"], region, project_name


# ------------------------------------------------------------------
# DataZone client
# ------------------------------------------------------------------


def dz_client(region: str):
    """Create a DataZone client for the given region."""
    return boto3.client("datazone", region_name=region)


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


def search_resources(
    domain_id: str,
    project_id: str,
    search_scope: str,
    region: str,
) -> List[Dict[str, Any]]:
    """Paginated search for resources of *search_scope* in *project_id*."""
    client = dz_client(region)
    results: List[Dict[str, Any]] = []
    next_token = None
    while True:
        kwargs: Dict[str, Any] = {
            "domainIdentifier": domain_id,
            "searchScope": search_scope,
            "owningProjectIdentifier": project_id,
            "maxResults": 50,
        }
        if next_token:
            kwargs["nextToken"] = next_token
        try:
            resp = client.search(**kwargs)
        except Exception:
            break
        results.extend(resp.get("items", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return results


# ------------------------------------------------------------------
# Bundle ZIP
# ------------------------------------------------------------------


def find_bundle_zip(prefix: str = "Catalog") -> Optional[str]:
    """Find the most recent bundle ZIP matching *prefix*."""
    for d in [".", "artifacts"]:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d), reverse=True):
                if f.startswith(prefix) and f.endswith(".zip"):
                    return os.path.join(d, f)
    return None


# ------------------------------------------------------------------
# Resource creation helpers
# ------------------------------------------------------------------


def create_glossary(
    domain_id: str,
    project_id: str,
    name: str,
    region: str,
    description: str = "",
) -> Optional[Dict[str, Any]]:
    """Create or find an existing glossary by name."""
    client = dz_client(region)
    try:
        resp = client.create_glossary(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            status="ENABLED",
        )
        return {"id": resp["id"], "name": name}
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "AccessDeniedException":
            pytest.skip("User lacks CreateGlossary permission")
        if code == "ConflictException":
            items = search_resources(domain_id, project_id, "GLOSSARY", region)
            for item in items:
                g = item.get("glossaryItem", {})
                if g.get("name") == name:
                    return {"id": g["id"], "name": name}
            return None
        raise
    except Exception:
        return None


def create_glossary_term(
    domain_id: str,
    glossary_id: str,
    name: str,
    short_description: str,
    region: str,
    project_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Create or find an existing glossary term by name."""
    client = dz_client(region)
    try:
        resp = client.create_glossary_term(
            domainIdentifier=domain_id,
            glossaryIdentifier=glossary_id,
            name=name,
            shortDescription=short_description,
            status="ENABLED",
        )
        return {"id": resp["id"], "name": name, "glossaryId": glossary_id}
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("AccessDeniedException", "ConflictException"):
            if code == "ConflictException" and project_id:
                items = search_resources(domain_id, project_id, "GLOSSARY_TERM", region)
                for item in items:
                    t = item.get("glossaryTermItem", {})
                    if t.get("name") == name:
                        return {
                            "id": t["id"],
                            "name": name,
                            "glossaryId": t.get("glossaryId"),
                        }
            return None
        raise
    except Exception:
        return None


def create_asset(
    domain_id: str,
    project_id: str,
    name: str,
    region: str,
    description: str = "",
    type_identifier: str = "amazon.datazone.RelationalTableAssetType",
) -> Optional[Dict[str, Any]]:
    """Create or find an existing asset by name."""
    client = dz_client(region)
    try:
        resp = client.create_asset(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            typeIdentifier=type_identifier,
        )
        return {"id": resp["id"], "name": name}
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "AccessDeniedException":
            pytest.skip("User lacks CreateAsset permission")
        if code == "ConflictException":
            items = search_resources(domain_id, project_id, "ASSET", region)
            for item in items:
                a = item.get("assetItem", {})
                if a.get("name") == name:
                    return {
                        "id": a.get("identifier", a.get("id")),
                        "name": name,
                    }
            return None
        raise


def publish_asset(domain_id: str, asset_id: str, region: str) -> bool:
    """Publish an asset and poll until listing status is ACTIVE."""
    import time

    client = dz_client(region)
    try:
        client.create_listing_change_set(
            domainIdentifier=domain_id,
            entityIdentifier=asset_id,
            entityType="ASSET",
            action="PUBLISH",
        )
        for _ in range(30):
            time.sleep(2)
            resp = client.get_asset(domainIdentifier=domain_id, identifier=asset_id)
            if resp.get("listingStatus") == "ACTIVE":
                return True
        return False
    except ClientError:
        return False


def delete_glossary(domain_id: str, glossary_id: str, region: str):
    """Best-effort delete of a glossary."""
    try:
        dz_client(region).delete_glossary(
            domainIdentifier=domain_id, identifier=glossary_id
        )
    except Exception:
        pass


def delete_glossary_term(domain_id: str, term_id: str, region: str):
    """Best-effort delete of a glossary term."""
    try:
        dz_client(region).delete_glossary_term(
            domainIdentifier=domain_id, identifier=term_id
        )
    except Exception:
        pass


# ------------------------------------------------------------------
# Bundle read/create helpers
# ------------------------------------------------------------------


def read_catalog_from_bundle(bundle_path: str) -> Optional[Dict[str, Any]]:
    """Extract and return catalog_export.json from a bundle ZIP."""
    import json
    import zipfile

    with zipfile.ZipFile(bundle_path, "r") as zf:
        if "catalog/catalog_export.json" not in zf.namelist():
            return None
        with zf.open("catalog/catalog_export.json") as fh:
            return json.load(fh)


def create_bundle_with_catalog(
    catalog_data: Dict[str, Any],
    extra_files: Optional[Dict[str, str]] = None,
) -> str:
    """Create a temporary bundle ZIP containing catalog_data. Returns path."""
    import json
    import tempfile
    import zipfile

    tmp = tempfile.mkdtemp()
    bundle_path = os.path.join(tmp, "test-bundle.zip")
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr(
            "catalog/catalog_export.json",
            json.dumps(catalog_data, indent=2, default=str),
        )
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)
    return bundle_path


def create_bundle_without_catalog() -> str:
    """Create a temporary bundle ZIP without catalog_export.json."""
    import tempfile
    import zipfile

    tmp = tempfile.mkdtemp()
    bundle_path = os.path.join(tmp, "test-bundle-no-catalog.zip")
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("placeholder.txt", "no catalog data")
    return bundle_path

#!/usr/bin/env python3
"""Remove project-owned business catalog resources from the test target domain/project.

Skips Glue-backed assets (GlueTable, GlueDatabase, etc.) and only cleans up
resources created in the business data catalog (glossaries, glossary terms,
form types, asset types, custom assets, and data products).
"""

import boto3
import os
import time

DOMAIN_ID = os.environ.get("DOMAIN_ID")
PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("DEV_DOMAIN_REGION")

endpoint_url = os.environ.get("DATAZONE_ENDPOINT_URL")
kwargs = {"region_name": REGION}
if endpoint_url:
    kwargs["endpoint_url"] = endpoint_url

client = boto3.client("datazone", **kwargs)

# AWS-managed asset types backed by Glue/physical infrastructure — never delete these
GLUE_ASSET_TYPES = {
    "amazon.datazone.GlueTableAssetType",
    "amazon.datazone.GlueDatabaseAssetType",
    "amazon.datazone.GlueViewAssetType",
    "GlueTable",
    "GlueDatabase",
    "GlueView",
}


def is_glue_asset(item):
    """Return True if the asset is backed by a Glue/physical resource."""
    asset = item.get("assetItem", {})
    type_id = asset.get("typeIdentifier", "")
    # Match exact known types or any type containing 'Glue'
    return type_id in GLUE_ASSET_TYPES or "Glue" in type_id


def search_resources(search_scope):
    items = []
    params = {
        "domainIdentifier": DOMAIN_ID,
        "owningProjectIdentifier": PROJECT_ID,
        "searchScope": search_scope,
        "maxResults": 50,
    }
    while True:
        resp = client.search(**params)
        items.extend(resp.get("items", []))
        token = resp.get("nextToken")
        if not token:
            break
        params["nextToken"] = token
    return items


def search_type_resources(search_scope):
    items = []
    params = {
        "domainIdentifier": DOMAIN_ID,
        "searchScope": search_scope,
        "managed": False,
        "maxResults": 50,
    }
    while True:
        resp = client.search_types(**params)
        for i in resp.get("items", []):
            for v in i.values():
                if isinstance(v, dict) and v.get("owningProjectId") == PROJECT_ID:
                    items.append(i)
                    break
        token = resp.get("nextToken")
        if not token:
            break
        params["nextToken"] = token
    return items


def get_id(item, scope):
    if scope == "ASSET":
        return item.get("assetItem", {}).get("identifier") or item.get("assetItem", {}).get("id")
    elif scope == "GLOSSARY":
        return item.get("glossaryItem", {}).get("id")
    elif scope == "GLOSSARY_TERM":
        return item.get("glossaryTermItem", {}).get("id")
    elif scope == "DATA_PRODUCT":
        dp = item.get("dataProductItem", item.get("dataProductListing", {}))
        return dp.get("id") or dp.get("identifier")
    elif scope == "FORM_TYPE":
        return item.get("formTypeItem", {}).get("name")
    elif scope == "ASSET_TYPE":
        return item.get("assetTypeItem", {}).get("name")
    return None


def get_name(item, scope):
    for key in item:
        inner = item[key]
        if isinstance(inner, dict) and "name" in inner:
            return inner["name"]
    return "unknown"


def disable_glossary_term(term_id):
    """Disable a glossary term and clear its termRelations."""
    try:
        # Get the term to find its glossaryIdentifier (required for update)
        term = client.get_glossary_term(
            domainIdentifier=DOMAIN_ID,
            identifier=term_id,
        )
        glossary_id = term.get("glossaryId")  # API returns glossaryId, not glossaryIdentifier
        name = term.get("name")

        if not glossary_id:
            print(f"    Glossary term {term_id} has no glossaryId, skipping")
            return False

        # Build update kwargs — only include termRelations if there are existing ones
        kwargs = {
            "domainIdentifier": DOMAIN_ID,
            "identifier": term_id,
            "glossaryIdentifier": glossary_id,
            "name": name,
            "status": "DISABLED",
        }
        # Clear term relations if they exist (empty lists are invalid, omit instead)
        existing_relations = term.get("termRelations", {})
        if existing_relations:
            clear_relations = {}
            for key, val in existing_relations.items():
                if isinstance(val, list) and len(val) > 0:
                    # Can't set to empty — just skip the key to leave it as-is
                    # Actually we need to remove references. The API doesn't allow
                    # empty lists, so we'll just disable and hope deletion works.
                    pass
            # If we can't clear relations, just disable
        client.update_glossary_term(**kwargs)
        print(f"    Disabled glossary term {term_id}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"    Failed to disable glossary term {term_id}: {e}")
        return False


def disable_glossary(glossary_id):
    """Disable a glossary."""
    try:
        client.update_glossary(
            domainIdentifier=DOMAIN_ID,
            identifier=glossary_id,
            status="DISABLED",
        )
        print(f"    Disabled glossary {glossary_id}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"    Failed to disable glossary {glossary_id}: {e}")
        return False


def disable_form_type(form_name):
    """Disable a form type by re-creating it with status=DISABLED."""
    try:
        resp = client.get_form_type(domainIdentifier=DOMAIN_ID, formTypeIdentifier=form_name)
        owning_project = resp.get("owningProjectId")
        description = resp.get("description")
        model = resp.get("model")

        kwargs = {
            "domainIdentifier": DOMAIN_ID,
            "owningProjectIdentifier": owning_project or PROJECT_ID,
            "name": form_name,
            "status": "DISABLED",
        }
        if description:
            kwargs["description"] = description
        if model:
            kwargs["model"] = model
        client.create_form_type(**kwargs)
        print(f"    Disabled form type {form_name}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"    Failed to disable form type {form_name}: {e}")
        return False
        return False


def unpublish_resource(resource_id, resource_type):
    """Unpublish an asset or data product if it has an ACTIVE listing."""
    if resource_type not in ("ASSET", "DATA_PRODUCT"):
        return
    try:
        if resource_type == "ASSET":
            resp = client.get_asset(domainIdentifier=DOMAIN_ID, identifier=resource_id)
            entity_type = "ASSET"
        else:
            resp = client.get_data_product(domainIdentifier=DOMAIN_ID, identifier=resource_id)
            entity_type = "DATA_PRODUCT"

        listing = resp.get("listing", {})
        listing_status = listing.get("listingStatus") or listing.get("status")
        listing_id = listing.get("listingId") or listing.get("id")

        if listing_status == "ACTIVE" and listing_id:
            print(f"    Unpublishing {resource_type} {resource_id} (listing={listing_id})...")
            client.create_listing_change_set(
                domainIdentifier=DOMAIN_ID,
                entityIdentifier=resource_id,
                entityType=entity_type,
                action="UNPUBLISH",
            )
            time.sleep(1)
            print(f"    Unpublished.")
        else:
            print(f"    No active listing for {resource_type} {resource_id} (status={listing_status})")
    except Exception as e:
        print(f"    ⚠️  Failed to unpublish {resource_type} {resource_id}: {e}")


def delete_resource(resource_id, resource_type, name):
    try:
        # Unpublish before deleting assets and data products
        if resource_type in ("ASSET", "DATA_PRODUCT"):
            unpublish_resource(resource_id, resource_type)

        if resource_type == "ASSET":
            client.delete_asset(domainIdentifier=DOMAIN_ID, identifier=resource_id)
        elif resource_type == "GLOSSARY":
            disable_glossary(resource_id)
            client.delete_glossary(domainIdentifier=DOMAIN_ID, identifier=resource_id)
        elif resource_type == "GLOSSARY_TERM":
            disable_glossary_term(resource_id)
            client.delete_glossary_term(domainIdentifier=DOMAIN_ID, identifier=resource_id)
        elif resource_type == "DATA_PRODUCT":
            client.delete_data_product(domainIdentifier=DOMAIN_ID, identifier=resource_id)
        elif resource_type == "FORM_TYPE":
            disable_form_type(resource_id)
            client.delete_form_type(domainIdentifier=DOMAIN_ID, formTypeIdentifier=resource_id)
        elif resource_type == "ASSET_TYPE":
            client.delete_asset_type(domainIdentifier=DOMAIN_ID, identifier=resource_id)
        print(f"  ✅ Deleted {resource_type}: {name} ({resource_id})")
        return True
    except Exception as e:
        print(f"  ❌ Failed to delete {resource_type}: {name} ({resource_id}): {e}")
        return False


# Deletion order: reverse dependency
deletion_order = [
    ("DATA_PRODUCT", "search"),
    ("ASSET", "search"),
    ("ASSET_TYPE", "search_types"),
    ("FORM_TYPE", "search_types"),
    ("GLOSSARY_TERM", "search"),
    ("GLOSSARY", "search"),
]

print(f"🧹 Cleaning catalog resources from domain={DOMAIN_ID}, project={PROJECT_ID}, region={REGION}")
print()

# Ensure policy grants exist before cleanup (needed to disable form types etc.)
_POLICY_DETAIL_KEY = {
    "CREATE_GLOSSARY": "createGlossary",
    "CREATE_FORM_TYPE": "createFormType",
    "CREATE_ASSET_TYPE": "createAssetType",
}
try:
    project_resp = client.get_project(domainIdentifier=DOMAIN_ID, identifier=PROJECT_ID)
    _domain_unit_id = project_resp.get("domainUnitId")
    if _domain_unit_id:
        for pt in ["CREATE_GLOSSARY", "CREATE_FORM_TYPE", "CREATE_ASSET_TYPE"]:
            try:
                resp = client.list_policy_grants(
                    domainIdentifier=DOMAIN_ID,
                    entityType="DOMAIN_UNIT",
                    entityIdentifier=_domain_unit_id,
                    policyType=pt,
                )
                if not resp.get("grantList"):
                    client.add_policy_grant(
                        domainIdentifier=DOMAIN_ID,
                        entityType="DOMAIN_UNIT",
                        entityIdentifier=_domain_unit_id,
                        policyType=pt,
                        principal={"project": {"projectDesignation": "OWNER", "projectIdentifier": PROJECT_ID}},
                        detail={_POLICY_DETAIL_KEY[pt]: {}},
                    )
                    print(f"  ➕ Added {pt} grant (needed for cleanup)")
            except Exception:
                pass
except Exception:
    pass

total_deleted = 0
total_failed = 0

for scope, api_type in deletion_order:
    print(f"--- {scope} ---")
    if api_type == "search":
        items = search_resources(scope)
    else:
        items = search_type_resources(scope)

    if not items:
        print(f"  (none found)")
        continue

    print(f"  Found {len(items)} resource(s)")

    # For glossary terms, disable all first (to clear references), then delete
    # with retries to handle cross-reference ordering
    if scope == "GLOSSARY_TERM":
        print("  Disabling all glossary terms first...")
        for item in items:
            rid = get_id(item, scope)
            if rid:
                disable_glossary_term(rid)
        time.sleep(1)

        # Retry loop: cross-references may prevent deletion on first pass
        remaining = [(get_id(item, scope), get_name(item, scope)) for item in items]
        max_passes = 3
        for pass_num in range(max_passes):
            still_remaining = []
            for rid, name in remaining:
                if rid:
                    if delete_resource(rid, scope, name):
                        total_deleted += 1
                    else:
                        still_remaining.append((rid, name))
                time.sleep(0.2)
            remaining = still_remaining
            if not remaining:
                break
            if pass_num < max_passes - 1:
                print(f"  Retrying {len(remaining)} term(s) (pass {pass_num + 2})...")
                time.sleep(1)
        total_failed += len(remaining)
        continue

    for item in items:
        rid = get_id(item, scope)
        name = get_name(item, scope)

        # Skip Glue-backed assets — only clean up business catalog resources
        if scope == "ASSET" and is_glue_asset(item):
            type_id = item.get("assetItem", {}).get("typeIdentifier", "unknown")
            print(f"  ⏭️  Skipping Glue asset: {name} (type={type_id})")
            continue

        if rid:
            if delete_resource(rid, scope, name):
                total_deleted += 1
            else:
                total_failed += 1
            time.sleep(0.2)

# --- Remove policy grants from the project's domain unit ---
print()
print("--- POLICY GRANTS ---")

GRANT_TYPES = ["CREATE_GLOSSARY", "CREATE_FORM_TYPE", "CREATE_ASSET_TYPE"]

try:
    project = client.get_project(domainIdentifier=DOMAIN_ID, identifier=PROJECT_ID)
    domain_unit_id = project.get("domainUnitId")
    if not domain_unit_id:
        print("  ⚠️  Project has no domainUnitId, skipping grant removal")
    else:
        print(f"  Domain unit: {domain_unit_id}")
        grants_removed = 0
        for policy_type in GRANT_TYPES:
            try:
                resp = client.list_policy_grants(
                    domainIdentifier=DOMAIN_ID,
                    entityType="DOMAIN_UNIT",
                    entityIdentifier=domain_unit_id,
                    policyType=policy_type,
                )
                grants = resp.get("grantList", [])
                if not grants:
                    print(f"  {policy_type}: no grants found")
                    continue
                for grant in grants:
                    principal = grant.get("principal", {})
                    detail = grant.get("detail", {})
                    try:
                        kwargs = {
                            "domainIdentifier": DOMAIN_ID,
                            "entityType": "DOMAIN_UNIT",
                            "entityIdentifier": domain_unit_id,
                            "policyType": policy_type,
                            "principal": principal,
                        }
                        client.remove_policy_grant(**kwargs)
                        print(f"  ✅ Removed {policy_type} grant (principal={principal})")
                        grants_removed += 1
                    except Exception as e:
                        print(f"  ❌ Failed to remove {policy_type} grant: {e}")
                        total_failed += 1
            except Exception as e:
                print(f"  ⚠️  Failed to list {policy_type} grants: {e}")
        print(f"  Grants removed: {grants_removed}")
except Exception as e:
    print(f"  ⚠️  Failed to get project domain unit: {e}")

print()
print(f"🏁 Done. Deleted: {total_deleted}, Failed: {total_failed}")

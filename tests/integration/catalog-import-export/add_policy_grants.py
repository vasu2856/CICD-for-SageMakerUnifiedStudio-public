#!/usr/bin/env python3
"""Add missing catalog policy grants (CREATE_GLOSSARY, CREATE_FORM_TYPE, CREATE_ASSET_TYPE)
to a DataZone project's domain unit.

Usage:
    source .env
    DOMAIN_ID=<id> PROJECT_ID=<id> DEV_DOMAIN_REGION=us-east-1 python add_policy_grants.py

Or resolve from manifest first:
    aws-smus-cicd-cli describe --manifest manifest_catalog_export_import_test.yaml --targets test --connect --output JSON
"""

import os
import sys

import boto3

DOMAIN_ID = os.environ.get("DOMAIN_ID")
PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("DEV_DOMAIN_REGION")

if not all([DOMAIN_ID, PROJECT_ID, REGION]):
    print("Error: DOMAIN_ID, PROJECT_ID, and DEV_DOMAIN_REGION environment variables are required.")
    sys.exit(1)

endpoint_url = os.environ.get("DATAZONE_ENDPOINT_URL")
kwargs = {"region_name": REGION}
if endpoint_url:
    kwargs["endpoint_url"] = endpoint_url

client = boto3.client("datazone", **kwargs)

# Get domain unit ID from project
project = client.get_project(domainIdentifier=DOMAIN_ID, identifier=PROJECT_ID)
domain_unit_id = project.get("domainUnitId")

if not domain_unit_id:
    print(f"⚠️  Project {PROJECT_ID} has no domainUnitId, cannot add grants.")
    sys.exit(1)

print(f"Domain: {DOMAIN_ID}")
print(f"Project: {PROJECT_ID}")
print(f"Domain unit: {domain_unit_id}")
print()

GRANTS = {
    "CREATE_GLOSSARY": "createGlossary",
    "CREATE_FORM_TYPE": "createFormType",
    "CREATE_ASSET_TYPE": "createAssetType",
}

added = 0
skipped = 0
failed = 0

for policy_type, detail_key in GRANTS.items():
    try:
        resp = client.list_policy_grants(
            domainIdentifier=DOMAIN_ID,
            entityType="DOMAIN_UNIT",
            entityIdentifier=domain_unit_id,
            policyType=policy_type,
        )
        if not resp.get("grantList"):
            client.add_policy_grant(
                domainIdentifier=DOMAIN_ID,
                entityType="DOMAIN_UNIT",
                entityIdentifier=domain_unit_id,
                policyType=policy_type,
                principal={"project": {"projectDesignation": "OWNER", "projectIdentifier": PROJECT_ID}},
                detail={detail_key: {}},
            )
            print(f"✅ Added {policy_type}")
            added += 1
        else:
            print(f"✓  {policy_type} already exists ({len(resp['grantList'])} grant(s))")
            skipped += 1
    except Exception as e:
        print(f"❌ Failed {policy_type}: {e}")
        failed += 1

print()
print(f"Done. Added: {added}, Already existed: {skipped}, Failed: {failed}")

#!/usr/bin/env python3
"""
Seed script to populate a DataZone project with sample catalog resources.

Creates glossaries, glossary terms, form types, asset types, and assets
for demonstrating the catalog import/export feature.

Usage:
    python seed_catalog_data.py --domain-id <domain-id> --project-id <project-id> --region us-east-1

The script is idempotent: it skips resources that already exist (ConflictException).
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def create_glossary(client, domain_id, project_id, name, description):
    """Create a glossary, skip if it already exists."""
    try:
        resp = client.create_glossary(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            status="ENABLED",
        )
        print(f"  ✅ Created glossary: {name} (id: {resp['id']})")
        return resp["id"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  ⏭️  Glossary already exists: {name}")
            return _find_glossary_id(client, domain_id, project_id, name)
        raise


def create_glossary_term(client, domain_id, glossary_id, name, short_desc, long_desc):
    """Create a glossary term, skip if it already exists."""
    try:
        resp = client.create_glossary_term(
            domainIdentifier=domain_id,
            glossaryIdentifier=glossary_id,
            name=name,
            shortDescription=short_desc,
            longDescription=long_desc,
            status="ENABLED",
        )
        print(f"  ✅ Created glossary term: {name} (id: {resp['id']})")
        return resp["id"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  ⏭️  Glossary term already exists: {name}")
            return None
        raise


def create_form_type(client, domain_id, project_id, name, description, model):
    """Create a form type, skip if it already exists."""
    try:
        resp = client.create_form_type(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            model={"smithy": model},
            status="ENABLED",
        )
        print(f"  ✅ Created form type: {name} (revision: {resp.get('revision', 'n/a')})")
        return resp.get("name", name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  ⏭️  Form type already exists: {name}")
            return name
        raise


def create_asset_type(client, domain_id, project_id, name, description, forms_input):
    """Create an asset type, skip if it already exists."""
    try:
        resp = client.create_asset_type(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            formsInput=forms_input,
        )
        print(f"  ✅ Created asset type: {name} (revision: {resp.get('revision', 'n/a')})")
        return resp.get("name", name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  ⏭️  Asset type already exists: {name}")
            return name
        raise


def create_asset(client, domain_id, project_id, name, description, type_identifier):
    """Create an asset, skip if it already exists."""
    try:
        resp = client.create_asset(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            name=name,
            description=description,
            typeIdentifier=type_identifier,
        )
        print(f"  ✅ Created asset: {name} (id: {resp['id']})")
        return resp["id"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  ⏭️  Asset already exists: {name}")
            return None
        raise


def _find_glossary_id(client, domain_id, project_id, name):
    """Find a glossary by name in the project."""
    try:
        resp = client.search(
            domainIdentifier=domain_id,
            owningProjectIdentifier=project_id,
            searchScope="GLOSSARY",
            searchText=name,
            maxResults=10,
        )
        for item in resp.get("items", []):
            glossary = item.get("glossaryItem", {})
            if glossary.get("name") == name:
                return glossary.get("id")
    except ClientError:
        pass
    return None


def seed(domain_id, project_id, region):
    """Seed the project with sample catalog resources."""
    client = boto3.client("datazone", region_name=region)

    summary = {"created": 0, "skipped": 0, "failed": 0}

    print(f"\n🌱 Seeding catalog data into project {project_id} (domain: {domain_id})\n")

    # --- Glossaries ---
    print("📚 Creating glossaries...")
    glossary_id = create_glossary(
        client, domain_id, project_id,
        name="Business Terms",
        description="Core business terminology for the organization",
    )
    if glossary_id:
        summary["created"] += 1
    else:
        summary["skipped"] += 1

    # --- Glossary Terms ---
    print("\n📝 Creating glossary terms...")
    if glossary_id:
        terms = [
            ("Revenue", "Total income generated", "Total income generated from sales of goods and services before expenses are deducted."),
            ("Customer", "An entity that purchases goods", "An individual or organization that purchases goods or services from the business."),
            ("Churn Rate", "Rate of customer attrition", "The percentage of customers who stop using a product or service during a given time period."),
        ]
        for name, short_desc, long_desc in terms:
            term_id = create_glossary_term(
                client, domain_id, glossary_id, name, short_desc, long_desc
            )
            if term_id:
                summary["created"] += 1
            else:
                summary["skipped"] += 1
    else:
        print("  ⚠️  Skipping terms — glossary ID not available")
        summary["skipped"] += 3

    # --- Form Types ---
    print("\n📋 Creating form types...")
    smithy_model = json.dumps({
        "smithy": "1.0",
        "shapes": {
            "com.example#DataQualityForm": {
                "type": "structure",
                "members": {
                    "qualityScore": {"target": "smithy.api#Integer"},
                    "lastValidated": {"target": "smithy.api#String"},
                },
            }
        },
    })
    form_name = create_form_type(
        client, domain_id, project_id,
        name="DataQualityForm",
        description="Tracks data quality metrics for assets",
        model=smithy_model,
    )
    if form_name:
        summary["created"] += 1
    else:
        summary["skipped"] += 1

    # --- Assets ---
    print("\n📦 Creating assets...")
    assets = [
        ("CustomerTransactions", "Daily customer transaction records"),
        ("RevenueReport", "Monthly revenue aggregation report"),
        ("ChurnAnalysis", "Customer churn prediction dataset"),
    ]
    for name, description in assets:
        asset_id = create_asset(
            client, domain_id, project_id, name, description,
            type_identifier="amazon.datazone.RelationalTableAssetType",
        )
        if asset_id:
            summary["created"] += 1
        else:
            summary["skipped"] += 1

    # --- Summary ---
    print(f"\n{'='*50}")
    print(f"🌱 Seed Summary:")
    print(f"   Created: {summary['created']}")
    print(f"   Skipped: {summary['skipped']} (already exist)")
    print(f"   Failed:  {summary['failed']}")
    print(f"{'='*50}\n")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Seed a DataZone project with sample catalog resources"
    )
    parser.add_argument("--domain-id", required=True, help="DataZone domain ID")
    parser.add_argument("--project-id", required=True, help="DataZone project ID")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    args = parser.parse_args()

    try:
        seed(args.domain_id, args.project_id, args.region)
    except ClientError as e:
        print(f"\n❌ AWS API error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

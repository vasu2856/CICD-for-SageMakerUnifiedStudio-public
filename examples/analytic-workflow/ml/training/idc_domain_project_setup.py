#!/usr/bin/env python3
"""
Setup script for ML training example on IdC-based domains.

Adds MLflow and CloudWatch Logs permissions to the project role.
All operations are idempotent.

Usage:
    TEST_DOMAIN_REGION=us-east-1 python idc_domain_project_setup.py
"""

import argparse
import json
import os
import re
import sys

import boto3
import yaml

STAGE_NAME = "test-idc"


def substitute_env_vars(text):
    def replace(match):
        expr = match.group(1)
        if ":" in expr:
            var_name, default = expr.split(":", 1)
            return os.environ.get(var_name, default)
        return os.environ.get(expr, match.group(0))
    return re.sub(r"\$\{([^}]+)\}", replace, text)


def load_manifest(path):
    with open(path) as f:
        return yaml.safe_load(substitute_env_vars(f.read()))


def get_project_info(domain_id, project_name, region):
    dz = boto3.client("datazone", region_name=region)
    projects = dz.list_projects(domainIdentifier=domain_id)
    project_id = None
    for p in projects.get("items", []):
        if p["name"] == project_name:
            project_id = p["id"]
            break
    if not project_id:
        print(f"❌ Project '{project_name}' not found")
        return None
    print(f"📋 Project: {project_name} ({project_id})")

    envs = dz.list_environments(domainIdentifier=domain_id, projectIdentifier=project_id)
    for env in envs.get("items", []):
        if "tooling" not in env.get("name", "").lower():
            continue
        detail = dz.get_environment(domainIdentifier=domain_id, identifier=env["id"])
        resources = {r["name"]: r["value"] for r in detail.get("provisionedResources", [])}
        role_arn = resources.get("userRoleArn")
        if role_arn:
            print(f"   Role: {role_arn}")
            return {"project_id": project_id, "role_arn": role_arn, "role_name": role_arn.split("/")[-1]}
    print("❌ No userRoleArn found")
    return None


def setup_mlflow_permissions(role_name, region, dry_run=False):
    """Add inline policy for MLflow tracking server access."""
    iam = boto3.client("iam")
    policy_name = "MLflowTrackingAccess"

    print(f"\n🔬 MLflow permissions setup")
    try:
        iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        print(f"   ✓ MLflow policy already exists")
        return
    except iam.exceptions.NoSuchEntityException:
        pass

    if dry_run:
        print(f"   [DRY RUN] Would add MLflow inline policy")
        return

    account_id = boto3.client("sts").get_caller_identity()["Account"]
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "sagemaker-mlflow:*",
                    "Resource": f"arn:aws:sagemaker:{region}:{account_id}:mlflow-tracking-server/*",
                },
                {
                    "Sid": "MLflowArtifactS3Access",
                    "Effect": "Allow",
                    "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                    "Resource": [
                        f"arn:aws:s3:::smus-mlflow-artifacts-{account_id}-{region}",
                        f"arn:aws:s3:::smus-mlflow-artifacts-{account_id}-{region}/*",
                    ],
                },
            ],
        }),
    )
    print(f"   ✅ Added MLflow inline policy")


def setup_cw_logs_permissions(role_name, region, dry_run=False):
    """Add inline policy for CW Logs access."""
    iam = boto3.client("iam")
    policy_name = "MWAAServerlessLogsAccess"

    print(f"\n📋 CloudWatch Logs setup")
    try:
        iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        print(f"   ✓ CW Logs policy already exists")
        return
    except iam.exceptions.NoSuchEntityException:
        pass

    if dry_run:
        print(f"   [DRY RUN] Would add CW Logs inline policy")
        return

    account_id = boto3.client("sts").get_caller_identity()["Account"]
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:CreateLogGroup", "logs:PutLogEvents", "logs:GetLogEvents"],
                "Resource": f"arn:aws:logs:*:{account_id}:log-group:/aws/mwaa-serverless/*",
            }],
        }),
    )
    print(f"   ✅ Added CW Logs inline policy")


def main():
    parser = argparse.ArgumentParser(description="Setup IdC domain for ML training example")
    parser.add_argument("--manifest", default="examples/analytic-workflow/ml/training/manifest.yaml")
    parser.add_argument("--stage", default=STAGE_NAME)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    stage_config = manifest.get("stages", {}).get(args.stage)
    if not stage_config:
        print(f"❌ Stage '{args.stage}' not found")
        sys.exit(1)

    domain_config = stage_config["domain"]
    region = domain_config["region"]
    project_name = stage_config["project"]["name"]

    domain_id = domain_config.get("id")
    if not domain_id:
        domain_name = domain_config.get("name")
        dz = boto3.client("datazone", region_name=region)
        for d in dz.list_domains().get("items", []):
            if d["name"] == domain_name:
                domain_id = d["id"]
                break
        if not domain_id:
            print(f"❌ Domain '{domain_name}' not found")
            sys.exit(1)

    print(f"📋 Domain: {domain_id} ({region})")

    info = get_project_info(domain_id, project_name, region)
    if not info:
        sys.exit(1)

    setup_mlflow_permissions(info["role_name"], region, dry_run=args.dry_run)
    setup_cw_logs_permissions(info["role_name"], region, dry_run=args.dry_run)

    print(f"\n✅ Setup complete")


if __name__ == "__main__":
    main()

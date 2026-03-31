#!/usr/bin/env python3
"""Delete all MWAA Serverless workflows in a given region.

This script is used by the housekeeping workflow (smus-workflow-housekeeping.yml)
which runs every 3 days. MWAA Serverless enforces a quota on the number of versions
per workflow. Each deployment creates a new version, so workflows accumulate versions
over time and eventually hit the quota, causing deployments to fail. Deleting the
workflows periodically resets the version count and prevents this issue.

Usage:
    python tests/scripts/delete_all_workflows.py --region us-east-1
"""

import argparse
import subprocess
import sys


def delete_all_workflows(region: str) -> None:
    endpoint = f"https://airflow-serverless.{region}.api.aws/"

    print(f"🧹 Listing all MWAA workflows in {region}...")
    result = subprocess.run(
        [
            "aws", "mwaa-serverless", "list-workflows",
            "--endpoint-url", endpoint,
            "--region", region,
            "--output", "json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ Failed to list workflows: {result.stderr.strip()}")
        sys.exit(1)

    import json
    workflows = json.loads(result.stdout).get("Workflows", [])
    print(f"Found {len(workflows)} workflow(s) to delete")

    deleted = 0
    failed = 0
    for wf in workflows:
        arn = wf["WorkflowArn"]
        name = wf["Name"]
        del_result = subprocess.run(
            [
                "aws", "mwaa-serverless", "delete-workflow",
                "--endpoint-url", endpoint,
                "--region", region,
                "--workflow-arn", arn,
            ],
            capture_output=True,
            text=True,
        )
        if del_result.returncode == 0:
            print(f"  ✅ Deleted: {name}")
            deleted += 1
        else:
            print(f"  ❌ Failed to delete {name}: {del_result.stderr.strip()}")
            failed += 1

    print(f"\n✅ Housekeeping complete: {deleted} deleted, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete all MWAA Serverless workflows")
    parser.add_argument("--region", required=True, help="AWS region")
    args = parser.parse_args()
    delete_all_workflows(args.region)

"""Test that the ML training model artifacts were created."""
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone


def test_model_registered(smus_config):
    """Verify that model artifacts were created in S3 and registered in SageMaker Model Registry."""
    region = smus_config.get("region", os.environ.get("DOMAIN_REGION", "us-east-1"))
    account_id = smus_config.get("account_id", "")
    domain_id = smus_config.get("domain_id", "")
    project_id = smus_config.get("project_id", "")

    s3_client = boto3.client("s3", region_name=region)
    sagemaker_client = boto3.client("sagemaker", region_name=region)

    # Determine the correct S3 key prefix based on domain type
    # IdC domains use: dzd-.../project-id/shared/...
    # IAM domains use: shared/...
    base_prefix = "shared/"
    if domain_id and project_id:
        # Check if this is an IdC domain by looking for a bucket with the domain prefix
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            if "amazon-sagemaker" not in bucket["Name"] or region not in bucket["Name"]:
                continue
            try:
                idc_prefix = f"{domain_id}/{project_id}/shared/"
                s3_client.list_objects_v2(
                    Bucket=bucket["Name"], Prefix=idc_prefix, MaxKeys=1
                )
                resp = s3_client.list_objects_v2(
                    Bucket=bucket["Name"], Prefix=idc_prefix, MaxKeys=1
                )
                if resp.get("KeyCount", 0) > 0:
                    base_prefix = idc_prefix
                    break
            except ClientError:
                continue

    model_key = f"{base_prefix}ml/output/model-artifacts/latest/output/model.tar.gz"

    # Find the project bucket
    response = s3_client.list_buckets()
    project_bucket = None
    for bucket in response["Buckets"]:
        if "amazon-sagemaker" in bucket["Name"] and region in bucket["Name"]:
            try:
                s3_client.head_object(Bucket=bucket["Name"], Key=model_key)
                project_bucket = bucket["Name"]
                break
            except ClientError:
                continue

    assert project_bucket, f"No SageMaker bucket with model artifacts found at {model_key}"

    obj = s3_client.head_object(Bucket=project_bucket, Key=model_key)
    last_modified = obj["LastModified"]
    size = obj["ContentLength"]

    # Verify model was created recently (within last 2 hours)
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=2)

    print(f"✓ Model artifact found: s3://{project_bucket}/{model_key}")
    print(f"✓ Last modified: {last_modified}")
    print(f"✓ Size: {size:,} bytes")
    print(f"✓ Region: {region}")

    assert last_modified > cutoff_time, f"Model artifact is too old: {last_modified}"
    assert size > 0, "Model artifact is empty"

    print("✓ Model artifact is recent and valid")
    
    # Verify model is registered in SageMaker Model Registry
    model_groups = sagemaker_client.list_model_package_groups(
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=10
    )
    
    assert len(model_groups["ModelPackageGroupSummaryList"]) > 0, "No model package groups found"
    
    latest_group = model_groups["ModelPackageGroupSummaryList"][0]
    
    model_packages = sagemaker_client.list_model_packages(
        ModelPackageGroupName=latest_group["ModelPackageGroupName"],
        SortBy="CreationTime",
        SortOrder="Descending"
    )
    
    assert len(model_packages["ModelPackageSummaryList"]) > 0, "No models in package group"
    
    latest_model = model_packages["ModelPackageSummaryList"][0]
    model_created = latest_model["CreationTime"]
    
    print(f"✓ Model registered in SageMaker Model Registry")
    print(f"✓ Model Package: {latest_model['ModelPackageArn']}")
    print(f"✓ Created: {model_created}")
    print(f"✓ Status: {latest_model['ModelPackageStatus']}")
    
    assert model_created > cutoff_time, f"Latest model package is too old: {model_created}"
    assert latest_model["ModelPackageStatus"] == "Completed", f"Model status is {latest_model['ModelPackageStatus']}"

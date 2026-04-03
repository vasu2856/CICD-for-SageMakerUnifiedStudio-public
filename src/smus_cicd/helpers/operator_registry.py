"""
Operator registry for the destroy command.

Maps Airflow operator class names to deletion handlers. Each entry defines
which task field contains the resource name and how to delete that resource
type via boto3.

Adding support for a new operator type requires only a new dict entry —
no changes to the parser logic in the destroy command.
"""

import boto3
from botocore.exceptions import ClientError


class ResourceNotFoundError(Exception):
    """Raised when a resource targeted for deletion does not exist."""

    pass


def _delete_glue_job(resource_name: str, region: str) -> None:
    """
    Delete a Glue job by name.

    Args:
        resource_name: The name of the Glue job to delete.
        region: AWS region where the Glue job resides.

    Returns:
        None

    Raises:
        ResourceNotFoundError: When the Glue job does not exist.
        ClientError: For any other AWS API error.
    """
    try:
        boto3.client("glue", region_name=region).delete_job(JobName=resource_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityNotFoundException":
            raise ResourceNotFoundError(f"Glue job '{resource_name}' not found")
        raise


OPERATOR_REGISTRY = {
    "airflow.providers.amazon.aws.operators.glue.GlueJobOperator": {
        "resource_name_field": "job_name",
        "delete_fn": _delete_glue_job,
    },
}

"""Unit test for workflow version quota exceeded error handling."""

from unittest.mock import MagicMock, patch

import pytest

_PATCH_TARGET = "smus_cicd.helpers.airflow_serverless.create_airflow_serverless_client"
_WORKFLOW_ARN = "arn:aws:airflow-serverless:us-east-1:123:workflow/test-wf"
_CONFLICT = Exception("ConflictException: workflow already exists")
_QUOTA = Exception(
    "ServiceQuotaExceededException: Max workflows versions per workflow exceeded"
)


@patch(_PATCH_TARGET)
def test_create_workflow_quota_exceeded_raises_with_helpful_message(mock_factory, capsys):
    """ServiceQuotaExceededException: raises and prints actionable error with CLI commands."""
    client = MagicMock()
    client.create_workflow.side_effect = _CONFLICT
    client.update_workflow.side_effect = _QUOTA
    client.list_workflows.return_value = {
        "Workflows": [{"Name": "test-workflow", "WorkflowArn": _WORKFLOW_ARN}]
    }
    mock_factory.return_value = client

    from smus_cicd.helpers.airflow_serverless import create_workflow

    with pytest.raises(Exception):
        create_workflow(
            workflow_name="test-workflow",
            dag_s3_location="s3://bucket/key.yaml",
            role_arn="arn:aws:iam::123:role/role",
            region="us-east-1",
        )

    captured = capsys.readouterr()
    assert "version quota limit" in captured.out
    assert "delete-workflow" in captured.out
    # Workflow must NOT be deleted automatically
    client.delete_workflow.assert_not_called()

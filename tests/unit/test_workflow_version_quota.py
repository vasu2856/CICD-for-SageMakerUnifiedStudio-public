"""Unit tests for workflow version quota exceeded handling in create_workflow."""

from unittest.mock import MagicMock, patch

import pytest

# Target the installed package path since that's what gets executed
_PATCH_TARGET = "smus_cicd.helpers.airflow_serverless.create_airflow_serverless_client"

_WORKFLOW_ARN = "arn:aws:airflow-serverless:us-east-1:123:workflow/test-wf"

_CREATE_SUCCESS = {
    "WorkflowArn": _WORKFLOW_ARN,
    "WorkflowVersion": "1",
    "CreatedAt": "2024-01-01",
    "RevisionId": "rev-1",
}

_LIST_WORKFLOWS = {
    "Workflows": [{"Name": "test-workflow", "WorkflowArn": _WORKFLOW_ARN}]
}

_CONFLICT = Exception("ConflictException: workflow already exists")
_QUOTA = Exception(
    "ServiceQuotaExceededException: Max workflows versions per workflow exceeded"
)
_ACCESS_DENIED = Exception("AccessDeniedException: not authorized")
_VALIDATION = Exception("ValidationException: invalid params")


def _make_client():
    """Return a fresh mock client with sensible defaults."""
    client = MagicMock()
    client.create_workflow.return_value = _CREATE_SUCCESS
    client.list_workflows.return_value = _LIST_WORKFLOWS
    client.update_workflow.return_value = {"WorkflowVersion": "6"}
    client.delete_workflow.return_value = {}
    return client


def _invoke(**kwargs):
    """Call create_workflow with minimal required args plus any overrides."""
    from smus_cicd.helpers.airflow_serverless import create_workflow

    defaults = dict(
        workflow_name="test-workflow",
        dag_s3_location="s3://bucket/key.yaml",
        role_arn="arn:aws:iam::123:role/role",
        region="us-east-1",
    )
    defaults.update(kwargs)
    return create_workflow(**defaults)


@patch(_PATCH_TARGET)
def test_create_workflow_success(mock_factory):
    """Happy path: workflow created successfully on first attempt."""
    client = _make_client()
    mock_factory.return_value = client

    result = _invoke()

    assert result["success"] is True
    assert result["workflow_arn"] == _WORKFLOW_ARN
    client.create_workflow.assert_called_once()
    client.update_workflow.assert_not_called()
    client.delete_workflow.assert_not_called()


@patch(_PATCH_TARGET)
def test_create_workflow_conflict_updates_existing(mock_factory):
    """Workflow already exists: falls back to update_workflow."""
    client = _make_client()
    client.create_workflow.side_effect = _CONFLICT
    mock_factory.return_value = client

    result = _invoke()

    assert result["success"] is True
    assert result.get("updated") is True
    assert not result.get("recreated")
    client.update_workflow.assert_called_once()
    client.delete_workflow.assert_not_called()


@patch(_PATCH_TARGET)
def test_create_workflow_quota_exceeded_deletes_and_recreates(mock_factory):
    """ServiceQuotaExceededException on update: workflow deleted and recreated."""
    client = _make_client()
    # First create raises ConflictException; second (after delete) succeeds
    client.create_workflow.side_effect = [_CONFLICT, _CREATE_SUCCESS]
    client.update_workflow.side_effect = _QUOTA
    mock_factory.return_value = client

    result = _invoke()

    assert result["success"] is True
    assert result.get("recreated") is True
    assert result.get("already_exists") is True
    client.delete_workflow.assert_called_once_with(WorkflowArn=_WORKFLOW_ARN)
    assert client.create_workflow.call_count == 2


@patch(_PATCH_TARGET)
def test_create_workflow_quota_exceeded_logs_warning(mock_factory, capsys):
    """ServiceQuotaExceededException: warning message printed to stdout."""
    client = _make_client()
    client.create_workflow.side_effect = [_CONFLICT, _CREATE_SUCCESS]
    client.update_workflow.side_effect = _QUOTA
    mock_factory.return_value = client

    _invoke()

    captured = capsys.readouterr()
    assert "version quota limit" in captured.out
    assert "Deleting and recreating" in captured.out


@patch(_PATCH_TARGET)
def test_create_workflow_non_quota_update_error_raises(mock_factory):
    """Non-quota update errors are re-raised without deleting the workflow."""
    client = _make_client()
    client.create_workflow.side_effect = _CONFLICT
    client.update_workflow.side_effect = _ACCESS_DENIED
    mock_factory.return_value = client

    with pytest.raises(Exception, match="AccessDeniedException"):
        _invoke()

    client.delete_workflow.assert_not_called()


@patch(_PATCH_TARGET)
def test_create_workflow_non_conflict_error_raises(mock_factory):
    """Non-conflict create errors are raised immediately without update/delete."""
    client = _make_client()
    client.create_workflow.side_effect = _VALIDATION
    mock_factory.return_value = client

    with pytest.raises(Exception, match="ValidationException"):
        _invoke()

    client.update_workflow.assert_not_called()
    client.delete_workflow.assert_not_called()

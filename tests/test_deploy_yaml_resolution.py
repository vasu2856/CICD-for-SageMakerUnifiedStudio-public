"""Test that ContextResolver resolves variables in workflow YAML content."""

from unittest.mock import patch

from smus_cicd.helpers.context_resolver import ContextResolver


@patch("smus_cicd.helpers.context_resolver.ContextResolver._build_context")
def test_resolve_yaml_with_proj_variables(mock_build_context):
    """Test that {proj.*} variables are resolved in YAML content."""
    mock_build_context.return_value = {
        "proj": {
            "name": "test-project",
            "iam_role_name": "AmazonSageMakerUserIAMExecutionRole",
            "connection": {},
        },
        "domain": {
            "id": "test-domain-id",
            "name": "test-domain",
            "region": "us-east-1",
        },
        "stage": {"name": "test"},
        "env": {},
    }

    resolver = ContextResolver(
        project_name="test-project",
        domain_id="test-domain-id",
        region="us-east-1",
        domain_name="test-domain",
        stage_name="test",
        env_vars={},
    )

    content = """\
tasks:
  - name: test_task
    iam_role_name: '{proj.iam_role_name}'
    project_name: '{proj.name}'
"""

    resolved = resolver.resolve(content)

    assert "AmazonSageMakerUserIAMExecutionRole" in resolved
    assert "{proj.iam_role_name}" not in resolved
    assert "test-project" in resolved
    assert "{proj.name}" not in resolved


@patch("smus_cicd.helpers.context_resolver.ContextResolver._build_context")
def test_resolve_yaml_without_variables(mock_build_context):
    """Test that YAML content without variables passes through unchanged."""
    mock_build_context.return_value = {
        "proj": {"name": "test-project", "connection": {}},
        "domain": {
            "id": "test-domain-id",
            "name": "test-domain",
            "region": "us-east-1",
        },
        "stage": {"name": ""},
        "env": {},
    }

    resolver = ContextResolver(
        project_name="test-project",
        domain_id="test-domain-id",
        region="us-east-1",
        domain_name="test-domain",
        env_vars={},
    )

    content = """\
tasks:
  - name: test_task
    iam_role_name: 'StaticRole'
"""

    resolved = resolver.resolve(content)

    assert resolved == content
    assert "StaticRole" in resolved

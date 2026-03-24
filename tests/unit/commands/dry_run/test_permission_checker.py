"""Unit tests for PermissionChecker.

Tests all permission types, denied permissions, API failures,
SimulatePrincipalPolicy fallback to WARNING, bootstrap action permissions,
and Glue permissions for catalog Glue references.

Requirements: 10.3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from smus_cicd.commands.dry_run.checkers.permission_checker import (
    BOOTSTRAP_PERMISSION_MAP,
    PermissionChecker,
)
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Stub dataclasses mirroring the real manifest models
# ---------------------------------------------------------------------------


@dataclass
class _StorageConfig:
    name: str
    connectionName: Optional[str] = "default.s3_shared"
    targetDirectory: str = ""


@dataclass
class _GitTargetConfig:
    name: str
    connectionName: str = "default.git"
    targetDirectory: str = ""


@dataclass
class _DeploymentConfiguration:
    storage: List[_StorageConfig] = field(default_factory=list)
    git: List[_GitTargetConfig] = field(default_factory=list)
    catalog: Optional[Dict[str, Any]] = None
    quicksight: Optional[Dict[str, Any]] = None


@dataclass
class _QuickSightDashboardConfig:
    name: str
    type: str = "dashboard"


@dataclass
class _ProjectConfig:
    name: str = "test-project"
    create: bool = False
    role: Optional[Dict[str, Any]] = None


@dataclass
class _DomainConfig:
    region: str = "us-east-1"


@dataclass
class _BootstrapAction:
    type: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _BootstrapConfig:
    actions: List[_BootstrapAction] = field(default_factory=list)


@dataclass
class _TargetConfig:
    project: _ProjectConfig = field(default_factory=_ProjectConfig)
    domain: _DomainConfig = field(default_factory=_DomainConfig)
    stage: str = "dev"
    deployment_configuration: Optional[_DeploymentConfiguration] = None
    environment_variables: Optional[dict] = None
    bootstrap: Optional[_BootstrapConfig] = None
    quicksight: List[_QuickSightDashboardConfig] = field(default_factory=list)


def _make_context(
    storage_names=None,
    git_names=None,
    has_catalog=False,
    has_iam_role=False,
    quicksight_dashboards=None,
    bootstrap_actions=None,
    catalog_data=None,
    catalog_with_glue=False,
) -> DryRunContext:
    """Build a DryRunContext with the given features enabled."""
    storage = [_StorageConfig(name=n) for n in (storage_names or [])]
    git = [_GitTargetConfig(name=n) for n in (git_names or [])]
    deploy_cfg = _DeploymentConfiguration(
        storage=storage,
        git=git,
        catalog={"enabled": True} if has_catalog else None,
    )
    project = _ProjectConfig(
        role={"name": "test-role", "policies": []} if has_iam_role else None
    )
    qs = [_QuickSightDashboardConfig(name=n) for n in (quicksight_dashboards or [])]
    bootstrap = None
    if bootstrap_actions:
        bootstrap = _BootstrapConfig(
            actions=[_BootstrapAction(type=t) for t in bootstrap_actions]
        )

    target = _TargetConfig(
        project=project,
        deployment_configuration=deploy_cfg,
        bootstrap=bootstrap,
        quicksight=qs,
    )

    # Build catalog_data with Glue references if requested
    cd = catalog_data
    if catalog_with_glue and cd is None:
        cd = {
            "metadata": {},
            "resources": [
                {
                    "type": "assets",
                    "name": "test-asset",
                    "identifier": "id-1",
                    "formsInput": [
                        {
                            "typeIdentifier": "amazon.datazone.GlueTableFormType",
                            "content": json.dumps(
                                {
                                    "databaseName": "mydb",
                                    "tableName": "mytable",
                                }
                            ),
                        }
                    ],
                }
            ],
        }

    return DryRunContext(
        manifest_file="manifest.yaml",
        target_config=target,
        config={
            "region": "us-east-1",
            "account_id": "123456789012",
            "domain_id": "dzd_test",
        },
        catalog_data=cd if has_catalog or catalog_with_glue else None,
    )


def _mock_simulate_all_allowed(caller_arn, actions, resource_arns):
    """Return a simulate_principal_policy response where all actions are allowed."""
    return {
        "EvaluationResults": [
            {
                "EvalActionName": action,
                "EvalDecision": "allowed",
            }
            for action in actions
        ]
    }


def _mock_simulate_all_denied(caller_arn, actions, resource_arns):
    """Return a simulate_principal_policy response where all actions are denied."""
    return {
        "EvaluationResults": [
            {
                "EvalActionName": action,
                "EvalDecision": "implicitDeny",
            }
            for action in actions
        ]
    }


@pytest.fixture
def checker():
    return PermissionChecker()


# -----------------------------------------------------------------------
# Test: No target config → skip with WARNING
# -----------------------------------------------------------------------


class TestPermissionCheckerNoConfig:
    """Tests when manifest/target is not loaded."""

    def test_no_target_config_produces_warning(self, checker):
        context = DryRunContext(manifest_file="m.yaml", target_config=None)
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "skipping" in findings[0].message.lower()

    def test_no_config_dict_produces_warning(self, checker):
        context = DryRunContext(
            manifest_file="m.yaml",
            target_config=_TargetConfig(),
            config=None,
        )
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING


# -----------------------------------------------------------------------
# Test: STS caller identity failure
# -----------------------------------------------------------------------


class TestPermissionCheckerCallerIdentity:
    """Tests for STS get_caller_identity."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_sts_failure_returns_error(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("STS unavailable")
        mock_boto3.client.return_value = mock_sts

        context = _make_context(storage_names=["data"])
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "caller identity" in error_findings[0].message.lower()

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_sts_success_records_caller_arn(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["data"])
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        caller_findings = [
            f for f in ok_findings if "caller identity" in f.message.lower()
        ]
        assert len(caller_findings) == 1

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_assumed_role_arn_converted_to_iam_role(
        self, mock_conns, mock_boto3, checker
    ):
        """STS assumed-role ARN should be converted to IAM role ARN for
        SimulatePrincipalPolicy."""
        mock_conns.return_value = {"default.s3_shared": {"s3Uri": "s3://bucket"}}
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::592756948959:assumed-role/Admin/session-name"
        }
        mock_iam = MagicMock()
        captured_source_arns = []

        def capture_simulate(**kw):
            captured_source_arns.append(kw["PolicySourceArn"])
            return _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )

        mock_iam.simulate_principal_policy.side_effect = capture_simulate
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["data"])
        checker.check(context)

        # All calls should use the converted IAM role ARN
        for arn in captured_source_arns:
            assert arn == "arn:aws:iam::592756948959:role/Admin"
            assert "assumed-role" not in arn
            assert "sts" not in arn


# -----------------------------------------------------------------------
# Test: S3 permissions (Req 4.1)
# -----------------------------------------------------------------------


class TestPermissionCheckerS3:
    """Tests for S3 storage permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_permissions_checked(self, mock_conns, mock_boto3, checker):
        mock_conns.return_value = {
            "default.s3_shared": {"s3Uri": "s3://real-bucket-123"}
        }
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["my-data"])
        findings = checker.check(context)

        # Should have checked s3:PutObject and s3:GetObject
        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("s3:PutObject" in m for m in ok_msgs)
        assert any("s3:GetObject" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_denied_produces_error(self, mock_conns, mock_boto3, checker):
        mock_conns.return_value = {
            "default.s3_shared": {"s3Uri": "s3://real-bucket-123"}
        }
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_denied(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["bucket1"])
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) >= 2  # s3:PutObject + s3:GetObject denied

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_uses_real_bucket_arn(self, mock_conns, mock_boto3, checker):
        """Verify the S3 ARN uses the resolved bucket name, not the connection suffix."""
        mock_conns.return_value = {
            "default.s3_shared": {"s3Uri": "s3://my-actual-bucket"}
        }
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        captured_arns = []

        def capture_simulate(**kw):
            captured_arns.extend(kw["ResourceArns"])
            return _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )

        mock_iam.simulate_principal_policy.side_effect = capture_simulate
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["data"])
        checker.check(context)

        s3_arns = [a for a in captured_arns if a.startswith("arn:aws:s3")]
        assert any("my-actual-bucket" in a for a in s3_arns)
        # Should NOT contain the old naive split result
        assert not any("s3_shared" in a for a in s3_arns)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_unresolved_falls_back_to_wildcard(
        self, mock_conns, mock_boto3, checker
    ):
        """When connection can't be resolved, fall back to wildcard S3 ARN."""
        mock_conns.return_value = None
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        captured_arns = []

        def capture_simulate(**kw):
            captured_arns.extend(kw["ResourceArns"])
            return _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )

        mock_iam.simulate_principal_policy.side_effect = capture_simulate
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["data"])
        checker.check(context)

        s3_arns = [a for a in captured_arns if a.startswith("arn:aws:s3")]
        assert any("*" in a for a in s3_arns)


# -----------------------------------------------------------------------
# Test: DataZone permissions (Req 4.2)
# -----------------------------------------------------------------------


class TestPermissionCheckerDataZone:
    """Tests for DataZone permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_datazone_permissions_checked(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context()
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("datazone:GetDomain" in m for m in ok_msgs)
        assert any("datazone:GetProject" in m for m in ok_msgs)
        assert any("datazone:SearchListings" in m for m in ok_msgs)


# -----------------------------------------------------------------------
# Test: Catalog permissions (Req 4.3, 4.7)
# -----------------------------------------------------------------------


class TestPermissionCheckerCatalog:
    """Tests for catalog import and grant permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_catalog_permissions_checked(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(has_catalog=True)
        context.catalog_data = {"metadata": {}, "resources": []}
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        # Catalog import permissions
        assert any("datazone:CreateAsset" in m for m in ok_msgs)
        assert any("datazone:CreateGlossary" in m for m in ok_msgs)
        assert any("datazone:CreateGlossaryTerm" in m for m in ok_msgs)
        assert any("datazone:CreateFormType" in m for m in ok_msgs)
        # Catalog grant permissions
        assert any("datazone:CreateSubscriptionGrant" in m for m in ok_msgs)
        assert any("datazone:GetSubscriptionGrant" in m for m in ok_msgs)
        assert any("datazone:CreateSubscriptionRequest" in m for m in ok_msgs)


# -----------------------------------------------------------------------
# Test: IAM permissions (Req 4.4)
# -----------------------------------------------------------------------


class TestPermissionCheckerIAM:
    """Tests for IAM role creation permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_iam_permissions_checked_when_role_configured(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(has_iam_role=True)
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("iam:CreateRole" in m for m in ok_msgs)
        assert any("iam:AttachRolePolicy" in m for m in ok_msgs)
        assert any("iam:PutRolePolicy" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_no_iam_permissions_when_no_role(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(has_iam_role=False)
        findings = checker.check(context)

        all_msgs = [f.message for f in findings]
        assert not any("iam:CreateRole" in m for m in all_msgs)


# -----------------------------------------------------------------------
# Test: QuickSight permissions (Req 4.5)
# -----------------------------------------------------------------------


class TestPermissionCheckerQuickSight:
    """Tests for QuickSight permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_quicksight_permissions_checked(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(quicksight_dashboards=["dash1"])
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("quicksight:DescribeDashboard" in m for m in ok_msgs)
        assert any("quicksight:CreateDashboard" in m for m in ok_msgs)
        assert any("quicksight:UpdateDashboard" in m for m in ok_msgs)


# -----------------------------------------------------------------------
# Test: Bootstrap action permissions (Req 4.8–4.12)
# -----------------------------------------------------------------------


class TestPermissionCheckerBootstrap:
    """Tests for bootstrap action permission verification."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_workflow_create_permissions(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(bootstrap_actions=["workflow.create"])
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("airflow-serverless:CreateWorkflow" in m for m in ok_msgs)
        assert any("airflow-serverless:GetWorkflow" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_all_bootstrap_action_types(self, mock_boto3, checker):
        """Verify all bootstrap action types from BOOTSTRAP_PERMISSION_MAP are checked."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        all_action_types = list(BOOTSTRAP_PERMISSION_MAP.keys())
        context = _make_context(bootstrap_actions=all_action_types)
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        # Every IAM action from every bootstrap type should appear
        for action_type, iam_actions in BOOTSTRAP_PERMISSION_MAP.items():
            for iam_action in iam_actions:
                assert any(
                    iam_action in m for m in ok_msgs
                ), f"Missing permission check for {iam_action} (from {action_type})"


# -----------------------------------------------------------------------
# Test: Glue permissions for catalog Glue references (Req 4.13)
# -----------------------------------------------------------------------


class TestPermissionCheckerGlue:
    """Tests for Glue permission verification when catalog has Glue references."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_glue_permissions_added_for_glue_refs(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(catalog_with_glue=True)
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("glue:GetTable" in m for m in ok_msgs)
        assert any("glue:GetDatabase" in m for m in ok_msgs)
        assert any("glue:GetPartitions" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_no_glue_permissions_without_glue_refs(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        # Catalog data without Glue references
        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "resources": [
                {
                    "type": "glossaries",
                    "name": "test-glossary",
                    "identifier": "g-1",
                }
            ],
        }
        findings = checker.check(context)

        all_msgs = [f.message for f in findings]
        assert not any("glue:GetTable" in m for m in all_msgs)


# -----------------------------------------------------------------------
# Test: SimulatePrincipalPolicy AccessDenied fallback (Req 4.6)
# -----------------------------------------------------------------------


class TestPermissionCheckerAccessDeniedFallback:
    """Tests for fallback to WARNING when SimulatePrincipalPolicy is denied."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_access_denied_produces_warning_not_error(self, mock_boto3, checker):
        from botocore.exceptions import ClientError

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "SimulatePrincipalPolicy",
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["bucket1"])
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        warning_findings = [f for f in findings if f.severity == Severity.WARNING]

        # No ERROR findings for the simulation failure
        sim_errors = [
            f for f in error_findings if "SimulatePrincipalPolicy" in f.message
        ]
        assert len(sim_errors) == 0

        # Should have WARNING findings instead
        sim_warnings = [f for f in warning_findings if "AccessDenied" in f.message]
        assert len(sim_warnings) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_access_denied_exception_also_produces_warning(self, mock_boto3, checker):
        from botocore.exceptions import ClientError

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "Not authorized",
                }
            },
            "SimulatePrincipalPolicy",
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["bucket1"])
        findings = checker.check(context)

        warning_findings = [f for f in findings if f.severity == Severity.WARNING]
        assert any("AccessDeniedException" in f.message for f in warning_findings)


# -----------------------------------------------------------------------
# Test: Empty deployment config
# -----------------------------------------------------------------------


class TestPermissionCheckerEmptyConfig:
    """Tests for empty deployment configuration."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_empty_config_still_checks_datazone(self, mock_boto3, checker):
        """Even with no storage/catalog/etc, DataZone base permissions are checked."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context()
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("datazone:GetDomain" in m for m in ok_msgs)


# -----------------------------------------------------------------------
# Test: Mixed denied and allowed permissions (Req 4.6)
# -----------------------------------------------------------------------


class TestPermissionCheckerMixedResults:
    """Tests for mixed allowed/denied simulation results."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_mixed_results_report_each_action(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()

        def mixed_simulate(**kw):
            results = []
            for action in kw["ActionNames"]:
                if "PutObject" in action:
                    results.append(
                        {"EvalActionName": action, "EvalDecision": "implicitDeny"}
                    )
                else:
                    results.append(
                        {"EvalActionName": action, "EvalDecision": "allowed"}
                    )
            return {"EvaluationResults": results}

        mock_iam.simulate_principal_policy.side_effect = mixed_simulate
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["bucket1"])
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        ok_findings = [f for f in findings if f.severity == Severity.OK]

        # s3:PutObject should be denied
        put_errors = [f for f in error_findings if "s3:PutObject" in f.message]
        assert len(put_errors) >= 1

        # s3:GetObject should be allowed
        get_ok = [f for f in ok_findings if "s3:GetObject" in f.message]
        assert len(get_ok) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_denied_finding_contains_action_and_resource(self, mock_boto3, checker):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_denied(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["mybucket"])
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        for ef in error_findings:
            # Each denied finding should contain the action name and resource ARN
            assert ef.resource is not None
            assert ef.details is not None
            assert "action" in ef.details
            assert "resource" in ef.details


# -----------------------------------------------------------------------
# Test: BOOTSTRAP_PERMISSION_MAP completeness
# -----------------------------------------------------------------------


class TestBootstrapPermissionMap:
    """Tests for the BOOTSTRAP_PERMISSION_MAP constant."""

    def test_all_expected_action_types_present(self):
        expected_types = [
            "workflow.create",
            "workflow.run",
            "workflow.logs",
            "workflow.monitor",
            "quicksight.refresh_dataset",
            "eventbridge.put_events",
            "project.create_environment",
            "project.create_connection",
            "catalog.dependency_check",
        ]
        for action_type in expected_types:
            assert (
                action_type in BOOTSTRAP_PERMISSION_MAP
            ), f"Missing action type: {action_type}"

    def test_each_action_type_has_permissions(self):
        for action_type, perms in BOOTSTRAP_PERMISSION_MAP.items():
            assert isinstance(perms, list)
            assert len(perms) > 0, f"No permissions for {action_type}"
            for p in perms:
                assert ":" in p, f"Invalid IAM action format: {p}"


# -----------------------------------------------------------------------
# Test: DataZone policy grant checks
# -----------------------------------------------------------------------


class TestPermissionCheckerDataZoneGrants:
    """Tests for DataZone policy grant verification on domain units."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch(
        "smus_cicd.commands.dry_run.checkers.permission_checker.PermissionChecker._check_datazone_policy_grants"
    )
    def test_grant_check_called_when_catalog_data_present(
        self, mock_grant_check, mock_boto3, checker
    ):
        """Verify _check_datazone_policy_grants is called during check()."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(has_catalog=True)
        context.catalog_data = {"metadata": {}, "glossaries": [{"name": "g1"}]}
        checker.check(context)

        mock_grant_check.assert_called_once()

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_no_grant_check_without_catalog_data(self, mock_boto3, checker):
        """Grant check should be skipped when catalog_data is None."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context()
        findings = checker.check(context)

        # No grant-related findings should appear
        grant_findings = [f for f in findings if "policy grant" in f.message.lower()]
        assert len(grant_findings) == 0

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch("smus_cicd.helpers.utils._resolve_domain_id")
    @patch("smus_cicd.helpers.datazone.get_project_id_by_name")
    def test_missing_grant_produces_error(
        self, mock_get_project_id, mock_resolve_domain, mock_boto3, checker
    ):
        """Missing policy grant should produce an ERROR finding."""
        mock_resolve_domain.return_value = "dzd-test123"
        mock_get_project_id.return_value = "proj-abc"

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_dz = MagicMock()
        mock_dz.get_project.return_value = {"domainUnitId": "du-xyz"}
        # All grants missing (empty grantList)
        mock_dz.list_policy_grants.return_value = {"grantList": []}

        mock_boto3.client.side_effect = lambda svc, **kw: {
            "sts": mock_sts,
            "iam": mock_iam,
            "datazone": mock_dz,
        }.get(svc, MagicMock())

        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "glossaries": [{"name": "g1", "identifier": "g-1"}],
            "glossaryTerms": [],
            "formTypes": [{"name": "ft1", "identifier": "ft-1"}],
            "assetTypes": [{"name": "at1", "identifier": "at-1"}],
        }
        findings = checker.check(context)

        error_findings = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "policy grant" in f.message.lower()
        ]
        # Should have errors for CREATE_GLOSSARY, CREATE_FORM_TYPE, CREATE_ASSET_TYPE
        assert len(error_findings) == 3
        grant_types = {f.resource for f in error_findings}
        assert grant_types == {
            "CREATE_GLOSSARY",
            "CREATE_FORM_TYPE",
            "CREATE_ASSET_TYPE",
        }

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch("smus_cicd.helpers.utils._resolve_domain_id")
    @patch("smus_cicd.helpers.datazone.get_project_id_by_name")
    def test_present_grant_produces_ok(
        self, mock_get_project_id, mock_resolve_domain, mock_boto3, checker
    ):
        """Existing policy grant should produce an OK finding."""
        mock_resolve_domain.return_value = "dzd-test123"
        mock_get_project_id.return_value = "proj-abc"

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_dz = MagicMock()
        mock_dz.get_project.return_value = {"domainUnitId": "du-xyz"}
        # All grants present
        mock_dz.list_policy_grants.return_value = {"grantList": [{"detail": {}}]}

        mock_boto3.client.side_effect = lambda svc, **kw: {
            "sts": mock_sts,
            "iam": mock_iam,
            "datazone": mock_dz,
        }.get(svc, MagicMock())

        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "glossaries": [{"name": "g1", "identifier": "g-1"}],
            "formTypes": [{"name": "ft1", "identifier": "ft-1"}],
            "assetTypes": [{"name": "at1", "identifier": "at-1"}],
        }
        findings = checker.check(context)

        grant_ok = [
            f
            for f in findings
            if f.severity == Severity.OK and "policy grant" in f.message.lower()
        ]
        assert len(grant_ok) == 3

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch("smus_cicd.helpers.utils._resolve_domain_id")
    @patch("smus_cicd.helpers.datazone.get_project_id_by_name")
    def test_grant_only_checked_for_present_resource_types(
        self, mock_get_project_id, mock_resolve_domain, mock_boto3, checker
    ):
        """Grants should only be checked for resource types present in catalog."""
        mock_resolve_domain.return_value = "dzd-test123"
        mock_get_project_id.return_value = "proj-abc"

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_dz = MagicMock()
        mock_dz.get_project.return_value = {"domainUnitId": "du-xyz"}
        mock_dz.list_policy_grants.return_value = {"grantList": []}

        mock_boto3.client.side_effect = lambda svc, **kw: {
            "sts": mock_sts,
            "iam": mock_iam,
            "datazone": mock_dz,
        }.get(svc, MagicMock())

        # Only glossaries — no formTypes or assetTypes
        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "glossaries": [{"name": "g1", "identifier": "g-1"}],
        }
        findings = checker.check(context)

        error_findings = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "policy grant" in f.message.lower()
        ]
        # Only CREATE_GLOSSARY should be flagged
        assert len(error_findings) == 1
        assert error_findings[0].resource == "CREATE_GLOSSARY"

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch("smus_cicd.helpers.utils._resolve_domain_id")
    def test_domain_resolution_failure_produces_warning(
        self, mock_resolve_domain, mock_boto3, checker
    ):
        """Failed domain resolution should produce WARNING, not crash."""
        mock_resolve_domain.side_effect = Exception("Cannot resolve domain")

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "glossaries": [{"name": "g1"}],
        }
        findings = checker.check(context)

        warn_findings = [
            f
            for f in findings
            if f.severity == Severity.WARNING
            and "domain" in f.message.lower()
            and "grant" in f.message.lower()
        ]
        assert len(warn_findings) == 1

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch("smus_cicd.helpers.utils._resolve_domain_id")
    @patch("smus_cicd.helpers.datazone.get_project_id_by_name")
    def test_access_denied_on_list_grants_produces_warning(
        self, mock_get_project_id, mock_resolve_domain, mock_boto3, checker
    ):
        """AccessDenied on list_policy_grants should produce WARNING."""
        from botocore.exceptions import ClientError

        mock_resolve_domain.return_value = "dzd-test123"
        mock_get_project_id.return_value = "proj-abc"

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"],
                kw["ActionNames"],
                kw["ResourceArns"],
            )
        )
        mock_dz = MagicMock()
        mock_dz.get_project.return_value = {"domainUnitId": "du-xyz"}
        mock_dz.list_policy_grants.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListPolicyGrants",
        )

        mock_boto3.client.side_effect = lambda svc, **kw: {
            "sts": mock_sts,
            "iam": mock_iam,
            "datazone": mock_dz,
        }.get(svc, MagicMock())

        context = _make_context(has_catalog=True)
        context.catalog_data = {
            "metadata": {},
            "glossaries": [{"name": "g1", "identifier": "g-1"}],
        }
        findings = checker.check(context)

        warn_findings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "access denied" in f.message.lower()
        ]
        assert len(warn_findings) >= 1
        # Should NOT have ERROR for this grant
        grant_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "CREATE_GLOSSARY" in f.message
        ]
        assert len(grant_errors) == 0


# -----------------------------------------------------------------------
# Test: Skip permissions for missing bundle resources (Task 5)
# -----------------------------------------------------------------------


class TestPermissionCheckerSkipMissingResources:
    """Tests that permission checks are skipped when the bundle doesn't
    contain files for the declared resource type."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_permissions_skipped_when_bundle_has_no_storage_files(
        self, mock_conns, mock_boto3, checker
    ):
        """S3 permissions should be skipped when bundle_files is populated
        but contains no files matching any storage item."""
        mock_conns.return_value = {"default.s3_shared": {"s3Uri": "s3://real-bucket"}}
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        captured_arns = []

        def capture_simulate(**kw):
            captured_arns.extend(kw["ResourceArns"])
            return _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )

        mock_iam.simulate_principal_policy.side_effect = capture_simulate
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["my-data"])
        # Bundle is populated but has NO storage files
        context.bundle_files = {"catalog/catalog_export.json", "README.md"}
        findings = checker.check(context)

        # No S3 ARNs should have been checked
        s3_arns = [a for a in captured_arns if a.startswith("arn:aws:s3")]
        assert len(s3_arns) == 0

        all_msgs = [f.message for f in findings]
        assert not any("s3:PutObject" in m for m in all_msgs)
        assert not any("s3:GetObject" in m for m in all_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_permissions_checked_when_bundle_has_storage_files(
        self, mock_conns, mock_boto3, checker
    ):
        """S3 permissions should still be checked when bundle has matching
        storage files."""
        mock_conns.return_value = {"default.s3_shared": {"s3Uri": "s3://real-bucket"}}
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["my-data"])
        # Bundle has files under the storage item name
        context.bundle_files = {"my-data/file1.csv", "my-data/file2.csv"}
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("s3:PutObject" in m for m in ok_msgs)
        assert any("s3:GetObject" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_quicksight_permissions_skipped_when_bundle_has_no_qs_files(
        self, mock_boto3, checker
    ):
        """QuickSight permissions should be skipped when bundle_files is
        populated but contains no quicksight/ files."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(quicksight_dashboards=["dash1"])
        # Bundle is populated but has NO QuickSight files
        context.bundle_files = {"my-data/file1.csv", "README.md"}
        findings = checker.check(context)

        all_msgs = [f.message for f in findings]
        assert not any("quicksight:DescribeDashboard" in m for m in all_msgs)
        assert not any("quicksight:CreateDashboard" in m for m in all_msgs)
        assert not any("quicksight:UpdateDashboard" in m for m in all_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_quicksight_permissions_checked_when_bundle_has_qs_files(
        self, mock_boto3, checker
    ):
        """QuickSight permissions should be checked when bundle has
        quicksight/ files."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(quicksight_dashboards=["dash1"])
        # Bundle has QuickSight files
        context.bundle_files = {"quicksight/dashboard.qs", "README.md"}
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("quicksight:DescribeDashboard" in m for m in ok_msgs)

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    @patch.object(PermissionChecker, "_get_project_connections")
    def test_s3_permissions_still_checked_when_bundle_not_explored(
        self, mock_conns, mock_boto3, checker
    ):
        """When bundle_files is empty (bundle not yet explored), S3
        permissions should still be checked — we don't know what's in
        the bundle yet."""
        mock_conns.return_value = {"default.s3_shared": {"s3Uri": "s3://real-bucket"}}
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        context = _make_context(storage_names=["my-data"])
        # bundle_files is empty (default) — bundle not explored yet
        assert len(context.bundle_files) == 0
        findings = checker.check(context)

        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("s3:PutObject" in m for m in ok_msgs)


# -----------------------------------------------------------------------
# DataZone ARN resolution — wildcard fallback
# -----------------------------------------------------------------------


class TestDataZoneArnWildcardFallback:
    """When domain_id or account_id are wildcards, the DataZone resource ARN
    should be ``"*"`` — not a partial-wildcard like
    ``arn:aws:datazone:…:*:domain/*`` which causes ``SimulatePrincipalPolicy``
    to return ``implicitDeny`` even for admin roles."""

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_wildcard_domain_uses_star_arn(self, mock_boto3, checker):
        """When domain_id defaults to '*', the resource ARN passed to
        SimulatePrincipalPolicy should be '*' (not a constructed ARN)."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        # Config with no domain_id → defaults to "*"
        ctx = DryRunContext(
            manifest_file="manifest.yaml",
            target_config=_TargetConfig(
                project=_ProjectConfig(role=None),
                deployment_configuration=_DeploymentConfiguration(
                    storage=[], git=[], catalog=None
                ),
                bootstrap=None,
                quicksight=[],
            ),
            config={"region": "us-east-1", "account_id": "123456789012"},
            catalog_data=None,
        )
        checker.check(ctx)

        # Verify SimulatePrincipalPolicy was called with "*" as the resource
        calls = mock_iam.simulate_principal_policy.call_args_list
        resource_arns = [c.kwargs["ResourceArns"][0] for c in calls]
        # DataZone actions should use "*", not a partial-wildcard ARN
        assert "*" in resource_arns
        assert not any(
            "arn:aws:datazone" in a and ":*:" in a for a in resource_arns
        ), "Should not construct partial-wildcard DataZone ARNs"

    @patch("smus_cicd.commands.dry_run.checkers.permission_checker.boto3")
    def test_real_domain_uses_full_arn(self, mock_boto3, checker):
        """When domain_id and account_id are real values, a fully-qualified
        DataZone ARN should be used."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456789012:user/testuser"
        }
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = (
            lambda **kw: _mock_simulate_all_allowed(
                kw["PolicySourceArn"], kw["ActionNames"], kw["ResourceArns"]
            )
        )
        mock_boto3.client.side_effect = lambda svc, **kw: (
            mock_sts if svc == "sts" else mock_iam
        )

        # Config with real domain_id and account_id
        ctx = DryRunContext(
            manifest_file="manifest.yaml",
            target_config=_TargetConfig(
                project=_ProjectConfig(role=None),
                deployment_configuration=_DeploymentConfiguration(
                    storage=[], git=[], catalog=None
                ),
                bootstrap=None,
                quicksight=[],
            ),
            config={
                "region": "us-east-1",
                "account_id": "123456789012",
                "domain_id": "dzd_abc123",
            },
            catalog_data=None,
        )
        checker.check(ctx)

        calls = mock_iam.simulate_principal_policy.call_args_list
        resource_arns = [c.kwargs["ResourceArns"][0] for c in calls]
        expected_arn = "arn:aws:datazone:us-east-1:123456789012:domain/dzd_abc123"
        assert expected_arn in resource_arns

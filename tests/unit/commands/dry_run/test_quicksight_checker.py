"""Unit tests for QuickSightChecker.

Tests QuickSight deployment simulation: no config, dashboards found via
lookup, dashboards not found, local asset bundles, missing account ID,
and API errors.

Requirements: 5.5, 10.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pytest

from smus_cicd.commands.dry_run.checkers.quicksight_checker import QuickSightChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Stub dataclasses mirroring the real manifest models
# ---------------------------------------------------------------------------


@dataclass
class _DomainConfig:
    region: str = "us-east-1"


@dataclass
class _QuickSightDashboardConfig:
    name: str = ""
    type: str = "dashboard"
    assetBundle: str = "export"


@dataclass
class _ContentConfig:
    quicksight: List[_QuickSightDashboardConfig] = field(default_factory=list)


@dataclass
class _TargetConfig:
    domain: _DomainConfig = field(default_factory=_DomainConfig)
    quicksight: List[_QuickSightDashboardConfig] = field(default_factory=list)


@dataclass
class _Manifest:
    content: Optional[_ContentConfig] = None


def _make_context(
    dashboards: Optional[List[_QuickSightDashboardConfig]] = None,
    stage_dashboards: Optional[List[_QuickSightDashboardConfig]] = None,
    aws_account_id: Optional[str] = "123456789012",
    region: str = "us-east-1",
    bundle_files: Optional[Set[str]] = None,
) -> DryRunContext:
    """Build a DryRunContext with QuickSight configuration."""
    content = _ContentConfig(quicksight=dashboards or [])
    manifest = _Manifest(content=content)
    target = _TargetConfig(
        domain=_DomainConfig(region=region),
        quicksight=stage_dashboards or [],
    )

    config: Dict[str, Any] = {"region": region}
    if aws_account_id:
        config["aws"] = {"account_id": aws_account_id}

    ctx = DryRunContext(
        manifest_file="manifest.yaml",
        manifest=manifest,
        target_config=target,
        config=config,
    )
    if bundle_files is not None:
        ctx.bundle_files = bundle_files
    return ctx


@pytest.fixture
def checker():
    return QuickSightChecker()


# -----------------------------------------------------------------------
# Test: No target config → skip with WARNING
# -----------------------------------------------------------------------


class TestQuickSightCheckerNoConfig:
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
# Test: No dashboards configured → OK
# -----------------------------------------------------------------------


class TestNoDashboardsConfigured:
    """Tests when no QuickSight dashboards are configured."""

    def test_no_dashboards_returns_ok(self, checker):
        context = _make_context(dashboards=[], stage_dashboards=[])
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "no quicksight" in findings[0].message.lower()
        assert findings[0].service == "quicksight"

    def test_no_content_returns_ok(self, checker):
        manifest = _Manifest(content=None)
        target = _TargetConfig()
        context = DryRunContext(
            manifest_file="m.yaml",
            manifest=manifest,
            target_config=target,
            config={"region": "us-east-1"},
        )
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "no quicksight" in findings[0].message.lower()


# -----------------------------------------------------------------------
# Test: Dashboard found via export lookup → OK
# -----------------------------------------------------------------------


class TestDashboardExportFound:
    """Tests when dashboard is found via lookup_dashboard_by_name."""

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_dashboard_found_returns_ok(self, mock_lookup, checker):
        mock_lookup.return_value = "dash-123"

        dashboards = [_QuickSightDashboardConfig(name="MyDashboard")]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "mydashboard" in ok_findings[0].message.lower()
        assert "dash-123" in ok_findings[0].message
        assert "exported and imported" in ok_findings[0].message.lower()
        assert ok_findings[0].resource == "MyDashboard"
        assert ok_findings[0].service == "quicksight"

        mock_lookup.assert_called_once_with("MyDashboard", "123456789012", "us-east-1")

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_multiple_dashboards_found(self, mock_lookup, checker):
        mock_lookup.side_effect = ["dash-1", "dash-2"]

        dashboards = [
            _QuickSightDashboardConfig(name="Dashboard1"),
            _QuickSightDashboardConfig(name="Dashboard2"),
        ]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 2
        assert ok_findings[0].resource == "Dashboard1"
        assert ok_findings[1].resource == "Dashboard2"


# -----------------------------------------------------------------------
# Test: Dashboard not found via export lookup → ERROR
# -----------------------------------------------------------------------


class TestDashboardExportNotFound:
    """Tests when dashboard lookup fails."""

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_dashboard_not_found_returns_error(self, mock_lookup, checker):
        mock_lookup.side_effect = Exception("Dashboard not found")

        dashboards = [_QuickSightDashboardConfig(name="MissingDash")]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "missingdash" in error_findings[0].message.lower()
        assert "not found" in error_findings[0].message.lower()
        assert error_findings[0].resource == "MissingDash"
        assert error_findings[0].service == "quicksight"

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_api_error_returns_error(self, mock_lookup, checker):
        mock_lookup.side_effect = Exception("Access denied")

        dashboards = [_QuickSightDashboardConfig(name="SecureDash")]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "access denied" in error_findings[0].message.lower()


# -----------------------------------------------------------------------
# Test: Local asset bundle → OK / WARNING
# -----------------------------------------------------------------------


class TestLocalAssetBundle:
    """Tests when dashboard uses a local asset bundle file."""

    def test_asset_bundle_found_in_bundle(self, checker):
        dashboards = [
            _QuickSightDashboardConfig(name="LocalDash", assetBundle="my_dash.qs")
        ]
        context = _make_context(
            dashboards=dashboards,
            bundle_files={"my_dash.qs", "other_file.txt"},
        )
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "my_dash.qs" in ok_findings[0].message
        assert ok_findings[0].resource == "LocalDash"

    def test_asset_bundle_found_with_quicksight_prefix(self, checker):
        dashboards = [
            _QuickSightDashboardConfig(name="PrefixDash", assetBundle="dashboard.qs")
        ]
        context = _make_context(
            dashboards=dashboards,
            bundle_files={"quicksight/dashboard.qs"},
        )
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "quicksight/dashboard.qs" in ok_findings[0].message

    def test_asset_bundle_not_found_in_bundle(self, checker):
        dashboards = [
            _QuickSightDashboardConfig(name="MissingBundle", assetBundle="missing.qs")
        ]
        context = _make_context(
            dashboards=dashboards,
            bundle_files={"other_file.txt"},
        )
        findings = checker.check(context)

        warn_findings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(warn_findings) == 1
        assert "missing.qs" in warn_findings[0].message
        assert "not found" in warn_findings[0].message.lower()
        assert warn_findings[0].resource == "MissingBundle"

    def test_asset_bundle_no_bundle_files(self, checker):
        """When no bundle files are loaded, report OK with local file info."""
        dashboards = [
            _QuickSightDashboardConfig(name="NoBundleDash", assetBundle="local.qs")
        ]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "local.qs" in ok_findings[0].message
        assert ok_findings[0].resource == "NoBundleDash"


# -----------------------------------------------------------------------
# Test: No AWS account ID → WARNING + still reports dashboards
# -----------------------------------------------------------------------


class TestNoAccountId:
    """Tests when AWS account ID is not available."""

    def test_no_account_id_produces_warning(self, checker):
        dashboards = [_QuickSightDashboardConfig(name="SomeDash")]
        context = _make_context(dashboards=dashboards, aws_account_id=None)
        findings = checker.check(context)

        warn_findings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(warn_findings) == 1
        assert "account id" in warn_findings[0].message.lower()

    def test_no_account_id_still_reports_dashboards(self, checker):
        dashboards = [
            _QuickSightDashboardConfig(name="Dash1"),
            _QuickSightDashboardConfig(name="Dash2"),
        ]
        context = _make_context(dashboards=dashboards, aws_account_id=None)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 2
        assert ok_findings[0].resource == "Dash1"
        assert ok_findings[1].resource == "Dash2"


# -----------------------------------------------------------------------
# Test: Stage-level QuickSight dashboards
# -----------------------------------------------------------------------


class TestStageLevelDashboards:
    """Tests when dashboards are configured at the stage level."""

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_stage_dashboards_are_checked(self, mock_lookup, checker):
        mock_lookup.return_value = "stage-dash-id"

        stage_dashboards = [_QuickSightDashboardConfig(name="StageDash")]
        context = _make_context(stage_dashboards=stage_dashboards)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert ok_findings[0].resource == "StageDash"

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_content_and_stage_dashboards_combined(self, mock_lookup, checker):
        mock_lookup.side_effect = ["content-id", "stage-id"]

        content_dashboards = [_QuickSightDashboardConfig(name="ContentDash")]
        stage_dashboards = [_QuickSightDashboardConfig(name="StageDash")]
        context = _make_context(
            dashboards=content_dashboards,
            stage_dashboards=stage_dashboards,
        )
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 2
        resources = [f.resource for f in ok_findings]
        assert "ContentDash" in resources
        assert "StageDash" in resources


# -----------------------------------------------------------------------
# Test: Finding metadata correctness
# -----------------------------------------------------------------------


class TestFindingMetadata:
    """Tests that findings include correct resource and service metadata."""

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_ok_finding_has_service(self, mock_lookup, checker):
        mock_lookup.return_value = "d-1"

        dashboards = [_QuickSightDashboardConfig(name="MetaDash")]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        assert all(f.service == "quicksight" for f in findings)

    @patch("smus_cicd.helpers.quicksight.lookup_dashboard_by_name")
    def test_error_finding_has_resource(self, mock_lookup, checker):
        mock_lookup.side_effect = Exception("Not found")

        dashboards = [_QuickSightDashboardConfig(name="ErrDash")]
        context = _make_context(dashboards=dashboards)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert error_findings[0].resource == "ErrDash"
        assert error_findings[0].service == "quicksight"

    def test_no_config_ok_finding_has_service(self, checker):
        context = _make_context(dashboards=[], stage_dashboards=[])
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].service == "quicksight"

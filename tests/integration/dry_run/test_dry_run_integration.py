"""Integration tests for the deploy dry-run feature.

These tests exercise the full flow through DryRunEngine and CLI, mocking
AWS API calls but testing real orchestration logic across all 12 checkers.

Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from smus_cicd.cli import app
from smus_cicd.commands.dry_run.engine import DryRunEngine
from smus_cicd.commands.dry_run.models import (
    DryRunContext,
    Finding,
    Phase,
    Severity,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(error_count: int = 0, warning_count: int = 0, ok_count: int = 0) -> MagicMock:
    """Create a mock DryRunReport with configurable counts."""
    report = MagicMock()
    report.error_count = error_count
    report.warning_count = warning_count
    report.ok_count = ok_count
    report.render.return_value = "mock report output"
    return report


def _make_checker_mock(findings: List[Finding]) -> MagicMock:
    """Return a mock checker whose check() returns the given findings."""
    mock = MagicMock()
    mock.check.return_value = findings
    return mock


def _ok_finding(msg: str = "OK") -> Finding:
    return Finding(severity=Severity.OK, message=msg)


def _warn_finding(msg: str = "Warning") -> Finding:
    return Finding(severity=Severity.WARNING, message=msg)


def _error_finding(msg: str = "Error") -> Finding:
    return Finding(severity=Severity.ERROR, message=msg)


ALL_PHASES = list(Phase)


def _build_engine_all_ok() -> DryRunEngine:
    """Build a DryRunEngine with all 12 phases returning OK."""
    engine = DryRunEngine(
        manifest_file="manifest.yaml",
        stage_name="dev",
    )
    engine._checkers = [
        (phase, _make_checker_mock([_ok_finding(f"{phase.value} OK")]))
        for phase in ALL_PHASES
    ]
    return engine


# ---------------------------------------------------------------------------
# 1. Happy path: Valid manifest + bundle → report with zero errors
# Validates: Requirement 11.1
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Full dry-run flow with valid inputs produces zero errors."""

    def test_all_phases_ok_zero_errors(self):
        """Valid manifest + bundle → all 12 phases run, zero errors."""
        engine = _build_engine_all_ok()
        report = engine.run()

        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.ok_count == 12
        assert len(report.findings_by_phase) == 12
        for phase in ALL_PHASES:
            assert phase in report.findings_by_phase

    def test_happy_path_with_warnings_still_zero_errors(self):
        """Warnings are non-blocking — report has zero errors."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
        ] + [
            (phase, _make_checker_mock([_warn_finding(f"{phase.value} warn")]))
            for phase in ALL_PHASES[1:]
        ]
        report = engine.run()

        assert report.error_count == 0
        assert report.warning_count == 11
        assert len(report.findings_by_phase) == 12



# ---------------------------------------------------------------------------
# 2. Invalid manifest: Malformed YAML → manifest validation errors
# Validates: Requirement 11.2
# ---------------------------------------------------------------------------


class TestInvalidManifest:
    """Dry-run with invalid manifest produces manifest validation errors."""

    def test_manifest_error_stops_engine(self):
        """Manifest ERROR triggers fail-fast — no subsequent phases run."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (
                Phase.MANIFEST_VALIDATION,
                _make_checker_mock([_error_finding("Manifest parse error: invalid YAML")]),
            ),
            (
                Phase.BUNDLE_EXPLORATION,
                _make_checker_mock([_ok_finding("Bundle OK")]),
            ),
            (
                Phase.PERMISSION_VERIFICATION,
                _make_checker_mock([_ok_finding("Perms OK")]),
            ),
        ]
        report = engine.run()

        assert report.error_count == 1
        assert Phase.MANIFEST_VALIDATION in report.findings_by_phase
        assert Phase.BUNDLE_EXPLORATION not in report.findings_by_phase
        assert Phase.PERMISSION_VERIFICATION not in report.findings_by_phase

    def test_manifest_multiple_errors(self):
        """Multiple manifest errors are all collected before fail-fast."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (
                Phase.MANIFEST_VALIDATION,
                _make_checker_mock([
                    _error_finding("Missing required field: application_name"),
                    _error_finding("Target stage 'prod' not found"),
                ]),
            ),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
        ]
        report = engine.run()

        assert report.error_count == 2
        assert Phase.BUNDLE_EXPLORATION not in report.findings_by_phase


# ---------------------------------------------------------------------------
# 3. Missing permissions: Restricted IAM identity → permission errors
# Validates: Requirement 11.3
# ---------------------------------------------------------------------------


class TestMissingPermissions:
    """Dry-run with restricted IAM identity reports permission errors."""

    def test_permission_errors_collected(self):
        """Permission errors are reported but do not stop subsequent phases."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.PERMISSION_VERIFICATION,
                _make_checker_mock([
                    _error_finding("Missing s3:PutObject on arn:aws:s3:::my-bucket/*"),
                    _error_finding("Missing datazone:CreateAsset on domain dzd_123"),
                ]),
            ),
            (Phase.CONNECTIVITY, _make_checker_mock([_ok_finding()])),
            (Phase.PROJECT_INIT, _make_checker_mock([_ok_finding()])),
            (Phase.QUICKSIGHT, _make_checker_mock([_ok_finding()])),
            (Phase.STORAGE_DEPLOYMENT, _make_checker_mock([_ok_finding()])),
            (Phase.GIT_DEPLOYMENT, _make_checker_mock([_ok_finding()])),
            (Phase.CATALOG_IMPORT, _make_checker_mock([_ok_finding()])),
            (Phase.DEPENDENCY_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.WORKFLOW_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BOOTSTRAP_ACTIONS, _make_checker_mock([_ok_finding()])),
        ]
        report = engine.run()

        assert report.error_count == 2
        assert len(report.findings_by_phase) == 12
        perm_findings = report.findings_by_phase[Phase.PERMISSION_VERIFICATION]
        assert any("s3:PutObject" in f.message for f in perm_findings)
        assert any("datazone:CreateAsset" in f.message for f in perm_findings)

    def test_permission_warning_fallback(self):
        """SimulatePrincipalPolicy denied → WARNING, not ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.PERMISSION_VERIFICATION,
                _make_checker_mock([
                    _warn_finding("Could not verify permissions: AccessDenied on SimulatePrincipalPolicy"),
                ]),
            ),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[3:]
        ]
        report = engine.run()

        assert report.error_count == 0
        assert report.warning_count == 1


# ---------------------------------------------------------------------------
# 4. Unreachable resources: Nonexistent S3 bucket / DataZone domain
# Validates: Requirement 11.4
# ---------------------------------------------------------------------------


class TestUnreachableResources:
    """Dry-run targeting unreachable AWS resources reports connectivity errors."""

    def test_connectivity_errors_reported(self):
        """Unreachable domain and bucket produce ERROR findings."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
            (Phase.PERMISSION_VERIFICATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.CONNECTIVITY,
                _make_checker_mock([
                    _error_finding("DataZone domain dzd_nonexistent is unreachable: ResourceNotFoundException"),
                    _error_finding("S3 bucket my-missing-bucket is unreachable: 404 Not Found"),
                ]),
            ),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[4:]
        ]
        report = engine.run()

        assert report.error_count == 2
        conn_findings = report.findings_by_phase[Phase.CONNECTIVITY]
        assert any("dzd_nonexistent" in f.message for f in conn_findings)
        assert any("my-missing-bucket" in f.message for f in conn_findings)

    def test_connectivity_errors_do_not_stop_later_phases(self):
        """Connectivity errors are non-blocking for subsequent phases."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
            (Phase.PERMISSION_VERIFICATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.CONNECTIVITY,
                _make_checker_mock([_error_finding("Unreachable resource")]),
            ),
            (Phase.PROJECT_INIT, _make_checker_mock([_ok_finding("Project OK")])),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[5:]
        ]
        report = engine.run()

        assert Phase.PROJECT_INIT in report.findings_by_phase
        assert len(report.findings_by_phase) == 12


# ---------------------------------------------------------------------------
# 5. Invalid bundle: Incomplete artifacts → bundle validation errors
# Validates: Requirement 11.5
# ---------------------------------------------------------------------------


class TestInvalidBundle:
    """Dry-run with invalid or incomplete bundle reports bundle errors."""

    def test_bundle_errors_collected(self):
        """Missing artifacts in bundle produce ERROR findings."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.BUNDLE_EXPLORATION,
                _make_checker_mock([
                    _error_finding("Missing artifact: storage/data.csv not found in bundle"),
                    _error_finding("Invalid ZIP: bundle.zip is corrupted"),
                ]),
            ),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[2:]
        ]
        report = engine.run()

        assert report.error_count == 2
        bundle_findings = report.findings_by_phase[Phase.BUNDLE_EXPLORATION]
        assert any("storage/data.csv" in f.message for f in bundle_findings)

    def test_bundle_errors_do_not_stop_later_phases(self):
        """Bundle errors are non-blocking (only manifest errors cause fail-fast)."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (
                Phase.BUNDLE_EXPLORATION,
                _make_checker_mock([_error_finding("Bad bundle")]),
            ),
            (
                Phase.PERMISSION_VERIFICATION,
                _make_checker_mock([_ok_finding("Perms OK")]),
            ),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[3:]
        ]
        report = engine.run()

        assert Phase.PERMISSION_VERIFICATION in report.findings_by_phase
        assert len(report.findings_by_phase) == 12


# ---------------------------------------------------------------------------
# 6. Idempotence: Same inputs twice → identical reports
# Validates: Requirement 11.6
# ---------------------------------------------------------------------------


class TestIdempotence:
    """Dry-run produces consistent results across repeated executions."""

    def test_same_inputs_produce_identical_reports(self):
        """Running the engine twice with identical checkers yields identical reports."""
        def _build():
            engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
            engine._checkers = [
                (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding("Manifest OK")])),
                (Phase.BUNDLE_EXPLORATION, _make_checker_mock([
                    _ok_finding("Bundle OK"),
                    _warn_finding("Extra file in bundle"),
                ])),
                (Phase.PERMISSION_VERIFICATION, _make_checker_mock([
                    _error_finding("Missing s3:PutObject"),
                ])),
            ] + [
                (phase, _make_checker_mock([_ok_finding(f"{phase.value} OK")]))
                for phase in ALL_PHASES[3:]
            ]
            return engine

        report1 = _build().run()
        report2 = _build().run()

        assert report1.error_count == report2.error_count
        assert report1.warning_count == report2.warning_count
        assert report1.ok_count == report2.ok_count
        assert set(report1.findings_by_phase.keys()) == set(report2.findings_by_phase.keys())

        for phase in report1.findings_by_phase:
            findings1 = report1.findings_by_phase[phase]
            findings2 = report2.findings_by_phase[phase]
            assert len(findings1) == len(findings2)
            for f1, f2 in zip(findings1, findings2):
                assert f1.severity == f2.severity
                assert f1.message == f2.message

    def test_idempotence_with_all_ok(self):
        """Two runs with all-OK checkers produce identical zero-error reports."""
        report1 = _build_engine_all_ok().run()
        report2 = _build_engine_all_ok().run()

        assert report1.error_count == report2.error_count == 0
        assert report1.ok_count == report2.ok_count == 12


# ---------------------------------------------------------------------------
# 7. Missing Glue dependencies: Catalog export referencing nonexistent
#    Glue tables, views, or databases → dependency validation errors
# Validates: Requirement 11.7 (mapped from 13.1, 13.2, 13.3)
# ---------------------------------------------------------------------------


class TestMissingGlueDependencies:
    """Dry-run detects missing Glue Data Catalog resources."""

    def test_missing_glue_table_produces_error(self):
        """Missing Glue table referenced by catalog asset → ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([_ok_finding()])),
            (Phase.PERMISSION_VERIFICATION, _make_checker_mock([_ok_finding()])),
            (Phase.CONNECTIVITY, _make_checker_mock([_ok_finding()])),
            (Phase.PROJECT_INIT, _make_checker_mock([_ok_finding()])),
            (Phase.QUICKSIGHT, _make_checker_mock([_ok_finding()])),
            (Phase.STORAGE_DEPLOYMENT, _make_checker_mock([_ok_finding()])),
            (Phase.GIT_DEPLOYMENT, _make_checker_mock([_ok_finding()])),
            (Phase.CATALOG_IMPORT, _make_checker_mock([_ok_finding()])),
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Glue table 'orders' in database 'analytics_db' does not exist"),
                ]),
            ),
            (Phase.WORKFLOW_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BOOTSTRAP_ACTIONS, _make_checker_mock([_ok_finding()])),
        ]
        report = engine.run()

        assert report.error_count == 1
        dep_findings = report.findings_by_phase[Phase.DEPENDENCY_VALIDATION]
        assert any("orders" in f.message and "analytics_db" in f.message for f in dep_findings)

    def test_missing_glue_database_produces_error(self):
        """Missing Glue database → ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        # Insert dependency checker at correct position
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Glue database 'missing_db' does not exist"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 1
        dep_findings = report.findings_by_phase[Phase.DEPENDENCY_VALIDATION]
        assert any("missing_db" in f.message for f in dep_findings)

    def test_missing_glue_view_produces_error(self):
        """Missing Glue view → ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Glue view 'summary_view' in database 'analytics_db' does not exist"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 1
        dep_findings = report.findings_by_phase[Phase.DEPENDENCY_VALIDATION]
        assert any("summary_view" in f.message for f in dep_findings)

    def test_multiple_missing_glue_resources(self):
        """Multiple missing Glue resources → multiple ERRORs."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Glue database 'db1' does not exist"),
                    _error_finding("Glue table 'tbl1' in database 'db2' does not exist"),
                    _error_finding("Glue view 'view1' in database 'db2' does not exist"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 3


# ---------------------------------------------------------------------------
# 8. Missing DataZone types: Catalog export referencing nonexistent
#    custom form types / asset types → dependency validation errors
# Validates: Requirement 11.8 (mapped from 13.6, 13.7, 13.8, 13.9)
# ---------------------------------------------------------------------------


class TestMissingDataZoneTypes:
    """Dry-run detects missing custom DataZone form types and asset types."""

    def test_missing_form_type_produces_error(self):
        """Missing custom form type → ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Custom form type 'custom.MyFormType' not found in domain"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 1
        dep_findings = report.findings_by_phase[Phase.DEPENDENCY_VALIDATION]
        assert any("custom.MyFormType" in f.message for f in dep_findings)

    def test_missing_asset_type_produces_error(self):
        """Missing custom asset type → ERROR."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Custom asset type 'custom.SpecialAsset' not found in domain"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 1
        dep_findings = report.findings_by_phase[Phase.DEPENDENCY_VALIDATION]
        assert any("custom.SpecialAsset" in f.message for f in dep_findings)

    def test_mixed_dependency_errors_and_warnings(self):
        """Missing form types (ERROR) + unresolvable revisions (WARNING)."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES
            if phase != Phase.DEPENDENCY_VALIDATION
        ]
        dep_idx = ALL_PHASES.index(Phase.DEPENDENCY_VALIDATION)
        engine._checkers.insert(
            dep_idx,
            (
                Phase.DEPENDENCY_VALIDATION,
                _make_checker_mock([
                    _error_finding("Custom form type 'custom.MissingForm' not found"),
                    _warn_finding("Form type revision 3 does not match target revision 5"),
                    _warn_finding("Data source 'GLUE/analytics_db' not found in project"),
                ]),
            ),
        )
        report = engine.run()

        assert report.error_count == 1
        assert report.warning_count == 2


# ---------------------------------------------------------------------------
# 9. Pre-deployment validation pass → deploy proceeds
# Validates: Requirement 11.7 (mapped from 14.1, 14.3)
# ---------------------------------------------------------------------------


class TestPreDeploymentValidationPass:
    """Normal deploy with valid manifest + bundle → validation passes, deployment proceeds."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_pass_calls_deploy(self, mock_engine_cls, mock_deploy):
        """Zero errors → deploy_command is called."""
        report = _make_report(error_count=0, warning_count=1, ok_count=12)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        mock_engine_cls.assert_called_once()
        mock_deploy.assert_called_once()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_pass_uses_text_format(self, mock_engine_cls, mock_deploy):
        """Pre-deployment validation always uses text format."""
        report = _make_report(error_count=0, ok_count=12)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        call_args = mock_engine_cls.call_args
        # Fourth positional arg is output_format
        assert call_args[0][3] == "text"

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_pass_with_warnings_still_deploys(self, mock_engine_cls, mock_deploy):
        """Warnings are non-blocking — deploy proceeds."""
        report = _make_report(error_count=0, warning_count=5, ok_count=7)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        mock_deploy.assert_called_once()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_pass_output_json_still_uses_text(self, mock_engine_cls, mock_deploy):
        """--output json on normal deploy: pre-deployment still uses text format."""
        report = _make_report(error_count=0, ok_count=12)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--output", "json", "--targets", "dev"])

        call_args = mock_engine_cls.call_args
        assert call_args[0][3] == "text"
        mock_deploy.assert_called_once()


# ---------------------------------------------------------------------------
# 10. Pre-deployment validation fail → abort
# Validates: Requirement 11.8 (mapped from 14.2)
# ---------------------------------------------------------------------------


class TestPreDeploymentValidationFail:
    """Normal deploy with errors → validation fails, deployment aborted."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_fail_aborts_deploy(self, mock_engine_cls, mock_deploy):
        """Errors found → deploy_command is NOT called, exit code non-zero."""
        report = _make_report(error_count=3, warning_count=1)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        assert result.exit_code != 0
        mock_deploy.assert_not_called()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_fail_renders_report(self, mock_engine_cls, mock_deploy):
        """Failed validation renders the report in text format."""
        report = _make_report(error_count=2)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        report.render.assert_called_once_with("text")

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_fail_no_resources_modified(self, mock_engine_cls, mock_deploy):
        """When validation fails, deploy_command is never invoked (no resources modified)."""
        report = _make_report(error_count=1)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        mock_deploy.assert_not_called()
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 11. Skip validation: --skip-validation → no validation, deploy directly
# Validates: Requirement 11.9
# ---------------------------------------------------------------------------


class TestSkipValidation:
    """--skip-validation bypasses pre-deployment validation."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_skip_validation_bypasses_engine(self, mock_engine_cls, mock_deploy):
        """--skip-validation → DryRunEngine is NOT instantiated."""
        runner.invoke(app, ["deploy", "--skip-validation", "--targets", "dev"])

        mock_engine_cls.assert_not_called()
        mock_deploy.assert_called_once()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_skip_validation_deploys_directly(self, mock_engine_cls, mock_deploy):
        """--skip-validation → deploy_command called with correct args."""
        runner.invoke(
            app,
            [
                "deploy",
                "--skip-validation",
                "--targets", "dev",
                "--manifest", "my-manifest.yaml",
            ],
        )

        mock_engine_cls.assert_not_called()
        mock_deploy.assert_called_once()
        call_args = mock_deploy.call_args
        # Verify targets and manifest are passed through
        assert call_args[0][0] == "dev"  # targets
        assert call_args[0][1] == "my-manifest.yaml"  # manifest_file

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_takes_precedence_over_skip_validation(
        self, mock_engine_cls, mock_deploy
    ):
        """--dry-run + --skip-validation: dry-run takes precedence."""
        report = _make_report(error_count=0)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(
            app, ["deploy", "--dry-run", "--skip-validation", "--targets", "dev"]
        )

        assert result.exit_code == 0
        mock_engine_cls.assert_called_once()
        mock_deploy.assert_not_called()


# ---------------------------------------------------------------------------
# Cross-cutting: Report rendering integration
# ---------------------------------------------------------------------------


class TestReportRendering:
    """Verify report rendering works end-to-end through the engine."""

    def test_text_report_contains_phase_names(self):
        """Text report includes phase names for all executed phases."""
        engine = _build_engine_all_ok()
        report = engine.run()
        text = report.render("text")

        for phase in ALL_PHASES:
            assert phase.value in text

    def test_json_report_is_valid_json(self):
        """JSON report is parseable and contains expected structure."""
        engine = _build_engine_all_ok()
        report = engine.run()
        json_str = report.render("json")

        parsed = json.loads(json_str)
        assert "summary" in parsed
        assert "phases" in parsed
        assert parsed["summary"]["errors"] == 0
        assert parsed["summary"]["ok"] == 12

    def test_report_with_mixed_severities(self):
        """Report correctly counts mixed OK/WARNING/ERROR findings."""
        engine = DryRunEngine(manifest_file="manifest.yaml", stage_name="dev")
        engine._checkers = [
            (Phase.MANIFEST_VALIDATION, _make_checker_mock([_ok_finding()])),
            (Phase.BUNDLE_EXPLORATION, _make_checker_mock([
                _ok_finding("Bundle OK"),
                _warn_finding("Extra file"),
            ])),
            (Phase.PERMISSION_VERIFICATION, _make_checker_mock([
                _error_finding("Missing permission"),
            ])),
        ] + [
            (phase, _make_checker_mock([_ok_finding()]))
            for phase in ALL_PHASES[3:]
        ]
        report = engine.run()

        assert report.ok_count == 11
        assert report.warning_count == 1
        assert report.error_count == 1

        json_str = report.render("json")
        parsed = json.loads(json_str)
        assert parsed["summary"]["ok"] == 11
        assert parsed["summary"]["warnings"] == 1
        assert parsed["summary"]["errors"] == 1

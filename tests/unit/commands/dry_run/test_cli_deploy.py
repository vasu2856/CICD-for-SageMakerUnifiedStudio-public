"""Unit tests for CLI deploy integration with dry-run.

Validates: Requirements 10.8 — pre-deployment validation integration in the CLI
deploy function, including: validation pass leading to deployment, validation
failure aborting deployment, and --skip-validation bypassing validation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from smus_cicd.cli import app

runner = CliRunner()


def _make_report(error_count=0, warning_count=0, ok_count=0):
    """Create a mock DryRunReport."""
    report = MagicMock()
    report.error_count = error_count
    report.warning_count = warning_count
    report.ok_count = ok_count
    report.render.return_value = "mock report output"
    return report


# ---------------------------------------------------------------------------
# Path 1: Standalone dry-run
# ---------------------------------------------------------------------------


class TestStandaloneDryRun:
    """Tests for --dry-run flag (standalone mode)."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_no_errors_exits_zero(self, mock_engine_cls, mock_deploy):
        """Standalone dry-run with 0 errors should exit 0 and not deploy."""
        report = _make_report(error_count=0, ok_count=5)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--dry-run", "--targets", "dev"])

        assert result.exit_code == 0
        mock_engine_cls.assert_called_once()
        mock_deploy.assert_not_called()
        report.render.assert_called_once()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_with_errors_exits_nonzero(self, mock_engine_cls, mock_deploy):
        """Standalone dry-run with errors should exit non-zero and not deploy."""
        report = _make_report(error_count=3)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--dry-run", "--targets", "dev"])

        assert result.exit_code != 0
        mock_deploy.assert_not_called()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_json_output(self, mock_engine_cls, mock_deploy):
        """--dry-run --output json should create engine with json format."""
        report = _make_report(error_count=0)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(
            app, ["deploy", "--dry-run", "--output", "json", "--targets", "dev"]
        )

        assert result.exit_code == 0
        # Engine should be created with output_format="json"
        call_args = mock_engine_cls.call_args
        assert call_args[0][3] == "json" or call_args[1].get("output_format") == "json"
        # Report should be rendered with "json"
        report.render.assert_called_once_with("json")

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_text_output_default(self, mock_engine_cls, mock_deploy):
        """--dry-run with default output should use text format."""
        report = _make_report(error_count=0)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--dry-run", "--targets", "dev"])

        assert result.exit_code == 0
        # Engine should be created with output_format="text"
        call_args = mock_engine_cls.call_args
        assert call_args[0][3] == "text" or call_args[1].get("output_format") == "text"
        # Report should be rendered with "text"
        report.render.assert_called_once_with("text")


# ---------------------------------------------------------------------------
# Path 2: Pre-deployment validation
# ---------------------------------------------------------------------------


class TestPreDeploymentValidation:
    """Tests for normal deploy with automatic pre-deployment validation."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_pass_proceeds_to_deploy(self, mock_engine_cls, mock_deploy):
        """When pre-deployment validation has 0 errors, deploy_command is called."""
        report = _make_report(error_count=0, warning_count=2)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])  # noqa: F841

        mock_deploy.assert_called_once()
        # Engine should be created with "text" format for pre-deployment
        call_args = mock_engine_cls.call_args
        assert call_args[0][3] == "text"

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_validation_fail_aborts_deploy(self, mock_engine_cls, mock_deploy):
        """When pre-deployment validation has errors, deploy is aborted."""
        report = _make_report(error_count=3)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(app, ["deploy", "--targets", "dev"])

        assert result.exit_code != 0
        mock_deploy.assert_not_called()
        # Report should be rendered in text format
        report.render.assert_called_once_with("text")


# ---------------------------------------------------------------------------
# Path 3: Skip validation
# ---------------------------------------------------------------------------


class TestSkipValidation:
    """Tests for --skip-validation flag."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_skip_validation_bypasses_engine(self, mock_engine_cls, mock_deploy):
        """--skip-validation should skip DryRunEngine and call deploy directly."""
        runner.invoke(app, ["deploy", "--skip-validation", "--targets", "dev"])

        mock_engine_cls.assert_not_called()
        mock_deploy.assert_called_once()


# ---------------------------------------------------------------------------
# Flag interactions
# ---------------------------------------------------------------------------


class TestFlagInteractions:
    """Tests for flag combination behavior."""

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_plus_skip_validation(self, mock_engine_cls, mock_deploy):
        """--dry-run + --skip-validation: dry-run takes precedence."""
        report = _make_report(error_count=0)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(
            app, ["deploy", "--dry-run", "--skip-validation", "--targets", "dev"]
        )

        assert result.exit_code == 0
        # dry-run path should run (engine created)
        mock_engine_cls.assert_called_once()
        # deploy should NOT be called (standalone dry-run never deploys)
        mock_deploy.assert_not_called()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_dry_run_suppresses_events(self, mock_engine_cls, mock_deploy):
        """--dry-run --emit-events: deploy_command should not be called."""
        report = _make_report(error_count=0)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(
            app, ["deploy", "--dry-run", "--emit-events", "--targets", "dev"]
        )

        assert result.exit_code == 0
        mock_deploy.assert_not_called()

    @patch("smus_cicd.cli.deploy_command")
    @patch("smus_cicd.cli.DryRunEngine")
    def test_pre_deploy_uses_text_regardless_of_output_flag(
        self, mock_engine_cls, mock_deploy
    ):
        """--output json on normal deploy: pre-deployment still uses text format."""
        report = _make_report(error_count=0, warning_count=1)
        mock_engine_cls.return_value.run.return_value = report

        result = runner.invoke(  # noqa: F841
            app, ["deploy", "--output", "json", "--targets", "dev"]
        )

        # Pre-deployment validation should use "text" format, not "json"
        call_args = mock_engine_cls.call_args
        assert call_args[0][3] == "text"
        mock_deploy.assert_called_once()

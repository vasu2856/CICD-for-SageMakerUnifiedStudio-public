"""Unit tests for ManifestChecker.

Tests valid manifest loading, invalid YAML, missing stage, unresolved env vars,
missing manifest file, and domain config building.

Requirements: 10.5
"""

import os
import textwrap
from unittest.mock import patch

import pytest

from smus_cicd.commands.dry_run.checkers.manifest_checker import ManifestChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity


@pytest.fixture
def valid_manifest_yaml(tmp_path):
    """Create a minimal valid manifest YAML file."""
    content = textwrap.dedent("""\
        applicationName: TestApp
        stages:
          dev:
            stage: DEV
            domain:
              region: us-east-1
            project:
              name: dev-project
            environment_variables:
              DB_HOST: localhost
              DB_PORT: "5432"
    """)
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(content)
    return str(manifest_file)


@pytest.fixture
def manifest_with_env_vars(tmp_path):
    """Create a manifest with environment variable references."""
    content = textwrap.dedent("""\
        applicationName: TestApp
        stages:
          dev:
            stage: DEV
            domain:
              region: us-east-1
            project:
              name: dev-project
            environment_variables:
              DB_HOST: localhost
              DB_PORT: "5432"
    """)
    # Add env var references in a comment-like section (they'll be in raw content)
    content += "# connection: ${DB_HOST}:${DB_PORT}\n"
    content += "# api_key: $API_KEY\n"
    content += "# home: $HOME\n"
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(content)
    return str(manifest_file)


@pytest.fixture
def invalid_yaml(tmp_path):
    """Create an invalid YAML file."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("applicationName: TestApp\n  bad_indent: [")
    return str(manifest_file)


@pytest.fixture
def checker():
    return ManifestChecker()


class TestManifestCheckerValidManifest:
    """Tests for successful manifest loading and target resolution."""

    def test_valid_manifest_and_stage(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="dev",
        )
        findings = checker.check(context)

        # Should have OK findings for manifest load, stage resolution, and domain config
        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) >= 3

        # Context should be populated
        assert context.manifest is not None
        assert context.stage_name == "dev"
        assert context.target_config is not None
        assert context.config is not None
        assert context.config["region"] == "us-east-1"

    def test_no_error_findings_for_valid_manifest(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="dev",
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 0


class TestManifestCheckerMissingFile:
    """Tests for missing or unreadable manifest files."""

    def test_missing_manifest_file(self, checker, tmp_path):
        context = DryRunContext(
            manifest_file=str(tmp_path / "nonexistent.yaml"),
            stage_name="dev",
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert (
            "not found" in error_findings[0].message.lower()
            or "failed to parse" in error_findings[0].message.lower()
        )

    def test_missing_manifest_returns_early(self, checker, tmp_path):
        context = DryRunContext(
            manifest_file=str(tmp_path / "nonexistent.yaml"),
            stage_name="dev",
        )
        findings = checker.check(context)

        # Should only have the error finding, no further checks
        assert len(findings) == 1
        assert context.manifest is None


class TestManifestCheckerInvalidYaml:
    """Tests for invalid YAML content."""

    def test_invalid_yaml_returns_error(self, checker, invalid_yaml):
        context = DryRunContext(
            manifest_file=invalid_yaml,
            stage_name="dev",
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) >= 1

    def test_invalid_yaml_returns_early(self, checker, invalid_yaml):
        context = DryRunContext(
            manifest_file=invalid_yaml,
            stage_name="dev",
        )
        checker.check(context)

        # Should not proceed to stage resolution
        assert context.manifest is None
        assert context.target_config is None


class TestManifestCheckerMissingStage:
    """Tests for missing target stage."""

    def test_missing_stage_returns_error(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="prod",
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "prod" in error_findings[0].message
        assert "dev" in error_findings[0].message  # available stages listed

    def test_missing_stage_lists_available(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="staging",
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert error_findings[0].details is not None
        assert "dev" in error_findings[0].details["available_stages"]

    def test_no_target_specified(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name=None,
        )
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "no target" in error_findings[0].message.lower()


class TestManifestCheckerEnvVars:
    """Tests for environment variable reference validation."""

    def test_unresolved_env_var_produces_warning(self, checker, manifest_with_env_vars):
        context = DryRunContext(
            manifest_file=manifest_with_env_vars,
            stage_name="dev",
        )
        # Ensure API_KEY is not in os.environ for this test
        with patch.dict(os.environ, {}, clear=True):
            # We need HOME to not be set for the test to detect it as unresolved
            findings = checker.check(context)

        warning_findings = [f for f in findings if f.severity == Severity.WARNING]
        # API_KEY should be unresolved (not in env_vars or os.environ)
        api_key_warnings = [f for f in warning_findings if "API_KEY" in f.message]
        assert len(api_key_warnings) == 1

    def test_resolved_env_vars_no_warning(self, checker, manifest_with_env_vars):
        context = DryRunContext(
            manifest_file=manifest_with_env_vars,
            stage_name="dev",
        )
        # Set all referenced vars in os.environ
        with patch.dict(
            os.environ, {"API_KEY": "secret", "HOME": "/home/user"}, clear=True
        ):
            findings = checker.check(context)

        warning_findings = [f for f in findings if f.severity == Severity.WARNING]
        # DB_HOST and DB_PORT are in environment_variables, API_KEY and HOME in os.environ
        assert len(warning_findings) == 0

    def test_env_var_in_target_config_not_warned(self, checker, valid_manifest_yaml):
        """Env vars defined in target_config.environment_variables should not produce warnings."""
        # The valid manifest has DB_HOST and DB_PORT in environment_variables
        # but the raw YAML doesn't reference them with $ syntax, so no warnings expected
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="dev",
        )
        findings = checker.check(context)

        warning_findings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(warning_findings) == 0


class TestManifestCheckerCommaTargets:
    """Tests for comma-separated target handling."""

    def test_comma_separated_targets_uses_first(self, checker, valid_manifest_yaml):
        context = DryRunContext(
            manifest_file=valid_manifest_yaml,
            stage_name="dev, staging",
        )
        checker.check(context)

        # Should resolve "dev" (first target)
        assert context.stage_name == "dev"
        assert context.target_config is not None

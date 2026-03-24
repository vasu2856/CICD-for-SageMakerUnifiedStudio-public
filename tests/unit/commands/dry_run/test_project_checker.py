"""Unit tests for ProjectChecker.

Tests project initialization simulation: project exists, project not found
with create=True, project not found with create=False, missing config, and
API errors.

Requirements: 5.1, 6.2, 10.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from smus_cicd.commands.dry_run.checkers.project_checker import ProjectChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Stub dataclasses mirroring the real manifest models
# ---------------------------------------------------------------------------


@dataclass
class _ProjectConfig:
    name: str
    create: bool = False


@dataclass
class _TargetConfig:
    project: Optional[_ProjectConfig] = None


def _make_context(
    project_name: str = "test-project",
    create: bool = False,
    domain_id: str = "dzd_test",
    region: str = "us-east-1",
    has_project_config: bool = True,
) -> DryRunContext:
    """Build a DryRunContext with the given project configuration."""
    project_cfg = (
        _ProjectConfig(name=project_name, create=create) if has_project_config else None
    )
    target = _TargetConfig(project=project_cfg)

    config: Dict[str, Any] = {"region": region, "domain_id": domain_id}

    return DryRunContext(
        manifest_file="manifest.yaml",
        target_config=target,
        config=config,
    )


@pytest.fixture
def checker():
    return ProjectChecker()


# -----------------------------------------------------------------------
# Test: No target config → skip with WARNING
# -----------------------------------------------------------------------


class TestProjectCheckerNoConfig:
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

    def test_no_project_config_produces_warning(self, checker):
        context = _make_context(has_project_config=False)
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "no project configuration" in findings[0].message.lower()

    def test_no_domain_id_produces_warning(self, checker):
        context = DryRunContext(
            manifest_file="m.yaml",
            target_config=_TargetConfig(project=_ProjectConfig(name="proj")),
            config={"region": "us-east-1"},
        )
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "domain_id" in findings[0].message.lower()

    def test_no_project_name_produces_warning(self, checker):
        context = DryRunContext(
            manifest_file="m.yaml",
            target_config=_TargetConfig(project=_ProjectConfig(name="")),
            config={"region": "us-east-1", "domain_id": "dzd_test"},
        )
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "project_name" in findings[0].message.lower()


# -----------------------------------------------------------------------
# Test: Project exists → OK (Req 5.1)
# -----------------------------------------------------------------------


class TestProjectExists:
    """Tests when the project already exists in the domain."""

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_project_exists_returns_ok(self, mock_get_project, checker):
        mock_get_project.return_value = {"id": "proj-123", "name": "test-project"}

        context = _make_context(project_name="test-project", create=False)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "exists" in ok_findings[0].message.lower()
        assert ok_findings[0].resource == "test-project"
        assert ok_findings[0].service == "datazone"

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_project_exists_with_create_true_returns_ok(
        self, mock_get_project, checker
    ):
        mock_get_project.return_value = {"id": "proj-123", "name": "test-project"}

        context = _make_context(project_name="test-project", create=True)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "exists" in ok_findings[0].message.lower()
        assert "no creation needed" in ok_findings[0].message.lower()


# -----------------------------------------------------------------------
# Test: Project not found + create=True → OK (Req 5.1, 6.2)
# -----------------------------------------------------------------------


class TestProjectNotFoundCreateTrue:
    """Tests when project is not found but create=True."""

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_not_found_create_true_returns_ok(self, mock_get_project, checker):
        mock_get_project.return_value = None

        context = _make_context(project_name="new-project", create=True)
        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert len(ok_findings) == 1
        assert "not found" in ok_findings[0].message.lower()
        assert "create=true" in ok_findings[0].message.lower()
        assert "would be created" in ok_findings[0].message.lower()
        assert ok_findings[0].resource == "new-project"
        assert ok_findings[0].service == "datazone"


# -----------------------------------------------------------------------
# Test: Project not found + create=False → ERROR (Req 5.1, 6.2)
# -----------------------------------------------------------------------


class TestProjectNotFoundCreateFalse:
    """Tests when project is not found and create=False."""

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_not_found_create_false_returns_error(self, mock_get_project, checker):
        mock_get_project.return_value = None

        context = _make_context(project_name="missing-project", create=False)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "not found" in error_findings[0].message.lower()
        assert "create=false" in error_findings[0].message.lower()
        assert "would fail" in error_findings[0].message.lower()
        assert error_findings[0].resource == "missing-project"
        assert error_findings[0].service == "datazone"


# -----------------------------------------------------------------------
# Test: API error → ERROR
# -----------------------------------------------------------------------


class TestProjectApiError:
    """Tests when the DataZone API call fails."""

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_api_error_returns_error(self, mock_get_project, checker):
        mock_get_project.side_effect = Exception("Access denied")

        context = _make_context(project_name="err-project", create=True)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "failed" in error_findings[0].message.lower()
        assert "access denied" in error_findings[0].message.lower()
        assert error_findings[0].resource == "err-project"
        assert error_findings[0].service == "datazone"

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_api_error_with_create_false_returns_error(self, mock_get_project, checker):
        mock_get_project.side_effect = Exception("Network timeout")

        context = _make_context(project_name="timeout-project", create=False)
        findings = checker.check(context)

        error_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert len(error_findings) == 1
        assert "failed" in error_findings[0].message.lower()
        assert "network timeout" in error_findings[0].message.lower()


# -----------------------------------------------------------------------
# Test: Finding metadata correctness
# -----------------------------------------------------------------------


class TestFindingMetadata:
    """Tests that findings include correct resource and service metadata."""

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_ok_finding_has_resource_and_service(self, mock_get_project, checker):
        mock_get_project.return_value = {"id": "proj-1", "name": "my-proj"}

        context = _make_context(project_name="my-proj")
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].resource == "my-proj"
        assert findings[0].service == "datazone"

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_error_finding_has_resource_and_service(self, mock_get_project, checker):
        mock_get_project.return_value = None

        context = _make_context(project_name="missing", create=False)
        findings = checker.check(context)

        assert len(findings) == 1
        assert findings[0].resource == "missing"
        assert findings[0].service == "datazone"

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_exactly_one_finding_per_check(self, mock_get_project, checker):
        """Each check should produce exactly one finding."""
        mock_get_project.return_value = {"id": "proj-1", "name": "proj"}

        context = _make_context(project_name="proj")
        findings = checker.check(context)

        assert len(findings) == 1

    @patch("smus_cicd.helpers.datazone.get_project_by_name")
    def test_domain_id_in_message(self, mock_get_project, checker):
        """Finding message should reference the domain ID."""
        mock_get_project.return_value = None

        context = _make_context(
            project_name="proj", create=True, domain_id="dzd_custom"
        )
        findings = checker.check(context)

        assert "dzd_custom" in findings[0].message

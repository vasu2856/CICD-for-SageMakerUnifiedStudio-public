"""Unit tests for GitChecker (Phase 8 — Git Deployment Simulation).

Tests cover:
- No target config → WARNING
- No git items → OK skip
- Single git item with matching bundle files
- Multiple git items with varying file counts
- Git item with no matching files (zero count)
- Connection name reporting
- Repository (targetDirectory) reporting
- Finding metadata (resource, service, details)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

import pytest

from smus_cicd.commands.dry_run.checkers.git_checker import GitChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Lightweight stub dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _GitConfig:
    name: str
    connectionName: Optional[str] = "default.git"
    targetDirectory: str = ""


@dataclass
class _DeploymentConfiguration:
    git: List[_GitConfig] = field(default_factory=list)


@dataclass
class _TargetConfig:
    deployment_configuration: Optional[_DeploymentConfiguration] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    git_items: Optional[List[_GitConfig]] = None,
    bundle_files: Optional[Set[str]] = None,
) -> DryRunContext:
    """Build a DryRunContext with git configuration."""
    dep_cfg = _DeploymentConfiguration(git=git_items or [])
    target = _TargetConfig(deployment_configuration=dep_cfg)

    ctx = DryRunContext(
        manifest_file="manifest.yaml",
        target_config=target,
    )
    if bundle_files is not None:
        ctx.bundle_files = bundle_files
    return ctx


@pytest.fixture
def checker() -> GitChecker:
    return GitChecker()


# ---------------------------------------------------------------------------
# No config / empty config
# ---------------------------------------------------------------------------


# TestGitCheckerNoConfig tests moved to test_preflight_checker.py

# ---------------------------------------------------------------------------
# Single git item
# ---------------------------------------------------------------------------


class TestSingleGitItem:
    """A single git item with matching bundle files."""

    def test_reports_connection_repository_and_file_count(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="my_repo",
            )
        ]
        bundle = {
            "repositories/my_repo/README.md",
            "repositories/my_repo/src/main.py",
            "other/readme.md",
        }
        ctx = _make_context(git_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 1
        f = findings[0]
        assert f.severity == Severity.OK
        assert "my_repo" in f.message
        assert "default.git" in f.message
        assert "2 file(s)" in f.message

    def test_zero_matching_files(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="my_repo",
            )
        ]
        bundle = {"code/main.py"}
        ctx = _make_context(git_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 1
        assert "0 file(s)" in findings[0].message

    def test_empty_bundle(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="",
            )
        ]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)

        assert len(findings) == 1
        assert "0 file(s)" in findings[0].message


# ---------------------------------------------------------------------------
# Multiple git items
# ---------------------------------------------------------------------------


class TestMultipleGitItems:
    """Multiple git items produce one finding each."""

    def test_two_items_produce_two_findings(self, checker):
        items = [
            _GitConfig(
                name="repo_a",
                connectionName="default.git",
                targetDirectory="repo_a",
            ),
            _GitConfig(
                name="repo_b",
                connectionName="project.codecommit",
                targetDirectory="repo_b",
            ),
        ]
        bundle = {
            "repositories/repo_a/file1.py",
            "repositories/repo_a/file2.py",
            "repositories/repo_b/readme.md",
        }
        ctx = _make_context(git_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 2
        # First item
        assert "repo_a" in findings[0].message
        assert "default.git" in findings[0].message
        assert "2 file(s)" in findings[0].message
        # Second item
        assert "repo_b" in findings[1].message
        assert "codecommit" in findings[1].message
        assert "1 file(s)" in findings[1].message


# ---------------------------------------------------------------------------
# Connection name reporting
# ---------------------------------------------------------------------------


class TestConnectionReporting:
    """Connection name is reported as-is."""

    def test_dotted_connection_name(self, checker):
        items = [
            _GitConfig(
                name="x",
                connectionName="default.codecommit",
                targetDirectory="",
            )
        ]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "default.codecommit" in findings[0].message

    def test_simple_connection_name(self, checker):
        items = [_GitConfig(name="x", connectionName="myconn", targetDirectory="")]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "myconn" in findings[0].message

    def test_empty_connection_name(self, checker):
        items = [_GitConfig(name="x", connectionName="", targetDirectory="")]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "connection ''" in findings[0].message

    def test_none_connection_name(self, checker):
        items = [_GitConfig(name="x", connectionName=None, targetDirectory="")]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "connection ''" in findings[0].message


# ---------------------------------------------------------------------------
# Repository (targetDirectory) reporting
# ---------------------------------------------------------------------------


class TestRepositoryReporting:
    """targetDirectory is reported as the repository."""

    def test_non_empty_repository(self, checker):
        items = [
            _GitConfig(
                name="x",
                connectionName="default.git",
                targetDirectory="my/repo",
            )
        ]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "my/repo" in findings[0].message

    def test_empty_repository(self, checker):
        items = [_GitConfig(name="x", connectionName="default.git", targetDirectory="")]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "repository ''" in findings[0].message

    def test_none_target_directory(self, checker):
        items = [
            _GitConfig(name="x", connectionName="default.git", targetDirectory=None)
        ]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "repository ''" in findings[0].message


# ---------------------------------------------------------------------------
# Finding metadata
# ---------------------------------------------------------------------------


class TestFindingMetadata:
    """Each finding carries resource, service, and details."""

    def test_finding_has_resource(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="my_repo",
            )
        ]
        ctx = _make_context(
            git_items=items,
            bundle_files={"repositories/my_repo/a.py"},
        )

        findings = checker.check(ctx)
        assert findings[0].resource == "my_repo"

    def test_finding_has_service(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="my_repo",
            )
        ]
        ctx = _make_context(git_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert findings[0].service == "git"

    def test_finding_has_details(self, checker):
        items = [
            _GitConfig(
                name="my_repo",
                connectionName="default.git",
                targetDirectory="my_repo",
            )
        ]
        ctx = _make_context(
            git_items=items,
            bundle_files={
                "repositories/my_repo/a.py",
                "repositories/my_repo/b.py",
            },
        )

        findings = checker.check(ctx)
        details = findings[0].details
        assert details is not None
        assert details["connection"] == "default.git"
        assert details["repository"] == "my_repo"
        assert details["file_count"] == 2

    def test_skip_finding_has_service(self, checker):
        ctx = _make_context(git_items=[])
        findings = checker.check(ctx)
        assert findings[0].service == "git"

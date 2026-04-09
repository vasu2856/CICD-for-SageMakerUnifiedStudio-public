"""Unit tests for StorageChecker (Phase 7 — Storage Deployment Simulation).

Tests cover:
- No target config → WARNING
- No storage items → OK skip
- Single storage item with matching bundle files
- Multiple storage items with varying file counts
- Storage item with no matching files (zero count)
- Bucket derivation from connectionName
- Prefix from targetDirectory
- Finding metadata (resource, service, details)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set
from unittest.mock import patch

import pytest

from smus_cicd.commands.dry_run.checkers.storage_checker import StorageChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Lightweight stub dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _StorageConfig:
    name: str
    connectionName: Optional[str] = "default.s3_shared"
    targetDirectory: str = ""


@dataclass
class _DeploymentConfiguration:
    storage: List[_StorageConfig] = field(default_factory=list)


@dataclass
class _TargetConfig:
    deployment_configuration: Optional[_DeploymentConfiguration] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    storage_items: Optional[List[_StorageConfig]] = None,
    bundle_files: Optional[Set[str]] = None,
) -> DryRunContext:
    """Build a DryRunContext with storage configuration."""
    dep_cfg = _DeploymentConfiguration(storage=storage_items or [])
    target = _TargetConfig(deployment_configuration=dep_cfg)

    ctx = DryRunContext(
        manifest_file="manifest.yaml",
        target_config=target,
        config={"region": "us-east-1"},
    )
    if bundle_files is not None:
        ctx.bundle_files = bundle_files
    return ctx


def _mock_connections(*connection_mappings: tuple) -> dict:
    """Build a mock connections dict from (connectionName, bucket) pairs.

    Example: ``_mock_connections(("default.s3_shared", "real-bucket-123"))``
    """
    conns = {}
    for conn_name, bucket in connection_mappings:
        conns[conn_name] = {"s3Uri": f"s3://{bucket}"}
    return conns


@pytest.fixture
def checker() -> StorageChecker:
    return StorageChecker()


# ---------------------------------------------------------------------------
# No config / empty config
# ---------------------------------------------------------------------------


# TestStorageCheckerNoConfig tests moved to test_preflight_checker.py

# ---------------------------------------------------------------------------
# Single storage item
# ---------------------------------------------------------------------------


class TestSingleStorageItem:
    """A single storage item with matching bundle files."""

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_reports_bucket_prefix_and_file_count(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket-123")
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory="src"
            )
        ]
        bundle = {"code/main.py", "code/utils.py", "other/readme.md"}
        ctx = _make_context(storage_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 1
        f = findings[0]
        assert f.severity == Severity.OK
        assert "code" in f.message
        assert "real-bucket-123" in f.message
        assert "src" in f.message
        assert "2 file(s)" in f.message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_zero_matching_files(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket-123")
        )
        items = [
            _StorageConfig(
                name="data", connectionName="default.s3_shared", targetDirectory="data"
            )
        ]
        bundle = {"code/main.py"}
        ctx = _make_context(storage_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 1
        assert "0 file(s)" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_empty_bundle(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket-123")
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory=""
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)

        assert len(findings) == 1
        assert "0 file(s)" in findings[0].message


# ---------------------------------------------------------------------------
# Multiple storage items
# ---------------------------------------------------------------------------


class TestMultipleStorageItems:
    """Multiple storage items produce one finding each."""

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_two_items_produce_two_findings(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket-123"),
            ("project.s3_data", "data-bucket-456"),
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory="src"
            ),
            _StorageConfig(
                name="data",
                connectionName="project.s3_data",
                targetDirectory="datasets",
            ),
        ]
        bundle = {"code/a.py", "code/b.py", "data/file.csv"}
        ctx = _make_context(storage_items=items, bundle_files=bundle)

        findings = checker.check(ctx)

        assert len(findings) == 2
        # First item
        assert "code" in findings[0].message
        assert "real-bucket-123" in findings[0].message
        assert "2 file(s)" in findings[0].message
        # Second item
        assert "data" in findings[1].message
        assert "data-bucket-456" in findings[1].message
        assert "1 file(s)" in findings[1].message


# ---------------------------------------------------------------------------
# Bucket derivation from connectionName
# ---------------------------------------------------------------------------


class TestBucketDerivation:
    """Bucket name is resolved from DataZone project connections."""

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_resolved_connection_uses_real_bucket(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.my_bucket", "actual-bucket-name")
        )
        items = [
            _StorageConfig(
                name="x", connectionName="default.my_bucket", targetDirectory=""
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "actual-bucket-name" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_unresolved_connection_shows_placeholder(self, mock_conns, checker):
        """When connection can't be resolved, show an unresolved placeholder."""
        mock_conns.return_value = {}
        items = [
            _StorageConfig(name="x", connectionName="mybucket", targetDirectory="")
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "<unresolved:mybucket>" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_empty_connection_name(self, mock_conns, checker):
        mock_conns.return_value = {}
        items = [_StorageConfig(name="x", connectionName="", targetDirectory="")]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        # Empty connection → no connection to resolve, shows unknown
        assert "<unknown>" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_none_connection_name(self, mock_conns, checker):
        mock_conns.return_value = {}
        items = [_StorageConfig(name="x", connectionName=None, targetDirectory="")]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "<unknown>" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_null_project_connections_shows_unresolved(self, mock_conns, checker):
        """When _get_project_connections returns None, show unresolved."""
        mock_conns.return_value = None
        items = [
            _StorageConfig(
                name="x", connectionName="default.s3_shared", targetDirectory=""
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "<unresolved:default.s3_shared>" in findings[0].message


# ---------------------------------------------------------------------------
# Prefix from targetDirectory
# ---------------------------------------------------------------------------


class TestPrefixReporting:
    """targetDirectory is reported as the S3 prefix."""

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_non_empty_prefix(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="x",
                connectionName="default.s3_shared",
                targetDirectory="my/prefix",
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "my/prefix" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_empty_prefix(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="x", connectionName="default.s3_shared", targetDirectory=""
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "prefix ''" in findings[0].message

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_none_target_directory(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="x", connectionName="default.s3_shared", targetDirectory=None
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert "prefix ''" in findings[0].message


# ---------------------------------------------------------------------------
# Finding metadata
# ---------------------------------------------------------------------------


class TestFindingMetadata:
    """Each finding carries resource, service, and details."""

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_finding_has_resource(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory="src"
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files={"code/a.py"})

        findings = checker.check(ctx)
        assert findings[0].resource == "code"

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_finding_has_service(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory="src"
            )
        ]
        ctx = _make_context(storage_items=items, bundle_files=set())

        findings = checker.check(ctx)
        assert findings[0].service == "s3"

    @patch(
        "smus_cicd.commands.dry_run.checkers.storage_checker.get_project_connections"
    )
    def test_finding_has_details(self, mock_conns, checker):
        mock_conns.return_value = _mock_connections(
            ("default.s3_shared", "real-bucket")
        )
        items = [
            _StorageConfig(
                name="code", connectionName="default.s3_shared", targetDirectory="src"
            )
        ]
        ctx = _make_context(
            storage_items=items, bundle_files={"code/a.py", "code/b.py"}
        )

        findings = checker.check(ctx)
        details = findings[0].details
        assert details is not None
        assert details["bucket"] == "real-bucket"
        assert details["prefix"] == "src"
        assert details["file_count"] == 2

    def test_skip_finding_has_service(self, checker):
        ctx = _make_context(storage_items=[])
        findings = checker.check(ctx)
        assert findings[0].service == "s3"

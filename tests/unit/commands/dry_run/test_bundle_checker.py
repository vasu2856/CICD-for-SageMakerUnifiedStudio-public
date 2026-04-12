"""Unit tests for BundleChecker.

Tests valid ZIP, missing artifacts, catalog validation, bad ZIP,
bundle resolution from ./artifacts, and local-only storage items.

Requirements: 10.5
"""

import json
import zipfile

import pytest

from smus_cicd.commands.dry_run.checkers.bundle_checker import BundleChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(tmp_path, files: dict, name: str = "bundle.zip") -> str:
    """Create a ZIP archive with the given file mapping {path: content}."""
    zip_path = str(tmp_path / name)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return zip_path


def _make_manifest_stub(
    storage_names=None,
    git_names=None,
    app_name="TestApp",
    local_storage_names=None,
):
    """Return a minimal manifest-like object for context."""
    from dataclasses import dataclass, field
    from typing import List, Optional

    @dataclass
    class _StorageContent:
        name: str
        connectionName: Optional[str] = "default.s3_shared"
        include: list = field(default_factory=list)

    @dataclass
    class _GitContent:
        repository: str
        url: str

    @dataclass
    class _Content:
        storage: List[_StorageContent] = field(default_factory=list)
        git: List[_GitContent] = field(default_factory=list)

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

    @dataclass
    class _ProjectConfig:
        name: str = "test-project"
        create: bool = False

    @dataclass
    class _DomainConfig:
        region: str = "us-east-1"

    @dataclass
    class _TargetConfig:
        project: _ProjectConfig = field(default_factory=_ProjectConfig)
        domain: _DomainConfig = field(default_factory=_DomainConfig)
        stage: str = "dev"
        deployment_configuration: Optional[_DeploymentConfiguration] = None
        environment_variables: Optional[dict] = None

    @dataclass
    class _Manifest:
        application_name: str = "TestApp"
        content: Optional[_Content] = None

    # Build content storage items
    content_storage = []
    for name in storage_names or []:
        content_storage.append(_StorageContent(name=name))
    for name in local_storage_names or []:
        content_storage.append(_StorageContent(name=name, connectionName=None))

    content_git = [
        _GitContent(repository=n, url=f"https://git/{n}") for n in (git_names or [])
    ]

    content = _Content(storage=content_storage, git=content_git)

    # Build deployment configuration
    dep_storage = [_StorageConfig(name=n) for n in (storage_names or [])]
    dep_storage += [_StorageConfig(name=n) for n in (local_storage_names or [])]
    dep_git = [_GitTargetConfig(name=n) for n in (git_names or [])]
    dep_config = _DeploymentConfiguration(storage=dep_storage, git=dep_git)

    target_config = _TargetConfig(deployment_configuration=dep_config)
    manifest = _Manifest(application_name=app_name, content=content)

    return manifest, target_config


@pytest.fixture
def checker():
    return BundleChecker()


# ---------------------------------------------------------------------------
# Tests: Valid ZIP enumeration
# ---------------------------------------------------------------------------


class TestBundleEnumeration:
    """Tests for opening and enumerating bundle files."""

    def test_valid_zip_enumerates_files(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "data/file1.csv": "a,b",
                "data/file2.csv": "c,d",
            },
        )
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert any("2 file(s)" in f.message for f in ok_findings)
        assert context.bundle_files == {"data/file1.csv", "data/file2.csv"}

    def test_empty_zip(self, checker, tmp_path):
        bundle = _make_zip(tmp_path, {})
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        assert any("0 file(s)" in f.message for f in ok_findings)


class TestInvalidBundle:
    """Tests for invalid or missing bundle files."""

    def test_bad_zip_returns_error(self, checker, tmp_path):
        bad_file = tmp_path / "bad.zip"
        bad_file.write_text("not a zip")
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=str(bad_file),
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "invalid zip" in errors[0].message.lower()

    def test_missing_bundle_file_returns_error(self, checker, tmp_path):
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=str(tmp_path / "nonexistent.zip"),
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "not found" in errors[0].message.lower()


# ---------------------------------------------------------------------------
# Tests: Storage item cross-referencing
# ---------------------------------------------------------------------------


class TestStorageItems:
    """Tests for cross-referencing storage items against bundle contents."""

    def test_storage_item_found_in_bundle(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "my_data/file1.csv": "data",
                "my_data/file2.csv": "data",
            },
        )
        manifest, target_config = _make_manifest_stub(storage_names=["my_data"])
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("my_data" in m and "2 file(s)" in m for m in ok_msgs)

    def test_missing_storage_item_returns_error(self, checker, tmp_path):
        bundle = _make_zip(tmp_path, {"other/file.txt": "x"})
        manifest, target_config = _make_manifest_stub(storage_names=["my_data"])
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "my_data" in errors[0].message
        assert errors[0].resource == "my_data"

    def test_local_storage_item_skipped(self, checker, tmp_path):
        """Local-only storage items (no connectionName) should not be checked in bundle."""
        bundle = _make_zip(tmp_path, {"other/file.txt": "x"})
        manifest, target_config = _make_manifest_stub(
            local_storage_names=["local_data"]
        )
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("local filesystem" in m for m in ok_msgs)


# ---------------------------------------------------------------------------
# Tests: Git item cross-referencing
# ---------------------------------------------------------------------------


class TestGitItems:
    """Tests for cross-referencing git items against bundle contents."""

    def test_git_item_found_in_bundle(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "repositories/my_repo/README.md": "# Repo",
                "repositories/my_repo/src/main.py": "print('hi')",
            },
        )
        manifest, target_config = _make_manifest_stub(git_names=["my_repo"])
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("my_repo" in m and "2 file(s)" in m for m in ok_msgs)

    def test_missing_git_item_returns_error(self, checker, tmp_path):
        bundle = _make_zip(tmp_path, {"other/file.txt": "x"})
        manifest, target_config = _make_manifest_stub(git_names=["my_repo"])
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "my_repo" in errors[0].message
        assert "repositories/my_repo/" in errors[0].message


# ---------------------------------------------------------------------------
# Tests: Catalog export validation
# ---------------------------------------------------------------------------


class TestCatalogExport:
    """Tests for catalog/catalog_export.json validation."""

    def test_valid_catalog_export(self, checker, tmp_path):
        catalog = {
            "metadata": {"version": "1.0"},
            "glossaries": [
                {"sourceId": "g1", "name": "Glossary1"},
            ],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        bundle = _make_zip(
            tmp_path,
            {
                "catalog/catalog_export.json": json.dumps(catalog),
            },
        )
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        assert context.catalog_data == catalog
        ok_msgs = [f.message for f in findings if f.severity == Severity.OK]
        assert any("1 resource(s)" in m for m in ok_msgs)

    def test_invalid_catalog_json(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "catalog/catalog_export.json": "{ not valid json",
            },
        )
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "invalid json" in errors[0].message.lower()
        assert context.catalog_data is None

    def test_catalog_missing_required_keys(self, checker, tmp_path):
        catalog = {"metadata": {"version": "1.0"}}  # missing resource-type keys
        bundle = _make_zip(
            tmp_path,
            {
                "catalog/catalog_export.json": json.dumps(catalog),
            },
        )
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "missing required key(s)" in errors[0].message
        assert context.catalog_data is None

    def test_catalog_not_a_dict(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "catalog/catalog_export.json": json.dumps([1, 2, 3]),
            },
        )
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "JSON object" in errors[0].message

    def test_no_catalog_in_bundle(self, checker, tmp_path):
        """When no catalog_export.json is present, no catalog findings are produced."""
        bundle = _make_zip(tmp_path, {"data/file.txt": "x"})
        manifest, target_config = _make_manifest_stub()
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        catalog_findings = [
            f for f in findings if f.resource == "catalog/catalog_export.json"
        ]
        assert len(catalog_findings) == 0
        assert context.catalog_data is None


# ---------------------------------------------------------------------------
# Tests: Bundle resolution
# ---------------------------------------------------------------------------


class TestBundleResolution:
    """Tests for bundle path resolution when not explicitly provided."""

    def test_no_bundle_no_manifest_returns_error(self, checker):
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=None,
            bundle_path=None,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "manifest not loaded" in errors[0].message.lower()


# ---------------------------------------------------------------------------
# Tests: Combined scenarios
# ---------------------------------------------------------------------------


class TestCombinedScenarios:
    """Tests for combined storage, git, and catalog validation."""

    def test_all_items_present(self, checker, tmp_path):
        catalog = {
            "metadata": {"version": "1.0"},
            "glossaries": [{"sourceId": "g1", "name": "Glossary1"}],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        bundle = _make_zip(
            tmp_path,
            {
                "my_data/file.csv": "data",
                "repositories/my_repo/main.py": "code",
                "catalog/catalog_export.json": json.dumps(catalog),
            },
        )
        manifest, target_config = _make_manifest_stub(
            storage_names=["my_data"], git_names=["my_repo"]
        )
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        assert context.catalog_data == catalog

    def test_mixed_present_and_missing(self, checker, tmp_path):
        bundle = _make_zip(
            tmp_path,
            {
                "my_data/file.csv": "data",
                # missing repositories/my_repo/
            },
        )
        manifest, target_config = _make_manifest_stub(
            storage_names=["my_data"], git_names=["my_repo"]
        )
        context = DryRunContext(
            manifest_file="manifest.yaml",
            manifest=manifest,
            target_config=target_config,
            config={"region": "us-east-1"},
            bundle_path=bundle,
        )

        findings = checker.check(context)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "my_repo" in errors[0].message

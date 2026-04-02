"""Unit tests for deploy command catalog import integration."""

import json
import os
import tempfile
import zipfile
from unittest.mock import Mock, patch

import pytest

from smus_cicd.commands.deploy import _import_catalog_from_bundle


@pytest.fixture
def mock_target_config():
    """Create a mock target configuration."""
    config = Mock()
    config.deployment_configuration = Mock()
    config.deployment_configuration.catalog = None
    config.domain = Mock()
    config.domain.region = "us-east-1"
    config.project = Mock()
    config.project.name = "test-project"
    config.name = "dev"
    return config


@pytest.fixture
def mock_config():
    """Create a mock configuration dictionary."""
    return {
        "region": "us-east-1",
        "domain_id": "dzd_test123",
        "domain_name": "test-domain",
    }


@pytest.fixture
def sample_catalog_export():
    """Create a sample catalog export JSON."""
    return {
        "metadata": {
            "sourceProjectId": "source-proj-123",
            "sourceDomainId": "dzd_source123",
            "exportTimestamp": "2025-01-01T00:00:00Z",
            "resourceTypes": ["glossaries", "assets"],
        },
        "glossaries": [
            {
                "sourceId": "gloss-123",
                "name": "Test Glossary",
                "description": "A test glossary",
                "status": "ENABLED",
            }
        ],
        "glossaryTerms": [],
        "formTypes": [],
        "assetTypes": [],
        "assets": [
            {
                "sourceId": "asset-456",
                "name": "Test Asset",
                "description": "A test asset",
                "typeIdentifier": "amazon.datazone.GlueTableAssetType",
            }
        ],
        "dataProducts": [],
    }


def create_bundle_with_catalog(catalog_data):
    """Create a temporary bundle ZIP with catalog export."""
    temp_dir = tempfile.mkdtemp()
    bundle_path = os.path.join(temp_dir, "test-bundle.zip")

    with zipfile.ZipFile(bundle_path, "w") as zip_ref:
        # Create catalog directory structure
        catalog_dir = os.path.join(temp_dir, "catalog")
        os.makedirs(catalog_dir, exist_ok=True)
        catalog_file = os.path.join(catalog_dir, "catalog_export.json")

        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        zip_ref.write(catalog_file, "catalog/catalog_export.json")

    return bundle_path, temp_dir


def create_bundle_without_catalog():
    """Create a temporary bundle ZIP without catalog export."""
    temp_dir = tempfile.mkdtemp()
    bundle_path = os.path.join(temp_dir, "test-bundle.zip")

    with zipfile.ZipFile(bundle_path, "w") as _zip_ref:  # noqa: F841
        # Create an empty bundle
        pass

    return bundle_path, temp_dir


def _make_manifest(skip_publish=False):
    """Create a mock manifest with catalog config."""
    manifest = Mock()
    manifest.content = Mock()
    manifest.content.catalog = Mock()
    manifest.content.catalog.skipPublish = skip_publish
    return manifest


def test_import_catalog_from_bundle_success(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test successful catalog import from bundle."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            mock_import.return_value = {
                "created": 2,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "published": 0,
            }

            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            assert result is True
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args[0][0] == "dzd_test123"  # domain_id
            assert call_args[0][1] == "proj-123"  # project_id
            assert call_args[0][3] == "us-east-1"  # region
            # skip_publish defaults to False when no manifest passed
            assert call_args[1]["skip_publish"] is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_missing_file(mock_target_config, mock_config):
    """Test catalog import when catalog_export.json is missing (backward compatible)."""
    bundle_path, temp_dir = create_bundle_without_catalog()

    try:
        result = _import_catalog_from_bundle(
            bundle_path, mock_target_config, mock_config
        )

        # Should skip silently and return True
        assert result is True
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_disabled(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test catalog import when disabled in deployment configuration."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    # Configure catalog as disabled
    mock_target_config.deployment_configuration.catalog = {"disable": True}

    try:
        result = _import_catalog_from_bundle(
            bundle_path, mock_target_config, mock_config
        )

        # Should skip and return True
        assert result is True
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_all_failed(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test catalog import when all imports fail."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            # All imports failed
            mock_import.return_value = {
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 2,
                "published": 0,
            }

            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            # Should return False when all fail
            assert result is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_partial_failure(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test catalog import with partial failures."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            # Some imports succeeded
            mock_import.return_value = {
                "created": 1,
                "updated": 0,
                "skipped": 0,
                "failed": 1,
                "published": 0,
            }

            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            # Should return True when at least one succeeds
            assert result is True
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_malformed_json(mock_target_config, mock_config):
    """Test catalog import with malformed JSON."""
    temp_dir = tempfile.mkdtemp()
    bundle_path = os.path.join(temp_dir, "test-bundle.zip")

    try:
        with zipfile.ZipFile(bundle_path, "w") as zip_ref:
            # Create catalog directory with malformed JSON
            catalog_dir = os.path.join(temp_dir, "catalog")
            os.makedirs(catalog_dir, exist_ok=True)
            catalog_file = os.path.join(catalog_dir, "catalog_export.json")

            with open(catalog_file, "w") as f:
                f.write("{ invalid json }")

            zip_ref.write(catalog_file, "catalog/catalog_export.json")

        result = _import_catalog_from_bundle(
            bundle_path, mock_target_config, mock_config
        )

        # Should return False for malformed JSON
        assert result is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_project_not_found(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test catalog import when project is not found."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            # Project not found
            mock_get_project.return_value = None

            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            # Should return False when project not found
            assert result is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_skipped_counts_reported(
    mock_target_config, mock_config, sample_catalog_export, capsys
):
    """Test that skipped (extra in target) counts are reported in the summary output."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            mock_import.return_value = {
                "created": 1,
                "updated": 1,
                "skipped": 3,
                "failed": 0,
                "published": 0,
            }

            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            assert result is True
            captured = capsys.readouterr()
            assert "Skipped (extra in target): 3" in captured.out
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_published_counts_with_skip_publish_false(
    mock_target_config, mock_config, sample_catalog_export, capsys
):
    """Test that published counts are reported when skipPublish=false."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)
    manifest = _make_manifest(skip_publish=False)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            mock_import.return_value = {
                "created": 2,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "published": 2,
            }

            result = _import_catalog_from_bundle(
                bundle_path,
                mock_target_config,
                mock_config,
                manifest=manifest,
            )

            assert result is True
            # Verify skip_publish=False was passed to import_catalog
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args[1]["skip_publish"] is False
            # Verify published count in output
            captured = capsys.readouterr()
            assert "Published: 2" in captured.out
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_skip_publish_false_by_default(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test skip_publish=false by default when catalog config is missing from manifest."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    # Manifest with no catalog config
    manifest = Mock()
    manifest.content = Mock()
    manifest.content.catalog = None

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            mock_import.return_value = {
                "created": 1,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "published": 1,
            }

            result = _import_catalog_from_bundle(
                bundle_path,
                mock_target_config,
                mock_config,
                manifest=manifest,
            )

            assert result is True
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args[1]["skip_publish"] is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)


def test_import_catalog_from_bundle_skip_publish_false_no_manifest(
    mock_target_config, mock_config, sample_catalog_export
):
    """Test skip_publish=false when no manifest is passed at all."""
    bundle_path, temp_dir = create_bundle_with_catalog(sample_catalog_export)

    try:
        with patch(
            "smus_cicd.helpers.datazone.get_domain_from_target_config"
        ) as mock_get_domain, patch(
            "smus_cicd.helpers.datazone.get_project_id_by_name"
        ) as mock_get_project, patch(
            "smus_cicd.helpers.catalog_import.import_catalog"
        ) as mock_import:
            mock_get_domain.return_value = ("dzd_test123", "test-domain")
            mock_get_project.return_value = "proj-123"
            mock_import.return_value = {
                "created": 1,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "published": 1,
            }

            # No manifest passed
            result = _import_catalog_from_bundle(
                bundle_path, mock_target_config, mock_config
            )

            assert result is True
            mock_import.assert_called_once()
            call_args = mock_import.call_args
            assert call_args[1]["skip_publish"] is False
    finally:
        import shutil

        shutil.rmtree(temp_dir)

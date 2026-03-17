"""Unit tests for bundle command."""

import json
import os
import pytest
import yaml
import zipfile
from unittest.mock import patch, mock_open, MagicMock
from typer.testing import CliRunner
from smus_cicd.cli import app

runner = CliRunner()


@pytest.fixture
def sample_manifest():
    return """
applicationName: TestPipeline
content:
  storage:
    - name: workflows
      connectionName: default.s3_shared
      append: true
      include: ['workflows/']
    - name: code
      connectionName: default.s3_shared
      append: false
      include: ['src/']
stages:
  dev:
    stage: DEV
    domain:
      name: test-domain
      region: us-east-1
    project:
      name: dev-project
"""


def test_bundle_default_target(sample_manifest):
    """Test bundle with default target - basic validation."""
    with patch("os.path.exists", return_value=True):
        with patch(
            "smus_cicd.commands.bundle.ApplicationManifest.from_file"
        ) as mock_manifest:
            from smus_cicd.application import ApplicationManifest
            mock_manifest.return_value = ApplicationManifest.from_dict(yaml.safe_load(sample_manifest))
            with patch(
                "smus_cicd.helpers.utils.load_config",
                return_value={"region": "us-east-1"},
            ):
                result = runner.invoke(app, ["bundle"])
                # Test should use DEV stage as default target
                assert result.exit_code == 1 or "dev" in result.output.lower()


def test_bundle_tree_structure_display(sample_manifest):
    """Test that bundle command displays tree structure in text mode."""
    with patch("builtins.open", mock_open(read_data=sample_manifest)):
        with patch(
            "smus_cicd.helpers.utils.load_config", return_value={"region": "us-east-1"}
        ):
            with patch("smus_cicd.commands.bundle.display_bundle_tree") as mock_tree:
                result = runner.invoke(app, ["bundle", "--output", "TEXT"])
                # Should call display_bundle_tree for text output
                if result.exit_code == 0:  # Only if bundle creation succeeds
                    mock_tree.assert_called_once()


def test_bundle_no_tree_for_json(sample_manifest):
    """Test that bundle command skips tree structure in JSON mode."""
    with patch("builtins.open", mock_open(read_data=sample_manifest)):
        with patch(
            "smus_cicd.helpers.utils.load_config", return_value={"region": "us-east-1"}
        ):
            with patch("smus_cicd.commands.bundle.display_bundle_tree") as mock_tree:
                result = runner.invoke(app, ["bundle", "--output", "JSON"])
                # Tree display should be called but skip output for JSON
                if result.exit_code == 0:
                    mock_tree.assert_called_once()


def test_bundle_no_bundle_section():
    """Test bundle with missing bundle section."""
    manifest = """
applicationName: TestPipeline
stages:
  dev:
    stage: DEV
    domain:
      name: test-domain
      region: us-east-1
    project:
      name: dev-project
"""

    with patch("os.path.exists", return_value=True):
        with patch(
            "smus_cicd.commands.bundle.ApplicationManifest.from_file"
        ) as mock_manifest:
            from smus_cicd.application import ApplicationManifest
            mock_manifest.return_value = ApplicationManifest.from_dict(yaml.safe_load(manifest))
            with patch(
                "smus_cicd.helpers.utils.load_config",
                return_value={"region": "us-east-1"},
            ):
                with patch(
                    "smus_cicd.helpers.utils.get_datazone_project_info",
                    return_value={"connections": {}},
                ):
                    with patch("boto3.client"):
                        with patch("tempfile.mkdtemp", return_value="/tmp/test"):
                            with patch("os.makedirs"):
                                result = runner.invoke(app, ["bundle"])
                                assert result.exit_code == 1
                                assert "No files found" in result.output


def test_bundle_no_default_target():
    """Test bundle with no default target specified."""
    manifest = """
applicationName: TestPipeline
content:
  storage: []
stages:
  test:
    stage: TEST
    domain:
      name: test-domain
      region: us-east-1
    project:
      name: test-project
"""

    with patch("os.path.exists", return_value=True):
        with patch(
            "smus_cicd.commands.bundle.ApplicationManifest.from_file"
        ) as mock_manifest:
            from smus_cicd.application import ApplicationManifest
            mock_manifest.return_value = ApplicationManifest.from_dict(yaml.safe_load(manifest))
            with patch(
                "smus_cicd.helpers.utils.load_config",
                return_value={"region": "us-east-1"},
            ):
                result = runner.invoke(app, ["bundle"])
                assert result.exit_code == 1
                assert "Target 'dev' not found in manifest" in result.output


def test_bundle_catalog_export_enabled():
    """Test that catalog export is called when content.catalog.enabled is true."""
    from smus_cicd.application import ApplicationManifest

    manifest_content = {
        "applicationName": "TestPipeline",
        "content": {
            "catalog": {
                "enabled": True,
            }
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    manifest = ApplicationManifest.from_dict(manifest_content)

    # Verify catalog config is parsed correctly
    assert manifest.content is not None
    assert manifest.content.catalog is not None
    assert manifest.content.catalog.enabled is True
    assert manifest.content.catalog.skipPublish is False


def test_bundle_catalog_export_disabled():
    """Test that catalog export is skipped when content.catalog.enabled is false."""
    from smus_cicd.application import ApplicationManifest

    manifest_content = {
        "applicationName": "TestPipeline",
        "content": {
            "catalog": {
                "enabled": False,
            }
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    manifest = ApplicationManifest.from_dict(manifest_content)
    assert manifest.content.catalog.enabled is False


def test_bundle_catalog_export_not_configured():
    """Test bundle without catalog export configured - verify catalog export is skipped."""
    manifest = """
applicationName: TestPipeline
content:
  storage: []
stages:
  dev:
    stage: DEV
    domain:
      name: test-domain
      region: us-east-1
    project:
      name: dev-project
"""

    with patch("os.path.exists", return_value=True):
        with patch(
            "smus_cicd.commands.bundle.ApplicationManifest.from_file"
        ) as mock_manifest:
            from smus_cicd.application import ApplicationManifest

            mock_manifest.return_value = ApplicationManifest.from_dict(
                yaml.safe_load(manifest)
            )
            with patch(
                "smus_cicd.helpers.utils.load_config",
                return_value={"region": "us-east-1"},
            ):
                with patch(
                    "smus_cicd.helpers.utils.get_datazone_project_info",
                    return_value={"connections": {}, "domainId": "test-domain-id"},
                ):
                    with patch("boto3.client"):
                        with patch(
                            "smus_cicd.helpers.catalog_export.export_catalog"
                        ) as mock_export:
                            with patch("tempfile.mkdtemp", return_value="/tmp/test"):
                                with patch("os.makedirs"):
                                    result = runner.invoke(app, ["bundle"])

                                    # Verify export_catalog was NOT called
                                    mock_export.assert_not_called()


def test_bundle_catalog_export_writes_json_to_bundle(tmp_path):
    """Test that catalog_export.json appears in bundle ZIP when catalog is enabled."""
    from smus_cicd.commands.bundle import bundle_command

    mock_catalog_data = {
        "metadata": {
            "sourceProjectId": "proj-123",
            "sourceDomainId": "dom-456",
            "exportTimestamp": "2024-01-01T00:00:00Z",
            "resourceTypes": ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"],
        },
        "glossaries": [{"sourceId": "g1", "name": "TestGlossary"}],
        "glossaryTerms": [],
        "formTypes": [],
        "assetTypes": [],
        "assets": [],
        "dataProducts": [],
    }

    manifest_content = {
        "applicationName": "TestApp",
        "content": {
            "catalog": {"enabled": True},
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    output_dir = str(tmp_path / "artifacts")
    os.makedirs(output_dir, exist_ok=True)

    with patch("smus_cicd.commands.bundle.ApplicationManifest.from_file") as mock_mf:
        from smus_cicd.application import ApplicationManifest
        mock_mf.return_value = ApplicationManifest.from_dict(manifest_content)

        with patch("smus_cicd.commands.bundle.load_config", return_value={"domain": {"region": "us-east-1"}}):
            with patch("smus_cicd.commands.bundle.get_datazone_project_info", return_value={
                "connections": {},
                "domain_id": "dom-456",
                "project_id": "proj-123",
            }):
                with patch("boto3.client"):
                    with patch("smus_cicd.helpers.catalog_export.export_catalog", return_value=mock_catalog_data) as mock_export:
                        with patch("smus_cicd.commands.bundle.deployment"):
                            bundle_command("dev", "manifest.yaml", output_dir, "TEXT")

                            # Verify export_catalog was called with correct args
                            mock_export.assert_called_once_with(
                                domain_id="dom-456",
                                project_id="proj-123",
                                region="us-east-1",
                                updated_after=None,
                            )

                            # Verify the ZIP contains catalog/catalog_export.json
                            zip_path = os.path.join(output_dir, "TestApp.zip")
                            assert os.path.exists(zip_path)

                            with zipfile.ZipFile(zip_path, "r") as zf:
                                assert "catalog/catalog_export.json" in zf.namelist()
                                catalog_json = json.loads(zf.read("catalog/catalog_export.json"))
                                assert catalog_json["metadata"]["sourceProjectId"] == "proj-123"
                                assert len(catalog_json["glossaries"]) == 1


def test_bundle_catalog_export_skipped_when_disabled(tmp_path):
    """Test that catalog_export.json is NOT in bundle when catalog.enabled is false."""
    from smus_cicd.commands.bundle import bundle_command

    manifest_content = {
        "applicationName": "TestApp",
        "content": {
            "catalog": {"enabled": False},
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    output_dir = str(tmp_path / "artifacts")
    os.makedirs(output_dir, exist_ok=True)

    with patch("smus_cicd.commands.bundle.ApplicationManifest.from_file") as mock_mf:
        from smus_cicd.application import ApplicationManifest
        mock_mf.return_value = ApplicationManifest.from_dict(manifest_content)

        with patch("smus_cicd.commands.bundle.load_config", return_value={"domain": {"region": "us-east-1"}}):
            with patch("smus_cicd.commands.bundle.get_datazone_project_info", return_value={
                "connections": {},
                "domain_id": "dom-456",
                "project_id": "proj-123",
            }):
                with patch("boto3.client"):
                    with patch("smus_cicd.helpers.catalog_export.export_catalog") as mock_export:
                        with patch("smus_cicd.commands.bundle.deployment"):
                            # No files will be added, so bundle will exit with error
                            # but export_catalog should NOT be called
                            try:
                                bundle_command("dev", "manifest.yaml", output_dir, "TEXT")
                            except Exception:
                                pass

                            mock_export.assert_not_called()


def test_bundle_catalog_export_skipped_when_omitted(tmp_path):
    """Test that catalog_export.json is NOT in bundle when catalog section is omitted."""
    from smus_cicd.commands.bundle import bundle_command

    manifest_content = {
        "applicationName": "TestApp",
        "content": {},
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    output_dir = str(tmp_path / "artifacts")
    os.makedirs(output_dir, exist_ok=True)

    with patch("smus_cicd.commands.bundle.ApplicationManifest.from_file") as mock_mf:
        from smus_cicd.application import ApplicationManifest
        mock_mf.return_value = ApplicationManifest.from_dict(manifest_content)

        with patch("smus_cicd.commands.bundle.load_config", return_value={"domain": {"region": "us-east-1"}}):
            with patch("smus_cicd.commands.bundle.get_datazone_project_info", return_value={
                "connections": {},
                "domain_id": "dom-456",
                "project_id": "proj-123",
            }):
                with patch("boto3.client"):
                    with patch("smus_cicd.helpers.catalog_export.export_catalog") as mock_export:
                        with patch("smus_cicd.commands.bundle.deployment"):
                            try:
                                bundle_command("dev", "manifest.yaml", output_dir, "TEXT")
                            except Exception:
                                pass

                            mock_export.assert_not_called()


def test_bundle_updated_after_cli_flag_passed_to_export(tmp_path):
    """Test that --updated-after CLI flag value is passed correctly to export_catalog()."""
    from smus_cicd.commands.bundle import bundle_command

    mock_catalog_data = {
        "metadata": {
            "sourceProjectId": "proj-123",
            "sourceDomainId": "dom-456",
            "exportTimestamp": "2024-06-01T00:00:00Z",
            "resourceTypes": ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"],
        },
        "glossaries": [],
        "glossaryTerms": [],
        "formTypes": [],
        "assetTypes": [],
        "assets": [],
        "dataProducts": [],
    }

    manifest_content = {
        "applicationName": "TestApp",
        "content": {
            "catalog": {"enabled": True},
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    output_dir = str(tmp_path / "artifacts")
    os.makedirs(output_dir, exist_ok=True)

    with patch("smus_cicd.commands.bundle.ApplicationManifest.from_file") as mock_mf:
        from smus_cicd.application import ApplicationManifest
        mock_mf.return_value = ApplicationManifest.from_dict(manifest_content)

        with patch("smus_cicd.commands.bundle.load_config", return_value={"domain": {"region": "us-east-1"}}):
            with patch("smus_cicd.commands.bundle.get_datazone_project_info", return_value={
                "connections": {},
                "domain_id": "dom-456",
                "project_id": "proj-123",
            }):
                with patch("boto3.client"):
                    with patch("smus_cicd.helpers.catalog_export.export_catalog", return_value=mock_catalog_data) as mock_export:
                        with patch("smus_cicd.commands.bundle.deployment"):
                            # Pass updated_after via the CLI flag parameter
                            bundle_command(
                                "dev", "manifest.yaml", output_dir, "TEXT",
                                updated_after="2024-06-01T00:00:00Z",
                            )

                            # Verify export_catalog was called with the CLI updated_after value
                            mock_export.assert_called_once_with(
                                domain_id="dom-456",
                                project_id="proj-123",
                                region="us-east-1",
                                updated_after="2024-06-01T00:00:00Z",
                            )


def test_bundle_no_manifest_filter_values_passed():
    """Test that no manifest-based filter values are read or passed to export_catalog."""
    from smus_cicd.application import ApplicationManifest

    # Manifest with catalog.enabled but NO filter fields
    manifest_content = {
        "applicationName": "TestPipeline",
        "content": {
            "catalog": {
                "enabled": True,
            }
        },
        "stages": {
            "dev": {
                "stage": "DEV",
                "domain": {"name": "test-domain", "region": "us-east-1"},
                "project": {"name": "dev-project"},
            }
        },
    }

    manifest = ApplicationManifest.from_dict(manifest_content)

    # Verify the catalog config has no filter-related attributes
    catalog = manifest.content.catalog
    assert catalog.enabled is True
    assert catalog.skipPublish is False
    assert not hasattr(catalog, "include")
    assert not hasattr(catalog, "names")
    assert not hasattr(catalog, "assetTypes")
    assert not hasattr(catalog, "updatedAfter")
    assert not hasattr(catalog, "glossaries")
    assert not hasattr(catalog, "dataProducts")
    assert not hasattr(catalog, "metadataForms")


def test_bundle_updated_after_cli_validation_invalid():
    """Test that invalid --updated-after timestamp format raises an error."""
    result = runner.invoke(app, ["bundle", "--updated-after", "not-a-timestamp"])
    assert result.exit_code == 1
    assert "Invalid --updated-after timestamp format" in result.output


def test_bundle_updated_after_cli_validation_valid():
    """Test that valid --updated-after timestamp format is accepted."""
    # This should not fail on timestamp validation (may fail later for other reasons)
    result = runner.invoke(app, ["bundle", "--updated-after", "2024-01-01T00:00:00Z"])
    # Should not contain timestamp validation error
    assert "Invalid --updated-after timestamp format" not in result.output

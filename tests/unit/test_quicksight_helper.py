"""Unit tests for QuickSight helper."""

import unittest
from unittest.mock import MagicMock, patch

from smus_cicd.helpers.quicksight import (
    QuickSightDeploymentError,
    export_dashboard,
    grant_dashboard_permissions,
    import_dashboard,
    poll_export_job,
    poll_import_job,
)


class TestQuickSightHelper(unittest.TestCase):
    """Test QuickSight helper functions."""

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    def test_export_dashboard_success(self, mock_boto_client):
        """Test successful dashboard export."""
        mock_qs = MagicMock()
        mock_qs.start_asset_bundle_export_job.return_value = {
            "AssetBundleExportJobId": "export-123"
        }
        mock_boto_client.return_value = mock_qs

        job_id = export_dashboard("dash-1", "123456789012", "us-east-1")

        self.assertEqual(job_id, "export-123")
        mock_qs.start_asset_bundle_export_job.assert_called_once()

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    def test_export_dashboard_failure(self, mock_boto_client):
        """Test dashboard export failure."""
        mock_qs = MagicMock()
        mock_qs.start_asset_bundle_export_job.side_effect = Exception("API error")
        mock_boto_client.return_value = mock_qs

        with self.assertRaises(QuickSightDeploymentError):
            export_dashboard("dash-1", "123456789012", "us-east-1")

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    @patch("smus_cicd.helpers.quicksight.time.sleep")
    def test_poll_export_job_success(self, mock_sleep, mock_boto_client):
        """Test successful export job polling."""
        mock_qs = MagicMock()
        mock_qs.describe_asset_bundle_export_job.return_value = {
            "JobStatus": "SUCCESSFUL",
            "DownloadUrl": "https://example.com/bundle.zip",
        }
        mock_boto_client.return_value = mock_qs

        url = poll_export_job("export-123", "123456789012", "us-east-1")

        self.assertEqual(url, "https://example.com/bundle.zip")

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    @patch("smus_cicd.helpers.quicksight.time.sleep")
    def test_poll_export_job_failure(self, mock_sleep, mock_boto_client):
        """Test export job polling with failure."""
        mock_qs = MagicMock()
        mock_qs.describe_asset_bundle_export_job.return_value = {
            "JobStatus": "FAILED",
            "Errors": ["Export error"],
        }
        mock_boto_client.return_value = mock_qs

        with self.assertRaises(QuickSightDeploymentError):
            poll_export_job("export-123", "123456789012", "us-east-1")

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    @patch("smus_cicd.helpers.quicksight._download_bundle")
    def test_import_dashboard_success(self, mock_download, mock_boto_client):
        """Test successful dashboard import."""
        mock_download.return_value = b"bundle-content"
        mock_qs = MagicMock()
        mock_qs.start_asset_bundle_import_job.return_value = {
            "AssetBundleImportJobId": "import-456"
        }
        mock_boto_client.return_value = mock_qs

        job_id = import_dashboard(
            "https://example.com/bundle.zip", "123456789012", "us-east-1"
        )

        self.assertEqual(job_id, "import-456")
        mock_qs.start_asset_bundle_import_job.assert_called_once()

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    @patch("smus_cicd.helpers.quicksight.time.sleep")
    def test_poll_import_job_success(self, mock_sleep, mock_boto_client):
        """Test successful import job polling."""
        mock_qs = MagicMock()
        mock_qs.describe_asset_bundle_import_job.return_value = {
            "JobStatus": "SUCCESSFUL",
            "AssetBundleImportJobId": "import-456",
        }
        mock_boto_client.return_value = mock_qs

        result = poll_import_job("import-456", "123456789012", "us-east-1")

        self.assertEqual(result["JobStatus"], "SUCCESSFUL")

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    def test_grant_permissions_success(self, mock_boto_client):
        """Test successful permission grant."""
        mock_qs = MagicMock()
        mock_boto_client.return_value = mock_qs

        permissions = [{"principal": "user1", "actions": ["READ"]}]
        result = grant_dashboard_permissions(
            "dash-1", "123456789012", "us-east-1", permissions
        )

        self.assertTrue(result)
        mock_qs.update_dashboard_permissions.assert_called_once()

    @patch("smus_cicd.helpers.quicksight.boto3.client")
    def test_grant_permissions_empty(self, mock_boto_client):
        """Test permission grant with empty list."""
        result = grant_dashboard_permissions(
            "dash-1", "123456789012", "us-east-1", []
        )

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()


class TestResolveResourcePrefix(unittest.TestCase):
    """Test resolve_resource_prefix."""

    def test_replaces_stage_name(self):
        from smus_cicd.helpers.quicksight import resolve_resource_prefix

        qs = {"overrideParameters": {"ResourceIdOverrideConfiguration": {
            "PrefixForAllResources": "deployed-{stage.name}-covid-"
        }}}
        assert resolve_resource_prefix("dev", qs) == "deployed-dev-covid-"

    def test_empty_config(self):
        from smus_cicd.helpers.quicksight import resolve_resource_prefix

        assert resolve_resource_prefix("dev", {}) == ""

    def test_no_variable(self):
        from smus_cicd.helpers.quicksight import resolve_resource_prefix

        qs = {"overrideParameters": {"ResourceIdOverrideConfiguration": {
            "PrefixForAllResources": "static-"
        }}}
        assert resolve_resource_prefix("dev", qs) == "static-"


class TestResolveResourceIdsFromOverrides(unittest.TestCase):
    """Test resolve_resource_ids_from_overrides."""

    def test_dashboards_only(self):
        from smus_cicd.helpers.quicksight import resolve_resource_ids_from_overrides

        qs = {"overrideParameters": {
            "ResourceIdOverrideConfiguration": {"PrefixForAllResources": "pfx-"},
            "Dashboards": [{"DashboardId": "d1", "Name": "Dash1"}],
        }}
        result = resolve_resource_ids_from_overrides("dev", qs)
        assert "dashboards" in result
        assert result["dashboards"][0]["id"] == "pfx-d1"
        assert result["dashboards"][0]["name"] == "Dash1"
        assert "datasets" not in result
        assert "data_sources" not in result

    def test_all_three_types(self):
        from smus_cicd.helpers.quicksight import resolve_resource_ids_from_overrides

        qs = {"overrideParameters": {
            "ResourceIdOverrideConfiguration": {"PrefixForAllResources": "p-"},
            "Dashboards": [{"DashboardId": "d1", "Name": "D"}],
            "DataSets": [{"DataSetId": "ds1", "Name": "DS"}],
            "DataSources": [{"DataSourceId": "src1", "Name": "S"}],
        }}
        result = resolve_resource_ids_from_overrides("test", qs)
        assert result["dashboards"][0]["id"] == "p-d1"
        assert result["datasets"][0]["id"] == "p-ds1"
        assert result["data_sources"][0]["id"] == "p-src1"

    def test_stage_name_resolved_in_ids(self):
        from smus_cicd.helpers.quicksight import resolve_resource_ids_from_overrides

        qs = {"overrideParameters": {
            "ResourceIdOverrideConfiguration": {"PrefixForAllResources": "pfx-{stage.name}-"},
            "Dashboards": [{"DashboardId": "dash-{stage.name}", "Name": "D"}],
        }}
        result = resolve_resource_ids_from_overrides("prod", qs)
        assert result["dashboards"][0]["id"] == "pfx-prod-dash-prod"

    def test_no_overrides_returns_empty(self):
        from smus_cicd.helpers.quicksight import resolve_resource_ids_from_overrides

        qs = {"overrideParameters": {
            "ResourceIdOverrideConfiguration": {"PrefixForAllResources": "pfx-"},
        }}
        result = resolve_resource_ids_from_overrides("dev", qs)
        assert result == {}

    def test_empty_id_skipped(self):
        from smus_cicd.helpers.quicksight import resolve_resource_ids_from_overrides

        qs = {"overrideParameters": {
            "ResourceIdOverrideConfiguration": {"PrefixForAllResources": "pfx-"},
            "Dashboards": [{"DashboardId": "", "Name": "Empty"}],
        }}
        result = resolve_resource_ids_from_overrides("dev", qs)
        assert result["dashboards"] == []


class TestFindResourcesByPrefix(unittest.TestCase):
    """Test find_resources_by_prefix."""

    @patch("smus_cicd.helpers.quicksight.list_data_sources", return_value=[])
    @patch("smus_cicd.helpers.quicksight.list_datasets", return_value=[])
    @patch("smus_cicd.helpers.quicksight.list_dashboards")
    def test_filters_by_prefix(self, mock_dash, mock_ds, mock_src):
        from smus_cicd.helpers.quicksight import find_resources_by_prefix

        mock_dash.return_value = [
            {"DashboardId": "pfx-d1"},
            {"DashboardId": "other-d2"},
            {"DashboardId": "pfx-d3"},
        ]
        result = find_resources_by_prefix("123", "us-east-1", "pfx-")
        assert len(result["dashboards"]) == 2
        assert all(d["DashboardId"].startswith("pfx-") for d in result["dashboards"])

    @patch("smus_cicd.helpers.quicksight.list_data_sources", return_value=[])
    @patch("smus_cicd.helpers.quicksight.list_datasets", return_value=[])
    @patch("smus_cicd.helpers.quicksight.list_dashboards", return_value=[])
    def test_empty_prefix_returns_empty(self, *_):
        from smus_cicd.helpers.quicksight import find_resources_by_prefix

        result = find_resources_by_prefix("123", "us-east-1", "")
        assert result == {"dashboards": [], "datasets": [], "data_sources": []}

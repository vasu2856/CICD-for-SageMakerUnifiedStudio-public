"""Integration tests for catalog import/export edge cases.

Covers integration tests from the testing guide:
  I7  — Bundle with content.catalog.enabled: false produces ZIP without catalog/
  I19 — Updated resources retain target identifiers after re-deploy
  I22 — Bundle with skipPublish: true skips publishing during deploy

Tests I18, I20, I21, I23, I24 are already covered by:
  - test_catalog_import.py::test_idempotent_redeploy          (I18)
  - test_catalog_import.py::test_deletion_of_resources_not_in_bundle (I20)
  - test_catalog_export.py::test_export_empty_project          (I21)
  - test_catalog_import.py::test_end_to_end_import             (I23)
  - test_catalog_import.py::test_publish_failures_do_not_block (I24)
"""

import importlib.util
import json
import os
import time
import zipfile

import pytest

from tests.integration.base import IntegrationTestBase

# Load helpers from hyphenated directory via importlib
_spec = importlib.util.spec_from_file_location(
    "catalog_test_helpers",
    os.path.join(os.path.dirname(__file__), "catalog_test_helpers.py"),
)
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)


class TestCatalogEdgeCases(IntegrationTestBase):
    """Integration tests for catalog edge cases (I7, I19, I22)."""

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_test_directory()
        self._region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

    def teardown_method(self, method):
        super().teardown_method(method)
        self.cleanup_resources()
        self.cleanup_test_directory()

    # ------------------------------------------------------------------
    # Workflow helpers (bundle + deploy)
    # ------------------------------------------------------------------

    def _setup_and_bundle(self, manifest_name, zip_prefix):
        """Deploy dev, bundle, return (manifest_path, bundle_path)."""
        pf = _h.get_manifest_path(manifest_name)
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip(prefix=zip_prefix) or _h.find_bundle_zip()
        assert bundle, "Bundle ZIP not found"
        return pf, bundle

    def _deploy_to_test(self, manifest_path, bundle_path):
        """Deploy bundle to test stage, return CLI result."""
        return self.run_cli_command(
            [
                "deploy",
                "--targets",
                "test",
                "--bundle-archive-path",
                bundle_path,
                "--manifest",
                manifest_path,
            ]
        )

    # ==================================================================
    # I7 — Bundle with content.catalog.enabled: false
    # ==================================================================
    @pytest.mark.integration
    def test_bundle_catalog_disabled_no_catalog_dir(self):
        """Bundle with content.catalog.enabled: false has no catalog/ directory.

        Validates: P1 (export disabled), I7
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = _h.get_manifest_path("manifest-catalog-disabled.yaml")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"], (
            f"Bundle should succeed (manifest has storage content). "
            f"Output: {r['output']}"
        )

        bundle = _h.find_bundle_zip(prefix="CatalogDisabledTest")
        assert bundle, "Bundle ZIP not found after successful bundle command"

        with zipfile.ZipFile(bundle, "r") as zf:
            catalog_files = [n for n in zf.namelist() if n.startswith("catalog/")]
            assert len(catalog_files) == 0, (
                f"Bundle should NOT contain catalog/ when catalog.enabled "
                f"is false. Found: {catalog_files}"
            )

    # ==================================================================
    # I19 — Updated resources retain target identifiers after re-deploy
    # ==================================================================
    @pytest.mark.integration
    def test_redeploy_retains_target_identifiers(self):
        """Re-deploy updates resources in place — target IDs are unchanged.

        Validates: I19, 5.2
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf, _ = self._setup_and_bundle("manifest-import.yaml", "CatalogImportTest")
        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"RetainIdGlossary-{ts}"
        glossary = _h.create_glossary(
            domain_id, project_id, gname, region, description="retain-id test"
        )
        assert glossary, "Failed to create glossary"

        # Re-bundle to include the new glossary
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = _h.find_bundle_zip(prefix="CatalogImportTest") or _h.find_bundle_zip()
        assert bundle

        # First deploy
        r = self._deploy_to_test(pf, bundle)
        assert r["success"], f"First deploy failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")
        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        first_id = None
        for item in items:
            g = item.get("glossaryItem", {})
            if g.get("name") == gname:
                first_id = g["id"]
                break
        assert first_id, f"Glossary {gname} not found in target after first deploy"

        # Second deploy (same bundle)
        r = self._deploy_to_test(pf, bundle)
        assert r["success"], f"Second deploy failed: {r['output']}"

        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        second_id = None
        for item in items:
            g = item.get("glossaryItem", {})
            if g.get("name") == gname:
                second_id = g["id"]
                break
        assert second_id, f"Glossary {gname} not found after re-deploy"
        assert (
            first_id == second_id
        ), f"Target glossary ID changed after re-deploy: {first_id} -> {second_id}"

    # ==================================================================
    # I22 — Deploy with skipPublish: true skips all publishing
    # ==================================================================
    @pytest.mark.integration
    def test_skip_publish_flag(self):
        """Deploy with skipPublish: true skips publishing even for ACTIVE assets.

        Validates: I22, P15b, 5.13
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = _h.get_manifest_path("manifest-skip-publish.yaml")
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        asset_name = f"SkipPublishAsset-{ts}"
        asset = _h.create_asset(
            domain_id, project_id, asset_name, region, description="skip-publish test"
        )
        assert asset, "Failed to create asset"

        published = _h.publish_asset(domain_id, asset["id"], region)
        if not published:
            pytest.skip(
                "Could not publish asset (physical resource may not exist). "
                "Skipping skipPublish verification."
            )

        # Bundle — exported JSON should include the ACTIVE asset
        pf, bundle = self._setup_and_bundle(
            "manifest-skip-publish.yaml", "CatalogSkipPublishTest"
        )

        # Verify bundle contains the asset with ACTIVE status
        with zipfile.ZipFile(bundle, "r") as zf:
            assert "catalog/catalog_export.json" in zf.namelist()
            with zf.open("catalog/catalog_export.json") as f:
                catalog_data = json.load(f)
            active = [
                a
                for a in catalog_data.get("assets", [])
                if a.get("name") == asset_name and a.get("listingStatus") == "ACTIVE"
            ]
            assert (
                active
            ), f"Bundle should contain {asset_name} with ACTIVE listingStatus"

        # Deploy with skipPublish: true
        r = self._deploy_to_test(pf, bundle)
        assert r["success"], f"Deploy failed: {r['output']}"

        # Assert Published: 0 in output
        out = r["output"]
        assert "Published: 0" in out or "published: 0" in out.lower(), (
            f"Deploy with skipPublish: true should report Published: 0. "
            f"Output: {out}"
        )

        # Assert asset exists in target but is NOT published
        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")
        items = _h.search_resources(t_domain, t_project, "ASSET", region)
        target_asset = None
        for item in items:
            a = item.get("assetItem", {})
            if a.get("name") == asset_name:
                target_asset = a
                break
        assert target_asset, f"Asset {asset_name} not found in target after deploy"
        assert not target_asset.get("listingId"), (
            f"Asset {asset_name} should NOT be published when skipPublish "
            f"is true, but has listingId: {target_asset.get('listingId')}"
        )

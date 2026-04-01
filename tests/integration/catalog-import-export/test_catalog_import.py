"""Integration tests for catalog import during deploy.

Tests the simplified catalog import design:
- content.catalog.enabled: true exports ALL project-owned resources
- content.catalog.skipPublish: false (default) preserves source publish state; true skips all publishing
- No filter fields in manifest
- Import uses externalIdentifier (with normalization) or name for mapping
- Import supports deletion of resources missing from bundle
- Import returns {created, updated, deleted, failed, published} summary

Subtasks covered:
  8.1 End-to-end catalog import during deploy
  8.2 Idempotent re-deploy (update existing resources)
  8.3 Deletion of resources not in bundle
  8.4 Automatic publishing when enabled
  8.5 No publishing when disabled
  8.6 Publish failures are logged but don't block
  8.7 Deploy skips catalog import when disabled
  8.8 Deploy with bundle missing catalog_export.json
"""

import importlib.util
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

import pytest
import yaml

from tests.integration.base import IntegrationTestBase

# Load shared helpers from hyphenated directory via importlib
_spec = importlib.util.spec_from_file_location(
    "catalog_test_helpers",
    os.path.join(os.path.dirname(__file__), "catalog_test_helpers.py"),
)
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_EXPORT_KEYS = [
    "metadata",
    "glossaries",
    "glossaryTerms",
    "formTypes",
    "assetTypes",
    "assets",
    "dataProducts",
]

RESOURCE_ARRAY_KEYS = [k for k in REQUIRED_EXPORT_KEYS if k != "metadata"]


class TestCatalogImport(IntegrationTestBase):
    """Integration tests for catalog import during deploy."""

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_test_directory()

    def teardown_method(self, method):
        super().teardown_method(method)
        self.cleanup_resources()
        self.cleanup_test_directory()

    # ------------------------------------------------------------------
    # Manifest helpers (thin wrappers over shared helpers)
    # ------------------------------------------------------------------

    def _get_manifest_file(self, variant: str = "default") -> str:
        if variant == "publish":
            return _h.get_manifest_path("manifest-import-publish.yaml")
        return _h.get_manifest_path("manifest-import.yaml")

    # ==================================================================
    # 8.1  End-to-end catalog import during deploy
    # ==================================================================
    @pytest.mark.integration
    def test_end_to_end_import(self):
        """End-to-end: bundle from source, deploy to target, verify import.

        Validates Requirements: 5.1, 5.2, 5.3, 5.6, 6.1, 6.3
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = _h.create_glossary(
            domain_id, project_id, f"ImportGlossary-{ts}", region,
            description="e2e import test",
        )
        assert glossary, "Failed to create glossary"

        term = _h.create_glossary_term(
            domain_id, glossary["id"], f"ImportTerm-{ts}",
            "e2e term", region, project_id=project_id,
        )

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip(prefix="CatalogImportTest")
        assert bundle, "Bundle ZIP not found"

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog, "catalog_export.json missing from bundle"
        for k in REQUIRED_EXPORT_KEYS:
            assert k in catalog, f"Missing key {k}"
        assert catalog["metadata"]["sourceProjectId"] == project_id

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"deploy test failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")
        glossaries = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        names = [i.get("glossaryItem", {}).get("name") for i in glossaries]
        assert f"ImportGlossary-{ts}" in names, f"Glossary not found. Found: {names}"

        if term:
            terms = _h.search_resources(t_domain, t_project, "GLOSSARY_TERM", region)
            tnames = [i.get("glossaryTermItem", {}).get("name") for i in terms]
            assert f"ImportTerm-{ts}" in tnames, f"Term not found. Found: {tnames}"

        out = r["output"].lower()
        assert "catalog" in out
        for kw in ["created", "updated", "deleted", "failed"]:
            assert kw in out, f"Deploy output should report '{kw}' count"

    # ==================================================================
    # 8.2  Idempotent re-deploy
    # ==================================================================
    @pytest.mark.integration
    def test_idempotent_redeploy(self):
        """Deploy same bundle twice — second deploy updates, not duplicates.

        Validates Requirements: 5.2, 5.10
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"IdempotentGlossary-{ts}"
        glossary = _h.create_glossary(
            domain_id, project_id, gname, region, description="idempotent test",
        )
        assert glossary

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = _h.find_bundle_zip(prefix="CatalogImportTest")
        assert bundle

        # first deploy
        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"First deploy failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")
        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        count_first = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert count_first == 1, f"Expected 1 glossary, found {count_first}"

        # second deploy
        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"Second deploy failed: {r['output']}"

        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        count_second = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert count_second == 1, (
            f"Expected 1 glossary after re-deploy, found {count_second} (duplicated)"
        )

    # ==================================================================
    # 8.3  Deletion of resources not in bundle
    # ==================================================================
    @pytest.mark.integration
    def test_deletion_of_resources_not_in_bundle(self):
        """Resources in target but not in bundle are deleted on re-deploy.

        Validates Requirements: 5.4, 5.5, 5.12
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        ga = _h.create_glossary(domain_id, project_id, f"GlossaryA-{ts}", region, description="A")
        gb = _h.create_glossary(domain_id, project_id, f"GlossaryB-{ts}", region, description="B")
        gc = _h.create_glossary(domain_id, project_id, f"GlossaryC-{ts}", region, description="C")
        assert ga and gb and gc, "Failed to create source glossaries"

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = _h.find_bundle_zip(prefix="CatalogImportTest")
        assert bundle

        # first deploy
        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"First deploy failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")

        # create extra resource D directly in target
        gd = _h.create_glossary(
            t_domain, t_project, f"GlossaryD-{ts}", region, description="extra",
        )
        if not gd:
            pytest.skip("Cannot create extra glossary in target")

        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        d_count = sum(
            1 for i in items
            if i.get("glossaryItem", {}).get("name") == f"GlossaryD-{ts}"
        )
        assert d_count == 1

        # re-deploy same bundle — D should be deleted
        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"Re-deploy failed: {r['output']}"

        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        d_count_after = sum(
            1 for i in items
            if i.get("glossaryItem", {}).get("name") == f"GlossaryD-{ts}"
        )
        assert d_count_after == 0, (
            f"GlossaryD should have been deleted, found {d_count_after}"
        )
        assert "deleted" in r["output"].lower()

    # ==================================================================
    # 8.4  Automatic publishing when enabled
    # ==================================================================
    @pytest.mark.integration
    def test_automatic_publishing_when_enabled(self):
        """Deploy with source-state-based publishing.

        Validates Requirements: 5.13, 5.14, 6.3
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file(variant="publish")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = _h.create_glossary(
            domain_id, project_id, f"PublishGlossary-{ts}", region,
            description="publish test",
        )
        assert glossary

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = (
            _h.find_bundle_zip(prefix="CatalogImportPublishTest")
            or _h.find_bundle_zip()
        )
        assert bundle

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"Deploy with publish failed: {r['output']}"

        out = r["output"].lower()
        assert "catalog" in out
        assert "published" in out

    # ==================================================================
    # 8.5  No publishing when disabled
    # ==================================================================
    @pytest.mark.integration
    def test_no_publishing_when_disabled(self):
        """Deploy with publish: false → Published: 0.

        Validates Requirements: 5.13
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        _h.create_glossary(
            domain_id, project_id, f"NoPublishGlossary-{ts}", region,
            description="no-publish test",
        )

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = _h.find_bundle_zip(prefix="CatalogImportTest")
        assert bundle

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"Deploy failed: {r['output']}"

        out = r["output"]
        assert "Published: 0" in out or "published: 0" in out.lower()

    # ==================================================================
    # 8.6  Publish failures don't block
    # ==================================================================
    @pytest.mark.integration
    def test_publish_failures_do_not_block(self):
        """Publish failures are logged but deploy continues.

        Validates Requirements: 5.14
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file(variant="publish")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        _h.create_glossary(
            domain_id, project_id, f"PublishFailGlossary-{ts}", region,
            description="publish-fail test",
        )

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = (
            _h.find_bundle_zip(prefix="CatalogImportPublishTest")
            or _h.find_bundle_zip()
        )
        assert bundle

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], (
            f"Deploy should succeed even when some publishes fail: {r['output']}"
        )
        assert "catalog" in r["output"].lower()

    # ==================================================================
    # 8.7  Deploy skips catalog import when disabled
    # ==================================================================
    @pytest.mark.integration
    def test_deploy_skips_when_catalog_disabled(self):
        """Deploy to stage with catalog.disable: true skips import.

        Validates Requirements: 6.2
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"DisabledGlossary-{ts}"
        _h.create_glossary(domain_id, project_id, gname, region, description="disabled test")

        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = _h.find_bundle_zip(prefix="CatalogImportTest")
        assert bundle

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog, "Bundle should contain catalog_export.json"

        r = self.run_cli_command(
            ["deploy", "--targets", "test-disabled", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"Deploy failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test-disabled")
        items = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        disabled_count = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert disabled_count == 0, (
            f"Expected 0 glossaries when disabled, found {disabled_count}"
        )

        out = r["output"].lower()
        assert "catalog" in out and ("disabled" in out or "skip" in out)

    # ==================================================================
    # 8.8  Deploy with bundle missing catalog_export.json
    # ==================================================================
    @pytest.mark.integration
    def test_deploy_without_catalog_in_bundle(self):
        """Deploy bundle without catalog/ directory succeeds silently.

        Validates Requirements: 6.1
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()

        with open(pf, "r") as fh:
            raw = yaml.safe_load(fh)

        if "content" in raw and "catalog" in raw["content"]:
            del raw["content"]["catalog"]

        tmp_manifest = os.path.join(self.test_dir, "manifest-no-catalog.yaml")
        with open(tmp_manifest, "w") as fh:
            yaml.dump(raw, fh)

        source_code = os.path.join(os.path.dirname(pf), "code")
        dest_code = os.path.join(self.test_dir, "code")
        if os.path.exists(source_code):
            shutil.copytree(source_code, dest_code)

        r = self.run_cli_command(
            ["bundle", "--targets", "dev", "--manifest", tmp_manifest]
        )
        assert r["success"], f"Bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip()
        assert bundle

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog is None, "Bundle should NOT contain catalog_export.json"

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", tmp_manifest]
        )
        assert r["success"], (
            f"Deploy should succeed without catalog_export.json: {r['output']}"
        )

        out = r["output"].lower()
        has_catalog_error = "catalog" in out and "error" in out
        assert not has_catalog_error

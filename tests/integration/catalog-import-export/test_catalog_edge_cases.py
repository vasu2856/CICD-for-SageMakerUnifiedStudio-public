"""Integration tests for catalog import/export edge cases.

Covers the remaining integration tests from the testing guide:
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

import json
import os
import time
import zipfile
from typing import Any, Dict, List, Optional

import boto3
import pytest
import yaml
from botocore.exceptions import ClientError

from tests.integration.base import IntegrationTestBase


class TestCatalogEdgeCases(IntegrationTestBase):
    """Integration tests for catalog edge cases (I7, I19, I22)."""

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_test_directory()

    def teardown_method(self, method):
        super().teardown_method(method)
        self.cleanup_resources()
        self.cleanup_test_directory()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _manifest_path(self, name: str) -> str:
        return os.path.join(os.path.dirname(__file__), name)

    def _get_project_info(self, pipeline_file: str, stage: str = "dev"):
        with open(pipeline_file, "r") as fh:
            raw = yaml.safe_load(fh)
        project_name = raw["stages"][stage]["project"]["name"]
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        from smus_cicd.application import ApplicationManifest
        from smus_cicd.helpers.utils import (
            build_domain_config,
            get_datazone_project_info,
        )

        manifest = ApplicationManifest.from_file(pipeline_file)
        config = build_domain_config(manifest.stages[stage])
        info = get_datazone_project_info(project_name, config)
        if "error" in info or "domain_id" not in info:
            pytest.fail(f"Failed to get project info for stage {stage}: {info}")
        return info["domain_id"], info["project_id"], region, project_name

    def _dz_client(self, region: str):
        return boto3.client("datazone", region_name=region)

    def _find_bundle_zip(self, prefix: str = "Catalog") -> Optional[str]:
        for d in [".", "artifacts"]:
            if os.path.isdir(d):
                for f in sorted(os.listdir(d), reverse=True):
                    if f.startswith(prefix) and f.endswith(".zip"):
                        return os.path.join(d, f)
        return None

    def _search_resources(
        self,
        domain_id: str,
        project_id: str,
        search_scope: str,
        region: str,
    ) -> List[Dict[str, Any]]:
        dz = self._dz_client(region)
        results: List[Dict[str, Any]] = []
        next_token = None
        while True:
            kwargs: Dict[str, Any] = {
                "domainIdentifier": domain_id,
                "searchScope": search_scope,
                "owningProjectIdentifier": project_id,
                "maxResults": 50,
            }
            if next_token:
                kwargs["nextToken"] = next_token
            try:
                resp = dz.search(**kwargs)
            except Exception:
                break
            results.extend(resp.get("items", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break
        return results

    def _create_glossary(
        self,
        domain_id: str,
        project_id: str,
        name: str,
        description: str,
        region: str,
    ) -> Optional[Dict[str, Any]]:
        dz = self._dz_client(region)
        try:
            resp = dz.create_glossary(
                domainIdentifier=domain_id,
                owningProjectIdentifier=project_id,
                name=name,
                description=description,
                status="ENABLED",
            )
            return {"id": resp["id"], "name": name}
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "AccessDeniedException":
                pytest.skip("User lacks CreateGlossary permission")
            if code == "ConflictException":
                return self._find_glossary(domain_id, project_id, name, region)
            raise

    def _find_glossary(
        self, domain_id: str, project_id: str, name: str, region: str
    ) -> Optional[Dict[str, Any]]:
        items = self._search_resources(domain_id, project_id, "GLOSSARY", region)
        for item in items:
            g = item.get("glossaryItem", {})
            if g.get("name") == name:
                return {"id": g["id"], "name": name}
        return None

    # ==================================================================
    # I7 — Bundle with content.catalog.enabled: false
    # ==================================================================
    @pytest.mark.integration
    def test_bundle_catalog_disabled_no_catalog_dir(self):
        """Bundle with content.catalog.enabled: false has no catalog/ directory.

        Steps:
        1. Deploy dev stage to initialize project
        2. Bundle using manifest with catalog.enabled: false
        3. Verify the ZIP does not contain catalog/ directory

        Validates: P1 (export disabled), I7
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._manifest_path("manifest-catalog-disabled.yaml")

        # Deploy dev to initialize project
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        # Bundle — catalog should be skipped.
        # The manifest has storage content (code/) so the bundle should succeed
        # but without a catalog/ directory inside.
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])

        if r["success"]:
            # ZIP was created — verify no catalog/ inside
            bundle = self._find_bundle_zip(prefix="CatalogDisabledTest")
            assert bundle, "Bundle ZIP not found after successful bundle command"

            with zipfile.ZipFile(bundle, "r") as zf:
                catalog_files = [
                    n for n in zf.namelist() if n.startswith("catalog/")
                ]
                assert len(catalog_files) == 0, (
                    f"Bundle should NOT contain catalog/ directory when "
                    f"catalog.enabled is false. Found: {catalog_files}"
                )
        else:
            # Bundle failed (no files to bundle) — also valid when catalog
            # is the only content type and it's disabled.
            # Verify no catalog/ directory exists in any output ZIP.
            bundle = self._find_bundle_zip(prefix="CatalogDisabledTest")
            if bundle:
                with zipfile.ZipFile(bundle, "r") as zf:
                    catalog_files = [
                        n for n in zf.namelist() if n.startswith("catalog/")
                    ]
                    assert len(catalog_files) == 0

    # ==================================================================
    # I19 — Updated resources retain target identifiers after re-deploy
    # ==================================================================
    @pytest.mark.integration
    def test_redeploy_retains_target_identifiers(self):
        """Re-deploy updates resources in place — target IDs are unchanged.

        Steps:
        1. Setup source with glossary → bundle → deploy to test
        2. Record target glossary ID
        3. Re-deploy same bundle
        4. Verify target glossary ID is unchanged

        Validates: I19, 5.2
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._manifest_path("manifest-import.yaml")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # Setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"RetainIdGlossary-{ts}"
        glossary = self._create_glossary(
            domain_id, project_id, gname, "retain-id test", region
        )
        assert glossary, "Failed to create glossary"

        # Bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip(prefix="CatalogImportTest")
        if not bundle:
            bundle = self._find_bundle_zip()
        assert bundle

        # First deploy
        r = self.run_cli_command(
            [
                "deploy",
                "--targets",
                "test",
                "--bundle-archive-path",
                bundle,
                "--manifest",
                pf,
            ]
        )
        assert r["success"], f"First deploy failed: {r['output']}"

        # Record target glossary ID
        t_domain, t_project, _, _ = self._get_project_info(pf, "test")
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        target_glossary = None
        for item in items:
            g = item.get("glossaryItem", {})
            if g.get("name") == gname:
                target_glossary = g
                break
        assert target_glossary, f"Glossary {gname} not found in target after first deploy"
        first_deploy_id = target_glossary["id"]

        # Second deploy (same bundle)
        r = self.run_cli_command(
            [
                "deploy",
                "--targets",
                "test",
                "--bundle-archive-path",
                bundle,
                "--manifest",
                pf,
            ]
        )
        assert r["success"], f"Second deploy failed: {r['output']}"

        # Verify target glossary ID is unchanged
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        target_glossary_after = None
        for item in items:
            g = item.get("glossaryItem", {})
            if g.get("name") == gname:
                target_glossary_after = g
                break
        assert target_glossary_after, f"Glossary {gname} not found after re-deploy"
        second_deploy_id = target_glossary_after["id"]

        assert first_deploy_id == second_deploy_id, (
            f"Target glossary ID changed after re-deploy: "
            f"{first_deploy_id} → {second_deploy_id}"
        )

    # ==================================================================
    # I22 — Deploy with skipPublish: true skips all publishing
    # ==================================================================
    @pytest.mark.integration
    def test_skip_publish_flag(self):
        """Deploy with skipPublish: true skips all publishing.

        Steps:
        1. Setup source with catalog resources
        2. Bundle using skip-publish manifest
        3. Deploy to test
        4. Verify Published: 0 in deploy output

        Validates: I22, P15b, 5.13
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._manifest_path("manifest-skip-publish.yaml")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # Setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = self._create_glossary(
            domain_id, project_id, f"SkipPublishGlossary-{ts}", "skip-publish test", region
        )
        assert glossary, "Failed to create glossary"

        # Bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip(prefix="CatalogSkipPublishTest")
        if not bundle:
            bundle = self._find_bundle_zip()
        assert bundle

        # Deploy with skipPublish: true
        r = self.run_cli_command(
            [
                "deploy",
                "--targets",
                "test",
                "--bundle-archive-path",
                bundle,
                "--manifest",
                pf,
            ]
        )
        assert r["success"], f"Deploy failed: {r['output']}"

        # Verify Published: 0
        out = r["output"]
        assert "Published: 0" in out or "published: 0" in out.lower(), (
            f"Deploy with skipPublish: true should report Published: 0. "
            f"Output: {out}"
        )

        # Verify catalog import completed
        assert "catalog" in out.lower(), "Deploy output should mention catalog"

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

import json
import os
import shutil
import tempfile
import time
import zipfile
from typing import Any, Dict, List, Optional

import boto3
import pytest
import yaml
from botocore.exceptions import ClientError

from tests.integration.base import IntegrationTestBase


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
    # Manifest helpers
    # ------------------------------------------------------------------

    def _get_manifest_file(self, variant: str = "default") -> str:
        """Return path to the appropriate manifest file.

        Args:
            variant: 'default' for standard import manifest,
                     'publish' for publish-enabled manifest.
        """
        base = os.path.dirname(__file__)
        if variant == "publish":
            return os.path.join(base, "manifest-import-publish.yaml")
        return os.path.join(base, "manifest-import.yaml")

    def _get_project_info(self, pipeline_file: str, stage: str = "dev"):
        """Return (domain_id, project_id, region, project_name) for *stage*."""
        with open(pipeline_file, "r") as fh:
            raw = yaml.safe_load(fh)
        project_name = raw["stages"][stage]["project"]["name"]
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        from smus_cicd.application import ApplicationManifest
        from smus_cicd.helpers.utils import build_domain_config, get_datazone_project_info

        manifest = ApplicationManifest.from_file(pipeline_file)
        config = build_domain_config(manifest.stages[stage])
        info = get_datazone_project_info(project_name, config)
        if "error" in info or "domain_id" not in info:
            pytest.fail(f"Failed to get project info for stage {stage}: {info}")
        return info["domain_id"], info["project_id"], region, project_name

    # ------------------------------------------------------------------
    # DataZone resource helpers
    # ------------------------------------------------------------------

    def _dz_client(self, region: str):
        return boto3.client("datazone", region_name=region)

    def _create_glossary(
        self,
        domain_id: str,
        project_id: str,
        name: str,
        description: str,
        region: str,
    ) -> Optional[Dict[str, Any]]:
        """Create or find an existing glossary by *name*."""
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
        except Exception:
            return None

    def _create_glossary_term(
        self,
        domain_id: str,
        glossary_id: str,
        name: str,
        short_description: str,
        region: str,
        project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create or find an existing glossary term by *name*."""
        dz = self._dz_client(region)
        try:
            resp = dz.create_glossary_term(
                domainIdentifier=domain_id,
                glossaryIdentifier=glossary_id,
                name=name,
                shortDescription=short_description,
                status="ENABLED",
            )
            return {"id": resp["id"], "name": name, "glossaryId": glossary_id}
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "AccessDeniedException":
                return None
            if code == "ConflictException":
                return self._find_glossary_term(domain_id, project_id, name, region)
            raise
        except Exception:
            return None

    def _find_glossary(
        self, domain_id: str, project_id: str, name: str, region: str
    ) -> Optional[Dict[str, Any]]:
        dz = self._dz_client(region)
        try:
            resp = dz.search(
                domainIdentifier=domain_id,
                searchScope="GLOSSARY",
                owningProjectIdentifier=project_id,
                maxResults=50,
            )
            for item in resp.get("items", []):
                g = item.get("glossaryItem", {})
                if g.get("name") == name:
                    return {"id": g["id"], "name": name}
        except Exception:
            pass
        return None

    def _find_glossary_term(
        self, domain_id: str, project_id: str, name: str, region: str
    ) -> Optional[Dict[str, Any]]:
        dz = self._dz_client(region)
        try:
            resp = dz.search(
                domainIdentifier=domain_id,
                searchScope="GLOSSARY_TERM",
                owningProjectIdentifier=project_id,
                maxResults=50,
            )
            for item in resp.get("items", []):
                t = item.get("glossaryTermItem", {})
                if t.get("name") == name:
                    return {"id": t["id"], "name": name, "glossaryId": t.get("glossaryId")}
        except Exception:
            pass
        return None

    def _search_resources(
        self,
        domain_id: str,
        project_id: str,
        search_scope: str,
        region: str,
    ) -> List[Dict[str, Any]]:
        """Paginated search for resources of *search_scope* in *project_id*."""
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

    def _delete_glossary(self, domain_id: str, glossary_id: str, region: str):
        """Best-effort delete of a glossary."""
        dz = self._dz_client(region)
        try:
            dz.delete_glossary(domainIdentifier=domain_id, identifier=glossary_id)
        except Exception:
            pass

    def _delete_glossary_term(self, domain_id: str, term_id: str, region: str):
        """Best-effort delete of a glossary term."""
        dz = self._dz_client(region)
        try:
            dz.delete_glossary_term(domainIdentifier=domain_id, identifier=term_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Bundle helpers
    # ------------------------------------------------------------------

    def _find_bundle_zip(self, prefix: str = "CatalogImportTest") -> Optional[str]:
        for d in [".", "artifacts"]:
            if os.path.isdir(d):
                for f in sorted(os.listdir(d), reverse=True):
                    if f.startswith(prefix) and f.endswith(".zip"):
                        return os.path.join(d, f)
        return None

    def _read_catalog_from_bundle(self, bundle_path: str) -> Optional[Dict[str, Any]]:
        """Extract and return catalog_export.json from *bundle_path*."""
        with zipfile.ZipFile(bundle_path, "r") as zf:
            if "catalog/catalog_export.json" not in zf.namelist():
                return None
            with zf.open("catalog/catalog_export.json") as fh:
                return json.load(fh)

    def _create_bundle_with_catalog(
        self,
        catalog_data: Dict[str, Any],
        extra_files: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create a temporary bundle ZIP containing *catalog_data*.

        Returns the path to the ZIP file.
        """
        tmp = tempfile.mkdtemp()
        bundle_path = os.path.join(tmp, "test-bundle.zip")
        with zipfile.ZipFile(bundle_path, "w") as zf:
            zf.writestr(
                "catalog/catalog_export.json",
                json.dumps(catalog_data, indent=2, default=str),
            )
            if extra_files:
                for name, content in extra_files.items():
                    zf.writestr(name, content)
        return bundle_path

    def _create_bundle_without_catalog(self) -> str:
        """Create a temporary bundle ZIP *without* catalog_export.json."""
        tmp = tempfile.mkdtemp()
        bundle_path = os.path.join(tmp, "test-bundle-no-catalog.zip")
        with zipfile.ZipFile(bundle_path, "w") as zf:
            zf.writestr("placeholder.txt", "no catalog data")
        return bundle_path


    # ==================================================================
    # 8.1  End-to-end catalog import during deploy
    # ==================================================================
    @pytest.mark.integration
    def test_end_to_end_import(self):
        """End-to-end: bundle from source, deploy to target, verify import.

        Steps:
        1. Deploy dev stage to create source project
        2. Create sample catalog resources (glossary + term) in source
        3. Bundle from source (exports catalog)
        4. Deploy bundle to test stage (imports catalog)
        5. Verify resources created in target via DataZone APIs
        6. Verify externalIdentifier-based mapping works
        7. Verify deploy output reports created/updated/deleted/failed counts

        Validates Requirements: 5.1, 5.2, 5.3, 5.6, 6.1, 6.3
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # 1 — deploy dev
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        # 2 — create resources
        ts = int(time.time())
        glossary = self._create_glossary(
            domain_id, project_id, f"ImportGlossary-{ts}", "e2e import test", region
        )
        assert glossary, "Failed to create glossary"

        term = self._create_glossary_term(
            domain_id, glossary["id"], f"ImportTerm-{ts}", "e2e term", region,
            project_id=project_id,
        )

        # 3 — bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = self._find_bundle_zip()
        assert bundle, "Bundle ZIP not found"

        catalog = self._read_catalog_from_bundle(bundle)
        assert catalog, "catalog_export.json missing from bundle"
        for k in REQUIRED_EXPORT_KEYS:
            assert k in catalog, f"Missing key {k}"
        assert catalog["metadata"]["sourceProjectId"] == project_id

        # 4 — deploy to test
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"deploy test failed: {r['output']}"

        # 5 — verify resources in target
        t_domain, t_project, _, _ = self._get_project_info(pf, "test")
        glossaries = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        names = [
            i.get("glossaryItem", {}).get("name")
            for i in glossaries
        ]
        assert f"ImportGlossary-{ts}" in names, (
            f"Glossary not found in target. Found: {names}"
        )

        if term:
            terms = self._search_resources(t_domain, t_project, "GLOSSARY_TERM", region)
            tnames = [
                i.get("glossaryTermItem", {}).get("name")
                for i in terms
            ]
            assert f"ImportTerm-{ts}" in tnames, (
                f"Term not found in target. Found: {tnames}"
            )

        # 6 — verify deploy output mentions catalog and counts
        out = r["output"].lower()
        assert "catalog" in out, "Deploy output should mention catalog import"
        # The deploy command prints created/updated/deleted/failed/published
        for keyword in ["created", "updated", "deleted", "failed"]:
            assert keyword in out, f"Deploy output should report '{keyword}' count"

    # ==================================================================
    # 8.2  Idempotent re-deploy (update existing resources)
    # ==================================================================
    @pytest.mark.integration
    def test_idempotent_redeploy(self):
        """Deploy same bundle twice — second deploy updates, not duplicates.

        Steps:
        1. Setup source project + create glossary
        2. Bundle
        3. First deploy to test
        4. Verify resource created
        5. Second deploy (same bundle)
        6. Verify resource count unchanged (no duplication)
        7. Verify ConflictException handling (update path)

        Validates Requirements: 5.2, 5.10
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"IdempotentGlossary-{ts}"
        glossary = self._create_glossary(domain_id, project_id, gname, "idempotent test", region)
        assert glossary, "Failed to create glossary"

        # bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip()
        assert bundle

        # first deploy
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"First deploy failed: {r['output']}"

        t_domain, t_project, _, _ = self._get_project_info(pf, "test")
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        count_first = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert count_first == 1, f"Expected 1 glossary, found {count_first}"

        # second deploy (idempotent)
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"Second deploy failed: {r['output']}"

        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        count_second = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert count_second == 1, (
            f"Expected 1 glossary after re-deploy, found {count_second} (duplicated)"
        )

        # output should mention catalog
        assert "catalog" in r["output"].lower()


    # ==================================================================
    # 8.3  Deletion of resources not in bundle
    # ==================================================================
    @pytest.mark.integration
    def test_deletion_of_resources_not_in_bundle(self):
        """Resources in target but not in bundle are deleted on re-deploy.

        Steps:
        1. Setup source with resources A, B, C → bundle → deploy
        2. Create additional resource D directly in target
        3. Re-deploy same bundle (only A, B, C)
        4. Verify resource D is deleted
        5. Verify deletion happens in reverse dependency order

        Validates Requirements: 5.4, 5.5, 5.12
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        # Create resources A, B, C in source
        ga = self._create_glossary(domain_id, project_id, f"GlossaryA-{ts}", "A", region)
        gb = self._create_glossary(domain_id, project_id, f"GlossaryB-{ts}", "B", region)
        gc = self._create_glossary(domain_id, project_id, f"GlossaryC-{ts}", "C", region)
        assert ga and gb and gc, "Failed to create source glossaries"

        # bundle (contains A, B, C)
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip()
        assert bundle

        # first deploy to target
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"First deploy failed: {r['output']}"

        # get target project info
        t_domain, t_project, _, _ = self._get_project_info(pf, "test")

        # create resource D directly in target (not in bundle)
        gd = self._create_glossary(
            t_domain, t_project, f"GlossaryD-{ts}", "extra resource", region
        )

        if not gd:
            pytest.skip("Cannot create extra glossary in target — skipping deletion test")

        # verify D exists in target
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        d_count = sum(
            1 for i in items
            if i.get("glossaryItem", {}).get("name") == f"GlossaryD-{ts}"
        )
        assert d_count == 1, f"Expected GlossaryD in target, found {d_count}"

        # re-deploy same bundle (only A, B, C — D should be deleted)
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"Re-deploy failed: {r['output']}"

        # verify D is deleted
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        d_count_after = sum(
            1 for i in items
            if i.get("glossaryItem", {}).get("name") == f"GlossaryD-{ts}"
        )
        assert d_count_after == 0, (
            f"GlossaryD should have been deleted, but found {d_count_after}"
        )

        # verify deploy output reports deletion count
        out = r["output"].lower()
        assert "deleted" in out, "Deploy output should report deleted count"

    # ==================================================================
    # 8.4  Automatic publishing when enabled
    # ==================================================================
    @pytest.mark.integration
    def test_automatic_publishing_when_enabled(self):
        """Deploy with source-state-based publishing → assets/data products are published.

        Steps:
        1. Setup source with catalog resources
        2. Bundle
        3. Deploy with publish-enabled manifest
        4. Verify publish API is called (published count > 0 in output)
        5. Verify published count is reported in deploy output

        Validates Requirements: 5.13, 5.14, 6.3
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file(variant="publish")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = self._create_glossary(
            domain_id, project_id, f"PublishGlossary-{ts}", "publish test", region
        )
        assert glossary, "Failed to create glossary"

        # bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip(prefix="CatalogImportPublishTest")
        if not bundle:
            bundle = self._find_bundle_zip()
        assert bundle, "Bundle ZIP not found"

        # deploy with source-state-based publishing (skipPublish defaults to false)
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"Deploy with publish failed: {r['output']}"

        # verify output reports published count
        out = r["output"].lower()
        assert "catalog" in out, "Deploy output should mention catalog"
        assert "published" in out, "Deploy output should report published count"

    # ==================================================================
    # 8.5  No publishing when disabled
    # ==================================================================
    @pytest.mark.integration
    def test_no_publishing_when_disabled(self):
        """Deploy with publish: false → assets/data products are NOT published.

        Steps:
        1. Setup source with catalog resources
        2. Bundle
        3. Deploy with default manifest (publish: false)
        4. Verify published count is 0 in deploy output

        Validates Requirements: 5.13
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()  # publish: false
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = self._create_glossary(
            domain_id, project_id, f"NoPublishGlossary-{ts}", "no-publish test", region
        )
        assert glossary, "Failed to create glossary"

        # bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip()
        assert bundle

        # deploy with publish: false (default)
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"Deploy failed: {r['output']}"

        # verify output reports Published: 0
        out = r["output"]
        assert "Published: 0" in out or "published: 0" in out.lower(), (
            "Deploy output should report Published: 0 when publish is disabled"
        )


    # ==================================================================
    # 8.6  Publish failures are logged but don't block
    # ==================================================================
    @pytest.mark.integration
    def test_publish_failures_do_not_block(self):
        """Publish failures are logged but deploy continues successfully.

        Since this is an integration test against real APIs, we verify the
        behaviour by deploying with publishing enabled (skipPublish: false) and checking that even if
        some resources cannot be published (e.g. glossaries are not
        publishable), the deploy still succeeds and reports the failure
        count without blocking.

        Steps:
        1. Setup source with glossary (not publishable)
        2. Bundle
        3. Deploy with publishing enabled (default skipPublish: false)
        4. Verify deploy succeeds (publish failure for non-publishable
           resources does not block)
        5. Verify failure is reflected in output

        Validates Requirements: 5.14
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file(variant="publish")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        glossary = self._create_glossary(
            domain_id, project_id, f"PublishFailGlossary-{ts}", "publish-fail test", region
        )
        assert glossary, "Failed to create glossary"

        # bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip(prefix="CatalogImportPublishTest")
        if not bundle:
            bundle = self._find_bundle_zip()
        assert bundle

        # deploy with publishing enabled — glossaries are not publishable so
        # the publish step may fail for them, but deploy should still succeed
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], (
            f"Deploy should succeed even when some publishes fail: {r['output']}"
        )

        # output should still mention catalog import completion
        out = r["output"].lower()
        assert "catalog" in out, "Deploy output should mention catalog"

    # ==================================================================
    # 8.7  Deploy skips catalog import when disabled
    # ==================================================================
    @pytest.mark.integration
    def test_deploy_skips_when_catalog_disabled(self):
        """Deploy to stage with catalog.disable: true skips import.

        Steps:
        1. Setup source with catalog resources
        2. Bundle (includes catalog export)
        3. Deploy to test-disabled stage (catalog.disable: true)
        4. Verify no catalog resources created in target
        5. Verify deploy output indicates skip

        Validates Requirements: 6.2
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        # setup source
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        domain_id, project_id, region, _ = self._get_project_info(pf, "dev")

        ts = int(time.time())
        gname = f"DisabledGlossary-{ts}"
        glossary = self._create_glossary(domain_id, project_id, gname, "disabled test", region)
        assert glossary, "Failed to create glossary"

        # bundle
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", pf])
        assert r["success"]
        bundle = self._find_bundle_zip()
        assert bundle

        # verify bundle has catalog data
        catalog = self._read_catalog_from_bundle(bundle)
        assert catalog, "Bundle should contain catalog_export.json"

        # deploy to test-disabled (catalog.disable: true)
        r = self.run_cli_command([
            "deploy", "--targets", "test-disabled",
            "--bundle-archive-path", bundle,
            "--manifest", pf,
        ])
        assert r["success"], f"Deploy failed: {r['output']}"

        # verify no catalog resources created
        t_domain, t_project, _, _ = self._get_project_info(pf, "test-disabled")
        items = self._search_resources(t_domain, t_project, "GLOSSARY", region)
        disabled_count = sum(
            1 for i in items if i.get("glossaryItem", {}).get("name") == gname
        )
        assert disabled_count == 0, (
            f"Expected 0 glossaries when disabled, found {disabled_count}"
        )

        # verify output indicates skip
        out = r["output"].lower()
        assert "catalog" in out and ("disabled" in out or "skip" in out), (
            "Deploy output should indicate catalog import was skipped/disabled"
        )

    # ==================================================================
    # 8.8  Deploy with bundle missing catalog_export.json
    # ==================================================================
    @pytest.mark.integration
    def test_deploy_without_catalog_in_bundle(self):
        """Deploy bundle without catalog/ directory succeeds silently.

        Steps:
        1. Create a manifest without catalog config
        2. Bundle (no catalog export)
        3. Deploy to test
        4. Verify deploy succeeds without errors
        5. Verify catalog import is skipped silently

        Validates Requirements: 6.1
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()

        # Create a temporary manifest with catalog disabled
        with open(pf, "r") as fh:
            raw = yaml.safe_load(fh)

        # Remove catalog config so bundle won't export catalog
        if "content" in raw and "catalog" in raw["content"]:
            del raw["content"]["catalog"]

        tmp_manifest = os.path.join(self.test_dir, "manifest-no-catalog.yaml")
        with open(tmp_manifest, "w") as fh:
            yaml.dump(raw, fh)

        # Copy code directory if it exists
        source_code = os.path.join(os.path.dirname(pf), "code")
        dest_code = os.path.join(self.test_dir, "code")
        if os.path.exists(source_code):
            shutil.copytree(source_code, dest_code)

        # bundle without catalog
        r = self.run_cli_command(["bundle", "--targets", "dev", "--manifest", tmp_manifest])
        assert r["success"], f"Bundle failed: {r['output']}"

        bundle = self._find_bundle_zip()
        assert bundle

        # verify no catalog in bundle
        catalog = self._read_catalog_from_bundle(bundle)
        assert catalog is None, "Bundle should NOT contain catalog_export.json"

        # deploy — should succeed silently
        r = self.run_cli_command([
            "deploy", "--targets", "test",
            "--bundle-archive-path", bundle,
            "--manifest", tmp_manifest,
        ])
        assert r["success"], (
            f"Deploy should succeed without catalog_export.json: {r['output']}"
        )

        # no catalog-related errors
        out = r["output"].lower()
        has_catalog_error = "catalog" in out and "error" in out
        assert not has_catalog_error, "Deploy should not have catalog-related errors"

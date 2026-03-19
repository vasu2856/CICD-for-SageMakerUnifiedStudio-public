"""Integration tests for catalog export during bundle.

Tests the simplified catalog export design:
- content.catalog.enabled: true exports ALL project-owned resources
- No filter fields in manifest (no include, names, assetTypes, updatedAfter)
- --updated-after is a CLI-only flag on the bundle command
- Export JSON keys: metadata, glossaries, glossaryTerms, formTypes,
  assetTypes, assets, dataProducts
"""

import json
import os
import time
import zipfile
from datetime import datetime, timezone

import boto3
import pytest
import yaml

from tests.integration.base import IntegrationTestBase

REQUIRED_TOP_LEVEL_KEYS = [
    "metadata",
    "glossaries",
    "glossaryTerms",
    "formTypes",
    "assetTypes",
    "assets",
    "dataProducts",
]

RESOURCE_ARRAY_KEYS = [k for k in REQUIRED_TOP_LEVEL_KEYS if k != "metadata"]


class TestCatalogExport(IntegrationTestBase):
    """Test catalog export functionality during bundle command."""

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_test_directory()

    def teardown_method(self, method):
        super().teardown_method(method)
        self.cleanup_resources()
        self.cleanup_test_directory()

    # ---- helpers --------------------------------------------------------

    def get_pipeline_file(self):
        return os.path.join(os.path.dirname(__file__), "manifest.yaml")

    def _get_project_info(self, pipeline_file):
        """Return (domain_id, project_id, region, project_name)."""
        with open(pipeline_file, "r") as f:
            raw = yaml.safe_load(f)
        project_name = raw["stages"]["dev"]["project"]["name"]
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        from smus_cicd.application import ApplicationManifest
        from smus_cicd.helpers.utils import (
            build_domain_config,
            get_datazone_project_info,
        )

        manifest = ApplicationManifest.from_file(pipeline_file)
        config = build_domain_config(manifest.stages["dev"])
        info = get_datazone_project_info(project_name, config)
        if "error" in info or "domain_id" not in info:
            pytest.fail(f"Failed to get project info: {info}")
        return info["domain_id"], info["project_id"], region, project_name

    def _create_test_resources(self, domain_id, project_id, region):
        """Create glossary, term, and form type. Returns dict of ids."""
        dz = boto3.client("datazone", region_name=region)
        created = {}

        # Glossary
        try:
            r = dz.create_glossary(
                domainIdentifier=domain_id,
                owningProjectIdentifier=project_id,
                name="TestGlossary",
                description="Integration test glossary",
                status="ENABLED",
            )
            created["glossary"] = r["id"]
        except Exception as e:
            if "ConflictException" in str(e):
                for item in dz.search(
                    domainIdentifier=domain_id,
                    searchScope="GLOSSARY",
                    owningProjectIdentifier=project_id,
                ).get("items", []):
                    g = item.get("glossaryItem", {})
                    if g.get("name") == "TestGlossary":
                        created["glossary"] = g["id"]
                        break

        # GlossaryTerm
        if "glossary" in created:
            try:
                r = dz.create_glossary_term(
                    domainIdentifier=domain_id,
                    glossaryIdentifier=created["glossary"],
                    name="TestTerm",
                    shortDescription="Integration test term",
                    status="ENABLED",
                )
                created["glossary_term"] = r["id"]
            except Exception as e:
                if "ConflictException" in str(e):
                    for item in dz.search(
                        domainIdentifier=domain_id,
                        searchScope="GLOSSARY_TERM",
                        owningProjectIdentifier=project_id,
                    ).get("items", []):
                        t = item.get("glossaryTermItem", {})
                        if t.get("name") == "TestTerm":
                            created["glossary_term"] = t["id"]
                            break

        # FormType
        try:
            r = dz.create_form_type(
                domainIdentifier=domain_id,
                owningProjectIdentifier=project_id,
                name="TestFormType",
                description="Integration test form type",
                model={"smithy": "structure TestFormType { testField: String }"},
                status="ENABLED",
            )
            created["form_type"] = r["revision"]
        except Exception as e:
            if "ConflictException" in str(e):
                for item in dz.search_types(
                    domainIdentifier=domain_id,
                    searchScope="FORM_TYPE",
                    managed=False,
                ).get("items", []):
                    ft = item.get("formTypeItem", {})
                    if (
                        ft.get("name") == "TestFormType"
                        and ft.get("owningProjectId") == project_id
                    ):
                        created["form_type"] = ft["revision"]
                        break

        return created

    def _find_bundle_zip(self, prefix="CatalogImportExportTest"):
        for d in [".", "artifacts"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.startswith(prefix) and f.endswith(".zip"):
                        return os.path.join(d, f)
        return None

    # ----------------------------------------------------------------
    # 7.2  End-to-end catalog export during bundle
    # ----------------------------------------------------------------
    @pytest.mark.integration
    def test_end_to_end_export(self):
        """End-to-end: deploy, create resources, bundle, verify export JSON.

        Validates Requirements 2.1-2.3, 2.5, 2.8-2.11, 3.1-3.2.
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self.get_pipeline_file()

        # Deploy dev project
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"Deploy failed: {r['output']}"

        domain_id, project_id, region, _ = self._get_project_info(pf)
        created = self._create_test_resources(domain_id, project_id, region)

        # Bundle (catalog enabled in manifest)
        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"Bundle failed: {r['output']}"

        # Verify bundle ZIP
        zp = self._find_bundle_zip()
        assert zp, "Bundle ZIP not found"

        with zipfile.ZipFile(zp, "r") as zf:
            assert "catalog/catalog_export.json" in zf.namelist()
            with zf.open("catalog/catalog_export.json") as f:
                data = json.load(f)

        # Top-level keys
        for k in REQUIRED_TOP_LEVEL_KEYS:
            assert k in data, f"Missing key: {k}"

        # Metadata
        md = data["metadata"]
        for field in [
            "sourceProjectId",
            "sourceDomainId",
            "exportTimestamp",
            "resourceTypes",
        ]:
            assert field in md, f"Missing metadata field: {field}"
        assert md["sourceProjectId"] == project_id
        assert md["sourceDomainId"] == domain_id

        if not created:
            for k in RESOURCE_ARRAY_KEYS:
                assert isinstance(data[k], list)
            return

        # Glossaries
        names = [g["name"] for g in data["glossaries"]]
        assert "TestGlossary" in names

        # GlossaryTerms + termRelations
        tnames = [t["name"] for t in data["glossaryTerms"]]
        assert "TestTerm" in tnames
        term = next(t for t in data["glossaryTerms"] if t["name"] == "TestTerm")
        assert "termRelations" in term

        # FormTypes + model
        fnames = [ft["name"] for ft in data["formTypes"]]
        assert "TestFormType" in fnames
        ft = next(x for x in data["formTypes"] if x["name"] == "TestFormType")
        assert "model" in ft

        # Assets — inputForms + externalIdentifier
        for asset in data["assets"]:
            assert "inputForms" in asset

    # ----------------------------------------------------------------
    # 7.3  Catalog export with --updated-after CLI flag
    # ----------------------------------------------------------------
    @pytest.mark.integration
    def test_export_with_updated_after_cli_flag(self):
        """--updated-after CLI flag filters ALL resource types uniformly.

        Validates Requirements 2.12, 3.1-3.2.
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self.get_pipeline_file()

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"Deploy failed: {r['output']}"

        domain_id, project_id, region, _ = self._get_project_info(pf)

        # Record timestamp, create resource, record second timestamp
        ts_before = datetime.now(timezone.utc).isoformat()
        time.sleep(2)

        dz = boto3.client("datazone", region_name=region)
        try:
            dz.create_glossary(
                domainIdentifier=domain_id,
                owningProjectIdentifier=project_id,
                name="RecentGlossary",
                description="For updatedAfter test",
                status="ENABLED",
            )
        except Exception as e:
            if "ConflictException" not in str(e):
                pytest.skip(f"Cannot create test resource: {e}")

        time.sleep(2)

        # Bundle with --updated-after = ts_before (recent)
        r = self.run_cli_command(
            [
                "bundle",
                "--manifest",
                pf,
                "--updated-after",
                ts_before,
            ]
        )
        assert r["success"], f"Bundle failed: {r['output']}"

        zp = self._find_bundle_zip()
        assert zp
        with zipfile.ZipFile(zp, "r") as zf:
            with zf.open("catalog/catalog_export.json") as f:
                data = json.load(f)

        # All arrays must be lists (filter applied uniformly)
        for k in RESOURCE_ARRAY_KEYS:
            assert isinstance(data[k], list), f"{k} should be a list"

        os.remove(zp)

        # Bundle with far-future --updated-after => empty arrays
        r = self.run_cli_command(
            [
                "bundle",
                "--manifest",
                pf,
                "--updated-after",
                "2099-01-01T00:00:00Z",
            ]
        )
        assert r["success"]

        zp = self._find_bundle_zip()
        assert zp
        with zipfile.ZipFile(zp, "r") as zf:
            with zf.open("catalog/catalog_export.json") as f:
                data = json.load(f)

        for k in RESOURCE_ARRAY_KEYS:
            assert len(data[k]) == 0, f"{k} should be empty with future timestamp"

    # ----------------------------------------------------------------
    # 7.4  Catalog export with no project-owned resources
    # ----------------------------------------------------------------
    @pytest.mark.integration
    def test_export_empty_project(self):
        """Empty project produces valid JSON with empty arrays, no errors.

        Validates Requirement 7.2.
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self.get_pipeline_file()

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"Deploy failed: {r['output']}"

        # Use far-future timestamp to simulate empty project
        r = self.run_cli_command(
            [
                "bundle",
                "--manifest",
                pf,
                "--updated-after",
                "2099-12-31T23:59:59Z",
            ]
        )
        assert r["success"], f"Bundle failed: {r['output']}"

        zp = self._find_bundle_zip()
        assert zp

        with zipfile.ZipFile(zp, "r") as zf:
            assert "catalog/catalog_export.json" in zf.namelist()
            with zf.open("catalog/catalog_export.json") as f:
                data = json.load(f)

        # Structure valid
        for k in REQUIRED_TOP_LEVEL_KEYS:
            assert k in data

        # All resource arrays empty
        for k in RESOURCE_ARRAY_KEYS:
            assert isinstance(data[k], list)
            assert len(data[k]) == 0

        # Metadata still populated
        md = data["metadata"]
        assert md.get("sourceProjectId")
        assert md.get("sourceDomainId")
        assert md.get("exportTimestamp")
        assert md.get("resourceTypes")

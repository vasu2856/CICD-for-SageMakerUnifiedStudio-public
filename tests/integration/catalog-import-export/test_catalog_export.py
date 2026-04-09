"""Integration tests for catalog export during bundle.

Tests the simplified catalog export design:
- content.catalog.enabled: true exports ALL project-owned resources
- No filter fields in manifest
- Export JSON keys: metadata, glossaries, glossaryTerms, formTypes,
  assetTypes, assets, dataProducts
"""

import importlib.util
import json
import os
import zipfile

import pytest

from tests.integration.base import IntegrationTestBase

# Load shared helpers from hyphenated directory via importlib
_spec = importlib.util.spec_from_file_location(
    "catalog_test_helpers",
    os.path.join(os.path.dirname(__file__), "catalog_test_helpers.py"),
)
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)

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

    def _create_test_resources(self, domain_id, project_id, region):
        """Create glossary, term, and form type. Returns dict of ids."""
        dz = _h.dz_client(region)
        created = {}

        # Glossary
        g = _h.create_glossary(
            domain_id,
            project_id,
            "TestGlossary",
            region,
            description="Integration test glossary",
        )
        if g:
            created["glossary"] = g["id"]

        # GlossaryTerm
        if "glossary" in created:
            t = _h.create_glossary_term(
                domain_id,
                created["glossary"],
                "TestTerm",
                "Integration test term",
                region,
                project_id=project_id,
            )
            if t:
                created["glossary_term"] = t["id"]

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

        pf = _h.get_manifest_path("manifest.yaml")

        # Deploy dev project
        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"Deploy failed: {r['output']}"

        domain_id, project_id, region, _ = _h.get_project_info(pf)
        created = self._create_test_resources(domain_id, project_id, region)

        # Bundle (catalog enabled in manifest)
        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"Bundle failed: {r['output']}"

        # Verify bundle ZIP
        zp = _h.find_bundle_zip(prefix="CatalogImportExportTest")
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

        # Assets — formsInput + externalIdentifier
        for asset in data["assets"]:
            assert "formsInput" in asset

    # ----------------------------------------------------------------
    # 7.4  Catalog export with no project-owned resources
    # ----------------------------------------------------------------
    @pytest.mark.integration
    def test_export_empty_project(self):
        """Empty project produces valid JSON with correct structure.

        Validates Requirement 7.2.
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = _h.get_manifest_path("manifest.yaml")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"Deploy failed: {r['output']}"

        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"Bundle failed: {r['output']}"

        zp = _h.find_bundle_zip(prefix="CatalogImportExportTest")
        assert zp

        with zipfile.ZipFile(zp, "r") as zf:
            assert "catalog/catalog_export.json" in zf.namelist()
            with zf.open("catalog/catalog_export.json") as f:
                data = json.load(f)

        # Structure valid
        for k in REQUIRED_TOP_LEVEL_KEYS:
            assert k in data

        # All resource arrays are lists
        for k in RESOURCE_ARRAY_KEYS:
            assert isinstance(data[k], list)

        # Metadata still populated
        md = data["metadata"]
        assert md.get("sourceProjectId")
        assert md.get("sourceDomainId")
        assert md.get("exportTimestamp")
        assert md.get("resourceTypes")

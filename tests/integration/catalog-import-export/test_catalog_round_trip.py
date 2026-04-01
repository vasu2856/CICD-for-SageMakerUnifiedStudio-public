"""Integration tests for full round-trip catalog export -> import -> verify.

Tests the complete workflow:
- Export catalog resources from source project via bundle
- Import catalog resources to target project via deploy
- Verify resources exist in target project via DataZone APIs
- Verify externalIdentifier-based mapping, cross-references, publishing

Subtasks covered:
  9.1 Full round-trip: export -> import -> verify resources exist
  9.2 Round-trip with source-state-based publishing (skipPublish: false)
  9.4 Negative scenarios (empty export, malformed JSON, all fail)
"""

import importlib.util
import json
import os
import shutil
import time
from datetime import datetime, timezone
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


class TestCatalogRoundTrip(IntegrationTestBase):
    """Integration tests for full round-trip catalog export/import."""

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
        if variant == "publish":
            return _h.get_manifest_path("manifest-import-publish.yaml")
        return _h.get_manifest_path("manifest-import.yaml")

    def _get_export_manifest_file(self) -> str:
        return _h.get_manifest_path("manifest.yaml")

    # ==================================================================
    # 9.1  Full round-trip: export -> import -> verify
    # ==================================================================
    @pytest.mark.integration
    def test_full_round_trip_export_import_verify(self):
        """Full round-trip: export from source, import to target, verify.

        Validates Requirements: 2.1, 2.2, 4.1, 4.2, 4.3, 4.6, 5.1, 5.6
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        glossary_name = f"RoundTripGlossary-{ts}"
        term_name = f"RoundTripTerm-{ts}"

        glossary = _h.create_glossary(
            domain_id, project_id, glossary_name, region,
            description="round-trip test glossary",
        )
        assert glossary, "Failed to create glossary"

        term = _h.create_glossary_term(
            domain_id, glossary["id"], term_name,
            "round-trip test term", region, project_id=project_id,
        )

        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip()
        assert bundle

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog, "catalog_export.json missing from bundle"

        for k in REQUIRED_EXPORT_KEYS:
            assert k in catalog, f"Missing top-level key: {k}"

        md = catalog["metadata"]
        assert md["sourceProjectId"] == project_id
        assert md["sourceDomainId"] == domain_id

        exported_glossary_names = [g["name"] for g in catalog["glossaries"]]
        assert glossary_name in exported_glossary_names

        if term:
            exported_term_names = [t["name"] for t in catalog["glossaryTerms"]]
            assert term_name in exported_term_names
            exported_term = next(
                t for t in catalog["glossaryTerms"] if t["name"] == term_name
            )
            assert "termRelations" in exported_term
            assert "glossaryId" in exported_term

        for asset in catalog.get("assets", []):
            assert "inputForms" in asset

        # Deploy to target
        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"deploy to target failed: {r['output']}"

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")

        target_glossaries = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        target_glossary_names = [
            i.get("glossaryItem", {}).get("name") for i in target_glossaries
        ]
        assert glossary_name in target_glossary_names

        if term:
            target_terms = _h.search_resources(
                t_domain, t_project, "GLOSSARY_TERM", region
            )
            target_term_names = [
                i.get("glossaryTermItem", {}).get("name") for i in target_terms
            ]
            assert term_name in target_term_names

            # Verify cross-reference remapping
            target_glossary_item = next(
                i.get("glossaryItem", {})
                for i in target_glossaries
                if i.get("glossaryItem", {}).get("name") == glossary_name
            )
            target_glossary_id = target_glossary_item.get("id")
            assert target_glossary_id

            target_term_item = next(
                i.get("glossaryTermItem", {})
                for i in target_terms
                if i.get("glossaryTermItem", {}).get("name") == term_name
            )
            assert target_term_item.get("glossaryId") == target_glossary_id

        out = r["output"].lower()
        assert "catalog" in out
        for kw in ["created", "updated", "deleted", "failed"]:
            assert kw in out

    # ==================================================================
    # 9.2  Round-trip with automatic publishing
    # ==================================================================
    @pytest.mark.integration
    def test_round_trip_with_automatic_publishing(self):
        """Round-trip with source-state-based publishing.

        Validates Requirements: 5.13, 5.14
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file(variant="publish")
        region = os.environ.get("DEV_DOMAIN_REGION", "us-east-1")

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        domain_id, project_id, region, _ = _h.get_project_info(pf, "dev")

        ts = int(time.time())
        glossary_name = f"PublishRoundTrip-{ts}"
        glossary = _h.create_glossary(
            domain_id, project_id, glossary_name, region,
            description="publish round-trip test",
        )
        assert glossary

        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip(prefix="Catalog")
        assert bundle

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog

        num_publishable = len(catalog.get("assets", [])) + len(
            catalog.get("dataProducts", [])
        )

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle,
             "--manifest", pf]
        )
        assert r["success"], f"deploy with publish failed: {r['output']}"

        out = r["output"].lower()
        assert "catalog" in out
        assert "published" in out

        if num_publishable > 0:
            assert "published: 0" not in out

        t_domain, t_project, _, _ = _h.get_project_info(pf, "test")
        target_glossaries = _h.search_resources(t_domain, t_project, "GLOSSARY", region)
        target_names = [
            i.get("glossaryItem", {}).get("name") for i in target_glossaries
        ]
        assert glossary_name in target_names

    # ==================================================================
    # 9.4  Negative scenarios
    # ==================================================================
    @pytest.mark.integration
    def test_export_empty_project_produces_valid_json(self):
        """Export from project -> valid JSON structure, no errors.

        Validates Requirements: 6.4, 7.2
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_export_manifest_file()

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"], f"deploy dev failed: {r['output']}"

        r = self.run_cli_command(["bundle", "--manifest", pf])
        assert r["success"], f"bundle failed: {r['output']}"

        bundle = _h.find_bundle_zip()
        assert bundle

        catalog = _h.read_catalog_from_bundle(bundle)
        assert catalog

        for k in REQUIRED_EXPORT_KEYS:
            assert k in catalog
        for k in RESOURCE_ARRAY_KEYS:
            assert isinstance(catalog[k], list)

        md = catalog["metadata"]
        assert md.get("sourceProjectId")
        assert md.get("sourceDomainId")
        assert md.get("exportTimestamp")
        assert md.get("resourceTypes")

    @pytest.mark.integration
    def test_import_malformed_catalog_json(self):
        """Import with malformed catalog_export.json -> validation error.

        Validates Requirements: 7.3, 7.4
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        malformed_catalog = {
            "metadata": {"sourceProjectId": "test"},
        }
        bundle_path = _h.create_bundle_with_catalog(malformed_catalog)

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle_path,
             "--manifest", pf]
        )

        out = r["output"].lower()
        has_error = (
            "error" in out or "invalid" in out or "missing" in out
            or "validation" in out or not r["success"]
        )
        assert has_error, "Deploy with malformed catalog JSON should report an error"

        if os.path.exists(bundle_path):
            shutil.rmtree(os.path.dirname(bundle_path))

    @pytest.mark.integration
    def test_deploy_all_imports_fail_reports_failure(self):
        """Deploy when all catalog imports fail -> deploy reports failure.

        Validates Requirements: 6.4, 7.1
        """
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        pf = self._get_manifest_file()

        r = self.run_cli_command(["deploy", "--targets", "dev", "--manifest", pf])
        assert r["success"]

        failing_catalog = {
            "metadata": {
                "sourceProjectId": "nonexistent-project",
                "sourceDomainId": "nonexistent-domain",
                "exportTimestamp": datetime.now(timezone.utc).isoformat(),
                "resourceTypes": [
                    "glossaries", "glossaryTerms", "formTypes",
                    "assetTypes", "assets", "dataProducts",
                ],
            },
            "glossaries": [],
            "glossaryTerms": [
                {
                    "sourceId": "fake-term-id",
                    "name": "FailingTerm",
                    "shortDescription": "This should fail",
                    "glossaryId": "nonexistent-glossary-id",
                    "status": "ENABLED",
                    "termRelations": {},
                }
            ],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        bundle_path = _h.create_bundle_with_catalog(failing_catalog)

        r = self.run_cli_command(
            ["deploy", "--targets", "test", "--bundle-archive-path", bundle_path,
             "--manifest", pf]
        )

        out = r["output"].lower()
        has_failure = "failed" in out or "error" in out or not r["success"]
        assert has_failure, "Deploy with all failing imports should report failure"

        if os.path.exists(bundle_path):
            shutil.rmtree(os.path.dirname(bundle_path))

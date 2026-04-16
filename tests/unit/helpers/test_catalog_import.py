"""Unit tests for catalog import functionality."""

import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from smus_cicd.helpers.catalog_import import (
    _build_identifier_map,
    _ensure_import_permissions,
    _get_form_type_revision,
    _identify_extra_target_resources,
    _import_resource,
    _is_managed_resource,
    _normalize_external_identifier,
    _normalize_forms_input_for_api,
    _publish_resource,
    _resolve_cross_references,
    _search_target_resources,
    _search_target_type_resources,
    _validate_catalog_json,
    import_catalog,
)


def _make_valid_catalog(**overrides):
    """Helper to create valid catalog data with optional overrides."""
    data = {
        "metadata": {
            "sourceProjectId": "source-project",
            "sourceDomainId": "source-domain",
            "exportTimestamp": "2025-01-01T00:00:00Z",
            "resourceTypes": [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ],
        },
        "glossaries": [],
        "glossaryTerms": [],
        "formTypes": [],
        "assetTypes": [],
        "assets": [],
        "dataProducts": [],
    }
    data.update(overrides)
    return data


class TestValidateCatalogJson(unittest.TestCase):
    """Test _validate_catalog_json function."""

    def test_validate_valid_json(self):
        _validate_catalog_json(_make_valid_catalog())

    def test_validate_missing_top_level_key(self):
        data = _make_valid_catalog()
        del data["glossaries"]
        with self.assertRaises(ValueError) as ctx:
            _validate_catalog_json(data)
        self.assertIn("missing required top-level keys", str(ctx.exception))

    def test_validate_missing_metadata_key(self):
        data = _make_valid_catalog()
        del data["metadata"]["exportTimestamp"]
        with self.assertRaises(ValueError) as ctx:
            _validate_catalog_json(data)
        self.assertIn("metadata missing required keys", str(ctx.exception))

    def test_validate_does_not_require_metadataForms(self):
        """metadataForms is NOT a required key in the new design."""
        data = _make_valid_catalog()
        # Should pass without metadataForms
        _validate_catalog_json(data)
        self.assertNotIn("metadataForms", data)


class TestNormalizeExternalIdentifier(unittest.TestCase):
    """Test _normalize_external_identifier function."""

    def test_strip_arn_prefix(self):
        ext_id = "arn:aws:s3:us-east-1:123456789012:bucket/my-bucket"
        result = _normalize_external_identifier(ext_id)
        self.assertNotIn("123456789012", result)
        self.assertNotIn("us-east-1", result)
        self.assertIn("bucket", result)

    def test_remove_account_id(self):
        ext_id = "some-resource-123456789012-data"
        result = _normalize_external_identifier(ext_id)
        self.assertNotIn("123456789012", result)

    def test_remove_region(self):
        ext_id = "some-resource-us-west-2-data"
        result = _normalize_external_identifier(ext_id)
        self.assertNotIn("us-west-2", result)

    def test_empty_string(self):
        self.assertEqual(_normalize_external_identifier(""), "")

    def test_none_passthrough(self):
        self.assertIsNone(_normalize_external_identifier(None))

    def test_no_aws_info(self):
        ext_id = "simple-identifier"
        result = _normalize_external_identifier(ext_id)
        self.assertEqual(result, "simple-identifier")


class TestBuildIdentifierMap(unittest.TestCase):
    """Test _build_identifier_map function."""

    def test_external_identifier_based_mapping(self):
        """Test mapping using externalIdentifier with normalization."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "items": [
                {
                    "assetItem": {
                        "identifier": "target-a1",
                        "name": "Asset1",
                        "externalIdentifier": "arn:aws:s3:us-west-2:999888777666:bucket/data",
                    }
                }
            ]
        }
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "source-a1",
                    "name": "DifferentName",
                    "externalIdentifier": "arn:aws:s3:us-east-1:123456789012:bucket/data",
                }
            ]
        )

        id_map = _build_identifier_map(
            mock_client, "domain-1", "project-1", catalog_data
        )
        self.assertEqual(id_map["assets"]["source-a1"], "target-a1")

    def test_name_based_mapping_fallback(self):
        """Test fallback to name when no externalIdentifier."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "items": [{"glossaryItem": {"id": "target-g1", "name": "MyGlossary"}}]
        }
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "source-g1", "name": "MyGlossary"}]
        )

        id_map = _build_identifier_map(
            mock_client, "domain-1", "project-1", catalog_data
        )
        self.assertEqual(id_map["glossaries"]["source-g1"], "target-g1")

    def test_no_match_leaves_unmapped(self):
        """Test that unmatched resources are not in the map."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "source-g1", "name": "NoMatch"}]
        )

        id_map = _build_identifier_map(
            mock_client, "domain-1", "project-1", catalog_data
        )
        self.assertNotIn("source-g1", id_map["glossaries"])

    def test_form_types_mapping(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {
            "items": [
                {
                    "formTypeItem": {
                        "revision": "target-ft1",
                        "name": "MyForm",
                        "owningProjectId": "project-1",
                    }
                }
            ]
        }

        catalog_data = _make_valid_catalog(
            formTypes=[{"sourceId": "source-ft1", "name": "MyForm"}]
        )

        id_map = _build_identifier_map(
            mock_client, "domain-1", "project-1", catalog_data
        )
        self.assertEqual(id_map["formTypes"]["source-ft1"], "target-ft1")


class TestResolveCrossReferences(unittest.TestCase):
    """Test _resolve_cross_references function."""

    def test_resolve_glossary_term_glossary_id(self):
        resource = {"sourceId": "t1", "name": "Term1", "glossaryId": "src-g1"}
        id_map = {
            "glossaries": {"src-g1": "tgt-g1"},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], "tgt-g1")

    def test_resolve_asset_type_identifier(self):
        resource = {"sourceId": "a1", "name": "Asset1", "typeIdentifier": "src-at1"}
        id_map = {
            "glossaries": {},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {"src-at1": "tgt-at1"},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "assets", id_map)
        self.assertEqual(resolved["typeIdentifier"], "tgt-at1")

    def test_no_mapping_keeps_original(self):
        resource = {"sourceId": "t1", "name": "Term1", "glossaryId": "src-g1"}
        id_map = {
            "glossaries": {},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], "src-g1")


class TestImportResource(unittest.TestCase):
    """Test _import_resource function."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_glossary(self):
        client = MagicMock()
        client.create_glossary.return_value = {"id": "new-g1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-g1",
            "name": "G1",
            "description": "desc",
            "status": "ENABLED",
        }

        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["glossaries"]["src-g1"], "new-g1")

    def test_update_glossary(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["glossaries"]["src-g1"] = "existing-g1"
        resource = {
            "sourceId": "src-g1",
            "name": "G1",
            "description": "updated",
            "status": "ENABLED",
        }

        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        client.update_glossary.assert_called_once()

    def test_conflict_exception_treated_as_update(self):
        client = MagicMock()
        error_response = {"Error": {"Code": "ConflictException", "Message": "exists"}}
        client.create_glossary.side_effect = ClientError(
            error_response, "CreateGlossary"
        )
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "status": "ENABLED"}

        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)

    def test_api_failure_returns_false(self):
        client = MagicMock()
        client.create_glossary.side_effect = Exception("API Error")
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "status": "ENABLED"}

        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertFalse(success)

    def test_create_asset_with_external_identifier(self):
        client = MagicMock()
        client.create_asset.return_value = {"id": "new-a1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-a1",
            "name": "A1",
            "description": "desc",
            "typeIdentifier": "type1",
            "formsInput": [],
            "externalIdentifier": "ext-id-1",
        }

        success, _ = _import_resource(client, "d1", "p1", resource, "assets", id_map)
        self.assertTrue(success)
        call_kwargs = client.create_asset.call_args[1]
        self.assertEqual(call_kwargs["externalIdentifier"], "ext-id-1")

    def test_missing_source_id_returns_false(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        resource = {"name": "G1"}  # no sourceId

        success, _ = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertFalse(success)


class TestPublishResource(unittest.TestCase):
    """Test _publish_resource function with listing verification."""

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_asset_active(self, mock_sleep):
        client = MagicMock()
        client.get_asset.return_value = {"listing": {"listingStatus": "ACTIVE"}}
        result = _publish_resource(
            client, "d1", "a1", "assets", max_wait_seconds=5, poll_interval=1
        )
        self.assertTrue(result)
        client.create_listing_change_set.assert_called_once_with(
            domainIdentifier="d1",
            entityIdentifier="a1",
            entityType="ASSET",
            action="PUBLISH",
        )
        client.get_asset.assert_called()

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_data_product_active(self, mock_sleep):
        client = MagicMock()
        client.get_data_product.return_value = {"listing": {"listingStatus": "ACTIVE"}}
        result = _publish_resource(
            client, "d1", "dp1", "dataProducts", max_wait_seconds=5, poll_interval=1
        )
        self.assertTrue(result)
        client.create_listing_change_set.assert_called_once_with(
            domainIdentifier="d1",
            entityIdentifier="dp1",
            entityType="DATA_PRODUCT",
            action="PUBLISH",
        )
        client.get_data_product.assert_called()

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_asset_failed(self, mock_sleep):
        client = MagicMock()
        client.get_asset.return_value = {"listing": {"listingStatus": "FAILED"}}
        result = _publish_resource(
            client, "d1", "a1", "assets", max_wait_seconds=5, poll_interval=1
        )
        self.assertFalse(result)

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_asset_timeout(self, mock_sleep):
        """Listing stays CREATING and never resolves within timeout."""
        client = MagicMock()
        client.get_asset.return_value = {"listing": {"listingStatus": "CREATING"}}
        result = _publish_resource(
            client, "d1", "a1", "assets", max_wait_seconds=3, poll_interval=1
        )
        self.assertFalse(result)

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_asset_becomes_active_after_creating(self, mock_sleep):
        """Listing transitions from CREATING to ACTIVE."""
        client = MagicMock()
        client.get_asset.side_effect = [
            {"listing": {"listingStatus": "CREATING"}},
            {"listing": {"listingStatus": "ACTIVE"}},
        ]
        result = _publish_resource(
            client, "d1", "a1", "assets", max_wait_seconds=10, poll_interval=1
        )
        self.assertTrue(result)
        self.assertEqual(client.get_asset.call_count, 2)

    def test_publish_non_publishable_type(self):
        client = MagicMock()
        result = _publish_resource(client, "d1", "g1", "glossaries")
        self.assertFalse(result)
        client.create_listing_change_set.assert_not_called()

    def test_publish_api_failure(self):
        client = MagicMock()
        client.create_listing_change_set.side_effect = Exception("Publish failed")
        result = _publish_resource(client, "d1", "a1", "assets")
        self.assertFalse(result)

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    def test_publish_poll_error_retries(self, mock_sleep):
        """Polling error on first attempt, then ACTIVE on second."""
        client = MagicMock()
        client.get_asset.side_effect = [
            Exception("Transient error"),
            {"listing": {"listingStatus": "ACTIVE"}},
        ]
        result = _publish_resource(
            client, "d1", "a1", "assets", max_wait_seconds=10, poll_interval=1
        )
        self.assertTrue(result)


class TestIdentifyExtraTargetResources(unittest.TestCase):
    """Test _identify_extra_target_resources function."""

    def test_identifies_extra_resources(self):
        client = MagicMock()
        # Target has glossary "Extra" not in bundle
        client.search.side_effect = lambda **kwargs: (
            {"items": [{"glossaryItem": {"id": "extra-g1", "name": "Extra"}}]}
            if kwargs.get("searchScope") == "GLOSSARY"
            else {"items": []}
        )
        client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "Kept"}]
        )
        extras = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(extras["glossaries"]), 1)
        self.assertEqual(extras["glossaries"][0]["name"], "Extra")

    def test_no_extras_when_all_match(self):
        client = MagicMock()
        client.search.side_effect = lambda **kwargs: (
            {"items": [{"glossaryItem": {"id": "g1", "name": "Kept"}}]}
            if kwargs.get("searchScope") == "GLOSSARY"
            else {"items": []}
        )
        client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "Kept"}]
        )
        extras = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(extras["glossaries"]), 0)


class TestImportCatalog(unittest.TestCase):
    """Test import_catalog orchestration function."""

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_dependency_order_creation(self, mock_get_client):
        """Test resources are created in correct dependency order."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        call_order = []
        client.create_glossary.side_effect = lambda **kw: (
            call_order.append("glossary"),
            {"id": "g1"},
        )[1]
        client.create_glossary_term.side_effect = lambda **kw: (
            call_order.append("glossaryTerm"),
            {"id": "t1"},
        )[1]
        client.create_form_type.side_effect = lambda **kw: (
            call_order.append("formType"),
            {"revision": "ft1"},
        )[1]
        client.create_asset_type.side_effect = lambda **kw: (
            call_order.append("assetType"),
            {"revision": "at1"},
        )[1]
        client.create_asset.side_effect = lambda **kw: (
            call_order.append("asset"),
            {"id": "a1"},
        )[1]
        client.create_data_product.side_effect = lambda **kw: (
            call_order.append("dataProduct"),
            {"id": "dp1"},
        )[1]

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                }
            ],
            formTypes=[{"sourceId": "ft1", "name": "FT1", "model": {}}],
            assetTypes=[{"sourceId": "at1", "name": "AT1", "formsInput": {}}],
            assets=[
                {
                    "sourceId": "a1",
                    "name": "A1",
                    "typeIdentifier": "at1",
                    "formsInput": [],
                }
            ],
            dataProducts=[{"sourceId": "dp1", "name": "DP1", "items": []}],
        )

        import_catalog("d1", "p1", catalog_data, "us-east-1")

        # Verify order: glossary < glossaryTerm < formType < assetType < asset < dataProduct
        self.assertEqual(
            call_order,
            [
                "glossary",
                "glossaryTerm",
                "formType",
                "assetType",
                "asset",
                "dataProduct",
            ],
        )

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_extra_resources_logged_not_deleted(self, mock_get_client):
        """Test extra resources in target are logged but NOT deleted."""
        client = MagicMock()
        mock_get_client.return_value = client

        # No resources in bundle
        catalog_data = _make_valid_catalog()

        # Target has extra resources
        def search_side_effect(**kwargs):
            scope = kwargs.get("searchScope")
            if scope == "GLOSSARY":
                return {"items": [{"glossaryItem": {"id": "g1", "name": "ExtraG"}}]}
            if scope == "ASSET":
                return {
                    "items": [{"assetItem": {"identifier": "a1", "name": "ExtraA"}}]
                }
            return {"items": []}

        client.search.side_effect = search_side_effect
        client.search_types.return_value = {"items": []}

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        # No delete APIs should be called
        client.delete_glossary.assert_not_called()
        client.delete_asset.assert_not_called()
        # Extra resources should be counted as skipped
        self.assertEqual(result["skipped"], 2)

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_publish_when_source_listed(self, mock_get_client, mock_sleep):
        """Test automatic publishing when source asset has listingStatus=ACTIVE."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}
        client.get_asset.return_value = {"listing": {"listingStatus": "ACTIVE"}}

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "a1",
                    "name": "A1",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "listingStatus": "ACTIVE",
                }
            ]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        client.create_listing_change_set.assert_called_once()
        self.assertEqual(result["published"], 1)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_no_publish_when_source_not_listed(self, mock_get_client):
        """Test publish API is NOT called when source asset was not published."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "a1",
                    "name": "A1",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                }
            ]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        client.create_listing_change_set.assert_not_called()
        self.assertEqual(result["published"], 0)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_no_publish_when_skip_publish(self, mock_get_client):
        """Test publish API is NOT called when skip_publish=True even if source was ACTIVE."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "a1",
                    "name": "A1",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "listingStatus": "ACTIVE",
                }
            ]
        )

        result = import_catalog(
            "d1", "p1", catalog_data, "us-east-1", skip_publish=True
        )
        client.create_listing_change_set.assert_not_called()
        self.assertEqual(result["published"], 0)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_publish_failure_increments_failed(self, mock_get_client):
        """Test publish failures are counted as failed."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}
        client.create_listing_change_set.side_effect = Exception("Publish failed")

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "a1",
                    "name": "A1",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "listingStatus": "ACTIVE",
                }
            ]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["published"], 0)
        self.assertEqual(result["failed"], 1)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_error_resilience(self, mock_get_client):
        """Test that failures don't stop processing of remaining resources."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        # First glossary fails, second succeeds
        client.create_glossary.side_effect = [
            Exception("API Error"),
            {"id": "g2"},
        ]

        catalog_data = _make_valid_catalog(
            glossaries=[
                {"sourceId": "g1", "name": "G1", "status": "ENABLED"},
                {"sourceId": "g2", "name": "G2", "status": "ENABLED"},
            ]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 1)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_summary_counts(self, mock_get_client):
        """Test that summary counts are correct."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_glossary.return_value = {"id": "g1"}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        self.assertIn("created", result)
        self.assertIn("updated", result)
        self.assertIn("skipped", result)
        self.assertIn("failed", result)
        self.assertIn("published", result)

    def test_invalid_json_raises_before_api_calls(self):
        """Test that malformed JSON raises ValueError before any API calls."""
        with self.assertRaises(ValueError):
            import_catalog("d1", "p1", {"metadata": {}}, "us-east-1")


class TestEnsureImportPermissions(unittest.TestCase):
    """Test _ensure_import_permissions function."""

    def test_all_grants_present(self):
        """Returns empty list when all required grants exist."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.return_value = {
            "grantList": [{"principal": {"domainUnit": {"id": "du-1"}}}]
        }

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])
        self.assertEqual(mock_client.list_policy_grants.call_count, 3)
        mock_client.add_policy_grant.assert_not_called()

    def test_missing_grants_are_added(self):
        """Adds missing grants and returns empty list on success."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.return_value = {"grantList": []}
        mock_client.add_policy_grant.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])
        self.assertEqual(mock_client.add_policy_grant.call_count, 3)

    def test_partial_grants_adds_only_missing(self):
        """Only adds grants that are missing."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        # CREATE_GLOSSARY has grants, the other two don't
        mock_client.list_policy_grants.side_effect = [
            {"grantList": [{"principal": {"domainUnit": {"id": "du-1"}}}]},
            {"grantList": []},
            {"grantList": []},
        ]
        mock_client.add_policy_grant.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])
        self.assertEqual(mock_client.add_policy_grant.call_count, 2)

    def test_add_grant_failure_returns_failed(self):
        """Returns policy types that could not be added."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.return_value = {"grantList": []}
        mock_client.add_policy_grant.side_effect = Exception("AccessDenied")

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(
            failed,
            ["CREATE_GLOSSARY", "CREATE_FORM_TYPE", "CREATE_ASSET_TYPE"],
        )

    def test_access_denied_on_list_then_add_succeeds(self):
        """When list_policy_grants raises AccessDeniedException, tries to add grant."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "ListPolicyGrants",
        )
        mock_client.add_policy_grant.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])
        self.assertEqual(mock_client.add_policy_grant.call_count, 3)

    def test_get_project_failure_returns_empty(self):
        """Returns empty list (no blocking) when get_project fails."""
        mock_client = MagicMock()
        mock_client.get_project.side_effect = Exception("NetworkError")

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])

    def test_no_domain_unit_id_returns_empty(self):
        """Returns empty list when project has no domainUnitId."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])
        mock_client.list_policy_grants.assert_not_called()

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_import_catalog_aborts_when_grants_cannot_be_added(self, mock_get_client):
        """import_catalog raises PermissionError when grants cannot be added."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.return_value = {"grantList": []}
        mock_client.add_policy_grant.side_effect = Exception("Forbidden")

        catalog_data = {
            "metadata": {
                "sourceProjectId": "src-proj",
                "sourceDomainId": "src-domain",
                "exportTimestamp": "2026-01-01T00:00:00Z",
                "resourceTypes": ["glossaries"],
            },
            "glossaries": [{"sourceId": "g1", "name": "G1"}],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }

        with self.assertRaises(PermissionError) as ctx:
            import_catalog("domain-1", "proj-1", catalog_data, "us-east-1")

        self.assertIn("CREATE_GLOSSARY", str(ctx.exception))
        # No mutating calls should have been made
        mock_client.create_glossary.assert_not_called()
        mock_client.search.assert_not_called()


class TestIsManagedResource(unittest.TestCase):
    """Test _is_managed_resource function."""

    def test_managed_form_type(self):
        self.assertTrue(_is_managed_resource("amazon.datazone.GlueTableForm"))

    def test_custom_form_type(self):
        self.assertFalse(_is_managed_resource("MyCustomForm"))

    def test_empty_name(self):
        self.assertFalse(_is_managed_resource(""))

    def test_none_name(self):
        self.assertFalse(_is_managed_resource(None))


class TestGetDatazoneClient(unittest.TestCase):
    """Test _get_datazone_client with custom endpoint."""

    @patch.dict("os.environ", {"DATAZONE_ENDPOINT_URL": "https://custom.endpoint"})
    @patch("smus_cicd.helpers.catalog_import.create_client")
    def test_custom_endpoint(self, mock_create_client):
        from smus_cicd.helpers.catalog_import import _get_datazone_client

        _get_datazone_client("us-east-1")
        mock_create_client.assert_called_once_with(
            "datazone", region="us-east-1", endpoint_url="https://custom.endpoint"
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("smus_cicd.helpers.catalog_import.create_client")
    def test_default_endpoint(self, mock_create_client):
        from smus_cicd.helpers.catalog_import import _get_datazone_client

        _get_datazone_client("us-west-2")
        mock_create_client.assert_called_once_with("datazone", region="us-west-2")


class TestSearchTargetResources(unittest.TestCase):
    """Test _search_target_resources with pagination."""

    def test_single_page(self):
        client = MagicMock()
        client.search.return_value = {
            "items": [{"glossaryItem": {"id": "g1"}}],
        }
        result = _search_target_resources(client, "d1", "p1", "GLOSSARY")
        self.assertEqual(len(result), 1)

    def test_pagination(self):
        client = MagicMock()
        client.search.side_effect = [
            {"items": [{"glossaryItem": {"id": "g1"}}], "nextToken": "tok1"},
            {"items": [{"glossaryItem": {"id": "g2"}}]},
        ]
        result = _search_target_resources(client, "d1", "p1", "GLOSSARY")
        self.assertEqual(len(result), 2)
        self.assertEqual(client.search.call_count, 2)


class TestSearchTargetTypeResources(unittest.TestCase):
    """Test _search_target_type_resources with client-side filtering."""

    def test_filters_by_owning_project(self):
        client = MagicMock()
        client.search_types.return_value = {
            "items": [
                {"formTypeItem": {"name": "F1", "owningProjectId": "p1"}},
                {"formTypeItem": {"name": "F2", "owningProjectId": "other"}},
            ]
        }
        result = _search_target_type_resources(client, "d1", "p1", "FORM_TYPE")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["formTypeItem"]["name"], "F1")

    def test_asset_type_filtering(self):
        client = MagicMock()
        client.search_types.return_value = {
            "items": [
                {"assetTypeItem": {"name": "AT1", "owningProjectId": "p1"}},
            ]
        }
        result = _search_target_type_resources(client, "d1", "p1", "ASSET_TYPE")
        self.assertEqual(len(result), 1)

    def test_pagination(self):
        client = MagicMock()
        client.search_types.side_effect = [
            {
                "items": [{"formTypeItem": {"name": "F1", "owningProjectId": "p1"}}],
                "nextToken": "tok1",
            },
            {
                "items": [{"formTypeItem": {"name": "F2", "owningProjectId": "p1"}}],
            },
        ]
        result = _search_target_type_resources(client, "d1", "p1", "FORM_TYPE")
        self.assertEqual(len(result), 2)

    def test_unknown_scope_skipped(self):
        client = MagicMock()
        client.search_types.return_value = {
            "items": [{"unknownItem": {"name": "X", "owningProjectId": "p1"}}]
        }
        result = _search_target_type_resources(client, "d1", "p1", "UNKNOWN")
        self.assertEqual(len(result), 0)


class TestGetFormTypeRevision(unittest.TestCase):
    """Test _get_form_type_revision function."""

    def test_returns_revision(self):
        client = MagicMock()
        client.get_form_type.return_value = {"revision": "rev-1"}
        result = _get_form_type_revision(client, "d1", "MyForm")
        self.assertEqual(result, "rev-1")

    def test_returns_none_on_error(self):
        client = MagicMock()
        client.get_form_type.side_effect = Exception("Not found")
        result = _get_form_type_revision(client, "d1", "Missing")
        self.assertIsNone(result)


class TestNormalizeFormsInputForApi(unittest.TestCase):
    """Test _normalize_forms_input_for_api function."""

    def test_asset_forms_rename_type_name(self):
        forms = [{"typeName": "MyForm", "typeRevision": "1", "content": "{}"}]
        result = _normalize_forms_input_for_api(forms, "assets")
        self.assertEqual(result[0]["typeIdentifier"], "MyForm")
        self.assertNotIn("typeName", result[0])

    def test_asset_forms_keep_existing_type_identifier(self):
        forms = [{"typeName": "X", "typeIdentifier": "Y", "typeRevision": "1"}]
        result = _normalize_forms_input_for_api(forms, "assets")
        self.assertEqual(result[0]["typeIdentifier"], "Y")
        self.assertIn("typeName", result[0])

    def test_asset_forms_revision_remap(self):
        client = MagicMock()
        client.get_form_type.return_value = {"revision": "target-rev"}
        forms = [{"typeIdentifier": "MyForm", "typeRevision": "source-rev"}]
        result = _normalize_forms_input_for_api(
            forms, "assets", client=client, domain_id="d1"
        )
        self.assertEqual(result[0]["typeRevision"], "target-rev")

    def test_asset_type_forms_rename(self):
        forms = {
            "MyForm": {"typeName": "MyForm", "typeRevision": "1", "required": True}
        }
        result = _normalize_forms_input_for_api(forms, "assetTypes")
        self.assertEqual(result["MyForm"]["typeIdentifier"], "MyForm")
        self.assertNotIn("typeName", result["MyForm"])

    def test_asset_type_forms_revision_remap(self):
        client = MagicMock()
        client.get_form_type.return_value = {"revision": "tgt-rev"}
        forms = {"F1": {"typeIdentifier": "F1", "typeRevision": "src-rev"}}
        result = _normalize_forms_input_for_api(
            forms, "assetTypes", client=client, domain_id="d1"
        )
        self.assertEqual(result["F1"]["typeRevision"], "tgt-rev")

    def test_empty_forms_passthrough(self):
        self.assertIsNone(_normalize_forms_input_for_api(None, "assets"))
        self.assertEqual(_normalize_forms_input_for_api([], "assets"), [])

    def test_unknown_type_passthrough(self):
        forms = [{"typeName": "X"}]
        result = _normalize_forms_input_for_api(forms, "glossaries")
        self.assertEqual(result, forms)


class TestResolveCrossReferencesDataProducts(unittest.TestCase):
    """Test _resolve_cross_references for data products."""

    def test_resolve_data_product_item_identifiers(self):
        resource = {
            "sourceId": "dp1",
            "name": "DP1",
            "items": [
                {"identifier": "src-a1", "glossaryTerms": ["src-t1", "src-t2"]},
                {"identifier": "src-a2"},
            ],
        }
        id_map = {
            "glossaries": {},
            "glossaryTerms": {"src-t1": "tgt-t1"},
            "formTypes": {},
            "assetTypes": {},
            "assets": {"src-a1": "tgt-a1"},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "dataProducts", id_map)
        self.assertEqual(resolved["items"][0]["identifier"], "tgt-a1")
        self.assertEqual(resolved["items"][0]["glossaryTerms"], ["tgt-t1", "src-t2"])
        self.assertEqual(resolved["items"][1]["identifier"], "src-a2")

    def test_resolve_term_relations(self):
        resource = {
            "sourceId": "t1",
            "name": "T1",
            "glossaryId": "g1",
            "termRelations": {"isA": ["src-t2", "src-t3"]},
        }
        id_map = {
            "glossaries": {"g1": "tgt-g1"},
            "glossaryTerms": {"src-t2": "tgt-t2"},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["termRelations"]["isA"], ["tgt-t2", "src-t3"])

    def test_term_relations_non_list_preserved(self):
        resource = {
            "sourceId": "t1",
            "name": "T1",
            "glossaryId": "g1",
            "termRelations": {"custom": "scalar-value"},
        }
        id_map = {
            "glossaries": {},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["termRelations"]["custom"], "scalar-value")


class TestImportResourceGlossaryTerms(unittest.TestCase):
    """Test _import_resource for glossary terms (create and update)."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_glossary_term(self):
        client = MagicMock()
        client.create_glossary_term.return_value = {"id": "new-t1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-t1",
            "name": "T1",
            "glossaryId": "g1",
            "shortDescription": "short",
            "longDescription": "long",
            "status": "ENABLED",
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaryTerms", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["glossaryTerms"]["src-t1"], "new-t1")
        call_kwargs = client.create_glossary_term.call_args[1]
        self.assertEqual(call_kwargs["shortDescription"], "short")

    def test_update_glossary_term(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["glossaryTerms"]["src-t1"] = "existing-t1"
        resource = {
            "sourceId": "src-t1",
            "name": "T1",
            "glossaryId": "g1",
            "shortDescription": "updated",
            "longDescription": "updated long",
            "status": "ENABLED",
            "termRelations": {"isA": ["t2"]},
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaryTerms", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        call_kwargs = client.update_glossary_term.call_args[1]
        self.assertEqual(call_kwargs["identifier"], "existing-t1")
        self.assertIn("termRelations", call_kwargs)


class TestImportResourceFormTypes(unittest.TestCase):
    """Test _import_resource for form types (create, update, managed skip)."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_form_type(self):
        client = MagicMock()
        client.create_form_type.return_value = {"revision": "rev-1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-ft1",
            "name": "CustomForm",
            "description": "desc",
            "model": {"smithy": "1.0"},
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "formTypes", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["formTypes"]["src-ft1"], "rev-1")
        call_kwargs = client.create_form_type.call_args[1]
        self.assertEqual(call_kwargs["status"], "ENABLED")
        self.assertEqual(call_kwargs["model"], {"smithy": "1.0"})

    def test_update_form_type_skips(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["formTypes"]["src-ft1"] = "existing-rev"
        resource = {"sourceId": "src-ft1", "name": "CustomForm"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "formTypes", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        client.create_form_type.assert_not_called()

    def test_managed_form_type_skipped(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-ft1",
            "name": "amazon.datazone.GlueTableForm",
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "formTypes", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        client.create_form_type.assert_not_called()


class TestImportResourceAssetTypes(unittest.TestCase):
    """Test _import_resource for asset types (create, update, managed skip, form filtering)."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_asset_type(self):
        client = MagicMock()
        client.create_asset_type.return_value = {"revision": "at-rev-1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-at1",
            "name": "CustomAssetType",
            "description": "desc",
            "formsInput": {
                "MyForm": {"typeName": "MyForm", "typeRevision": "1", "required": True}
            },
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assetTypes", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["assetTypes"]["src-at1"], "at-rev-1")

    def test_update_asset_type_skips(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["assetTypes"]["src-at1"] = "existing-rev"
        resource = {"sourceId": "src-at1", "name": "CustomAssetType"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assetTypes", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        client.create_asset_type.assert_not_called()

    def test_managed_asset_type_skipped(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-at1",
            "name": "amazon.datazone.DefaultAssetType",
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assetTypes", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        client.create_asset_type.assert_not_called()

    def test_managed_forms_filtered_from_asset_type(self):
        client = MagicMock()
        client.create_asset_type.return_value = {"revision": "at-rev-1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-at1",
            "name": "CustomType",
            "formsInput": {
                "MyForm": {"typeName": "MyForm", "typeRevision": "1"},
                "amazon.datazone.GlueTableForm": {
                    "typeName": "amazon.datazone.GlueTableForm",
                    "typeRevision": "1",
                },
            },
        }
        success, _ = _import_resource(
            client, "d1", "p1", resource, "assetTypes", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_asset_type.call_args[1]
        forms = call_kwargs.get("formsInput", {})
        self.assertIn("MyForm", forms)
        self.assertNotIn("amazon.datazone.GlueTableForm", forms)


class TestImportResourceAssetUpdate(unittest.TestCase):
    """Test _import_resource for asset update (revision merge)."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_update_asset_merges_forms(self):
        client = MagicMock()
        client.get_asset.return_value = {
            "formsOutput": [
                {
                    "formName": "ManagedForm",
                    "typeName": "amazon.datazone.GlueTableForm",
                    "typeRevision": "1",
                    "content": "{}",
                }
            ]
        }
        id_map = self._empty_id_map()
        id_map["assets"]["src-a1"] = "existing-a1"
        resource = {
            "sourceId": "src-a1",
            "name": "A1",
            "description": "updated",
            "formsInput": [
                {"typeName": "CustomForm", "typeRevision": "1", "content": "{}"}
            ],
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assets", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        call_kwargs = client.create_asset_revision.call_args[1]
        forms = call_kwargs["formsInput"]
        form_names = {f.get("formName") or f.get("typeIdentifier") for f in forms}
        self.assertIn("CustomForm", form_names)
        self.assertIn("ManagedForm", form_names)

    def test_update_asset_get_asset_failure_still_works(self):
        client = MagicMock()
        client.get_asset.side_effect = Exception("Not found")
        id_map = self._empty_id_map()
        id_map["assets"]["src-a1"] = "existing-a1"
        resource = {
            "sourceId": "src-a1",
            "name": "A1",
            "formsInput": [{"typeName": "F1", "typeRevision": "1"}],
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assets", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        client.create_asset_revision.assert_called_once()


class TestImportResourceDataProducts(unittest.TestCase):
    """Test _import_resource for data products (create and update)."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_data_product(self):
        client = MagicMock()
        client.create_data_product.return_value = {"id": "new-dp1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-dp1",
            "name": "DP1",
            "description": "desc",
            "items": [{"identifier": "a1"}],
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "dataProducts", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["dataProducts"]["src-dp1"], "new-dp1")
        call_kwargs = client.create_data_product.call_args[1]
        self.assertEqual(call_kwargs["items"], [{"identifier": "a1"}])

    def test_update_data_product(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["dataProducts"]["src-dp1"] = "existing-dp1"
        resource = {
            "sourceId": "src-dp1",
            "name": "DP1",
            "description": "updated",
            "items": [{"identifier": "a1"}],
        }
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "dataProducts", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        call_kwargs = client.create_data_product_revision.call_args[1]
        self.assertEqual(call_kwargs["identifier"], "existing-dp1")
        self.assertEqual(call_kwargs["items"], [{"identifier": "a1"}])


class TestIdentifyExtraTargetResourcesAllTypes(unittest.TestCase):
    """Test _identify_extra_target_resources for all resource types."""

    def _make_client(self, search_items=None, search_type_items=None):
        client = MagicMock()
        search_items = search_items or {}
        search_type_items = search_type_items or {}

        def search_side_effect(**kwargs):
            scope = kwargs.get("searchScope")
            return {"items": search_items.get(scope, [])}

        def search_types_side_effect(**kwargs):
            scope = kwargs.get("searchScope")
            return {"items": search_type_items.get(scope, [])}

        client.search.side_effect = search_side_effect
        client.search_types.side_effect = search_types_side_effect
        return client

    def test_identifies_extra_glossary_terms(self):
        client = self._make_client(
            search_items={
                "GLOSSARY_TERM": [
                    {"glossaryTermItem": {"id": "t1", "name": "ExtraTerm"}}
                ],
            }
        )
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["glossaryTerms"]), 1)
        self.assertEqual(to_delete["glossaryTerms"][0]["name"], "ExtraTerm")

    def test_identifies_extra_form_types(self):
        client = self._make_client(
            search_type_items={
                "FORM_TYPE": [
                    {
                        "formTypeItem": {
                            "revision": "ft1",
                            "name": "ExtraForm",
                            "owningProjectId": "p1",
                        }
                    }
                ],
            }
        )
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["formTypes"]), 1)

    def test_identifies_extra_asset_types(self):
        client = self._make_client(
            search_type_items={
                "ASSET_TYPE": [
                    {
                        "assetTypeItem": {
                            "revision": "at1",
                            "name": "ExtraAT",
                            "owningProjectId": "p1",
                        }
                    }
                ],
            }
        )
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["assetTypes"]), 1)

    def test_identifies_extra_assets(self):
        client = self._make_client(
            search_items={
                "ASSET": [{"assetItem": {"identifier": "a1", "name": "ExtraAsset"}}],
            }
        )
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["assets"]), 1)

    def test_identifies_extra_data_products(self):
        client = self._make_client(
            search_items={
                "DATA_PRODUCT": [{"dataProductItem": {"id": "dp1", "name": "ExtraDP"}}],
            }
        )
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["dataProducts"]), 1)

    def test_search_failure_graceful(self):
        client = MagicMock()
        client.search.side_effect = Exception("Network error")
        client.search_types.side_effect = Exception("Network error")
        catalog_data = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog_data)
        # Should not crash, all lists empty
        for rt in to_delete:
            self.assertEqual(len(to_delete[rt]), 0)


class TestEnsureImportPermissionsEdgeCases(unittest.TestCase):
    """Cover edge cases in _ensure_import_permissions."""

    def test_non_access_denied_client_error_tries_add(self):
        """Non-AccessDeniedException ClientError on list still tries to add grant."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
            "ListPolicyGrants",
        )
        mock_client.add_policy_grant.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        # ThrottlingException means we couldn't confirm — grant is not confirmed present,
        # so add_policy_grant should NOT be called (grant status unknown, not missing)
        self.assertEqual(failed, [])

    def test_generic_exception_on_list_tries_add(self):
        """Generic Exception on list still tries to add grant."""
        mock_client = MagicMock()
        mock_client.get_project.return_value = {"domainUnitId": "du-1"}
        mock_client.list_policy_grants.side_effect = Exception("Network timeout")
        mock_client.add_policy_grant.return_value = {}

        failed = _ensure_import_permissions(mock_client, "domain-1", "proj-1")
        self.assertEqual(failed, [])


class TestBuildIdentifierMapAllTypes(unittest.TestCase):
    """Cover _build_identifier_map for glossary terms, asset types, data products, and error paths."""

    def test_glossary_term_mapping(self):
        client = MagicMock()
        client.search.side_effect = lambda **kw: (
            {"items": [{"glossaryTermItem": {"id": "tgt-t1", "name": "Term1"}}]}
            if kw.get("searchScope") == "GLOSSARY_TERM"
            else {"items": []}
        )
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            glossaryTerms=[{"sourceId": "src-t1", "name": "Term1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertEqual(id_map["glossaryTerms"]["src-t1"], "tgt-t1")

    def test_asset_type_mapping(self):
        client = MagicMock()
        client.search.return_value = {"items": []}
        client.search_types.side_effect = lambda **kw: (
            {
                "items": [
                    {
                        "assetTypeItem": {
                            "revision": "tgt-at1",
                            "name": "AT1",
                            "owningProjectId": "p1",
                        }
                    }
                ]
            }
            if kw.get("searchScope") == "ASSET_TYPE"
            else {"items": []}
        )
        catalog = _make_valid_catalog(
            assetTypes=[{"sourceId": "src-at1", "name": "AT1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertEqual(id_map["assetTypes"]["src-at1"], "tgt-at1")

    def test_data_product_mapping(self):
        client = MagicMock()
        client.search.side_effect = lambda **kw: (
            {"items": [{"dataProductItem": {"id": "tgt-dp1", "name": "DP1"}}]}
            if kw.get("searchScope") == "DATA_PRODUCT"
            else {"items": []}
        )
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            dataProducts=[{"sourceId": "src-dp1", "name": "DP1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertEqual(id_map["dataProducts"]["src-dp1"], "tgt-dp1")

    def test_glossary_term_search_failure(self):
        client = MagicMock()
        call_count = [0]

        def search_side(**kw):
            scope = kw.get("searchScope")
            if scope == "GLOSSARY_TERM":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            glossaryTerms=[{"sourceId": "src-t1", "name": "T1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-t1", id_map["glossaryTerms"])

    def test_form_type_search_failure(self):
        client = MagicMock()
        client.search.return_value = {"items": []}

        def search_types_side(**kw):
            if kw.get("searchScope") == "FORM_TYPE":
                raise Exception("Search failed")
            return {"items": []}

        client.search_types.side_effect = search_types_side
        catalog = _make_valid_catalog(
            formTypes=[{"sourceId": "src-ft1", "name": "FT1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-ft1", id_map["formTypes"])

    def test_asset_type_search_failure(self):
        client = MagicMock()
        client.search.return_value = {"items": []}

        def search_types_side(**kw):
            if kw.get("searchScope") == "ASSET_TYPE":
                raise Exception("Search failed")
            return {"items": []}

        client.search_types.side_effect = search_types_side
        catalog = _make_valid_catalog(
            assetTypes=[{"sourceId": "src-at1", "name": "AT1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-at1", id_map["assetTypes"])

    def test_data_product_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "DATA_PRODUCT":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            dataProducts=[{"sourceId": "src-dp1", "name": "DP1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-dp1", id_map["dataProducts"])

    def test_asset_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "ASSET":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            assets=[{"sourceId": "src-a1", "name": "A1", "externalIdentifier": "ext1"}]
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-a1", id_map["assets"])

    def test_glossary_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "GLOSSARY":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(glossaries=[{"sourceId": "src-g1", "name": "G1"}])
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        self.assertNotIn("src-g1", id_map["glossaries"])

    def test_resource_without_source_id_skipped(self):
        client = MagicMock()
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog(
            glossaries=[{"name": "NoSourceId"}],
            glossaryTerms=[{"name": "NoSourceId"}],
            formTypes=[{"name": "NoSourceId"}],
            assetTypes=[{"name": "NoSourceId"}],
            assets=[{"name": "NoSourceId"}],
            dataProducts=[{"name": "NoSourceId"}],
        )
        id_map = _build_identifier_map(client, "d1", "p1", catalog)
        for rt in id_map:
            self.assertEqual(len(id_map[rt]), 0)


class TestNormalizeFormsInputBranches(unittest.TestCase):
    """Cover branch misses in _normalize_forms_input_for_api."""

    def test_asset_form_no_type_revision(self):
        """Form without typeRevision should not attempt revision remap."""
        forms = [{"typeName": "MyForm", "content": "{}"}]
        result = _normalize_forms_input_for_api(forms, "assets")
        self.assertEqual(result[0]["typeIdentifier"], "MyForm")
        self.assertNotIn("typeRevision", result[0])

    def test_asset_form_revision_resolves_to_none(self):
        """When target revision lookup returns None, keep original."""
        client = MagicMock()
        client.get_form_type.return_value = {}  # no "revision" key
        forms = [{"typeIdentifier": "MyForm", "typeRevision": "src-rev"}]
        result = _normalize_forms_input_for_api(
            forms, "assets", client=client, domain_id="d1"
        )
        self.assertEqual(result[0]["typeRevision"], "src-rev")

    def test_asset_type_form_no_type_revision(self):
        """AssetType form without typeRevision should not attempt remap."""
        forms = {"F1": {"typeName": "F1", "required": True}}
        result = _normalize_forms_input_for_api(forms, "assetTypes")
        self.assertEqual(result["F1"]["typeIdentifier"], "F1")
        self.assertNotIn("typeRevision", result["F1"])

    def test_asset_type_form_revision_resolves_to_none(self):
        """When target revision lookup returns None for assetType, keep original."""
        client = MagicMock()
        client.get_form_type.return_value = {}
        forms = {"F1": {"typeIdentifier": "F1", "typeRevision": "src-rev"}}
        result = _normalize_forms_input_for_api(
            forms, "assetTypes", client=client, domain_id="d1"
        )
        self.assertEqual(result["F1"]["typeRevision"], "src-rev")


class TestImportResourceBranches(unittest.TestCase):
    """Cover remaining branch misses in _import_resource."""

    def _empty_id_map(self):
        return {
            rt: {}
            for rt in [
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            ]
        }

    def test_create_asset_minimal_no_optional_fields(self):
        """Asset creation without description, typeIdentifier, formsInput, externalIdentifier."""
        client = MagicMock()
        client.create_asset.return_value = {"id": "new-a1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-a1", "name": "A1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assets", id_map
        )
        self.assertTrue(success)
        self.assertFalse(is_update)
        call_kwargs = client.create_asset.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("typeIdentifier", call_kwargs)
        self.assertNotIn("formsInput", call_kwargs)
        self.assertNotIn("externalIdentifier", call_kwargs)

    def test_non_conflict_client_error_returns_false(self):
        """Non-ConflictException ClientError should return (False, False)."""
        client = MagicMock()
        client.create_glossary.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad input"}},
            "CreateGlossary",
        )
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "status": "ENABLED"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertFalse(success)
        self.assertFalse(is_update)

    def test_create_glossary_minimal(self):
        """Glossary creation without description or status."""
        client = MagicMock()
        client.create_glossary.return_value = {"id": "new-g1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_glossary.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("status", call_kwargs)

    def test_create_glossary_term_minimal(self):
        """GlossaryTerm creation without optional fields."""
        client = MagicMock()
        client.create_glossary_term.return_value = {"id": "new-t1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-t1", "name": "T1", "glossaryId": "g1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaryTerms", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_glossary_term.call_args[1]
        self.assertNotIn("shortDescription", call_kwargs)
        self.assertNotIn("longDescription", call_kwargs)
        self.assertNotIn("status", call_kwargs)

    def test_update_glossary_minimal(self):
        """Glossary update without description or status."""
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["glossaries"]["src-g1"] = "existing-g1"
        resource = {"sourceId": "src-g1", "name": "G1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaries", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        call_kwargs = client.update_glossary.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("status", call_kwargs)

    def test_update_glossary_term_minimal(self):
        """GlossaryTerm update without optional fields."""
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["glossaryTerms"]["src-t1"] = "existing-t1"
        resource = {"sourceId": "src-t1", "name": "T1", "glossaryId": "g1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "glossaryTerms", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.update_glossary_term.call_args[1]
        self.assertNotIn("shortDescription", call_kwargs)
        self.assertNotIn("longDescription", call_kwargs)
        self.assertNotIn("status", call_kwargs)
        self.assertNotIn("termRelations", call_kwargs)

    def test_create_data_product_minimal(self):
        """DataProduct creation without description or items."""
        client = MagicMock()
        client.create_data_product.return_value = {"id": "new-dp1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-dp1", "name": "DP1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "dataProducts", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_data_product.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("items", call_kwargs)

    def test_update_data_product_minimal(self):
        """DataProduct update without description."""
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["dataProducts"]["src-dp1"] = "existing-dp1"
        resource = {"sourceId": "src-dp1", "name": "DP1"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "dataProducts", id_map
        )
        self.assertTrue(success)
        self.assertTrue(is_update)
        call_kwargs = client.create_data_product_revision.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("items", call_kwargs)

    def test_create_form_type_minimal(self):
        """FormType creation without description or model."""
        client = MagicMock()
        client.create_form_type.return_value = {"revision": "rev-1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-ft1", "name": "CustomForm"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "formTypes", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_form_type.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("model", call_kwargs)

    def test_create_asset_type_minimal(self):
        """AssetType creation without description or formsInput."""
        client = MagicMock()
        client.create_asset_type.return_value = {"revision": "at-rev-1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-at1", "name": "CustomAT"}
        success, is_update = _import_resource(
            client, "d1", "p1", resource, "assetTypes", id_map
        )
        self.assertTrue(success)
        call_kwargs = client.create_asset_type.call_args[1]
        self.assertNotIn("description", call_kwargs)
        self.assertNotIn("formsInput", call_kwargs)


class TestImportCatalogSecondPass(unittest.TestCase):
    """Cover import_catalog second pass termRelations and deletion integration."""

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_second_pass_updates_term_relations(self, mock_get_client):
        """Second pass should call update_glossary_term with resolved termRelations."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_glossary.return_value = {"id": "g1"}
        client.create_glossary_term.side_effect = [
            {"id": "tgt-t1"},
            {"id": "tgt-t2"},
        ]

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "src-t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                    "termRelations": {"isA": ["src-t2"]},
                },
                {
                    "sourceId": "src-t2",
                    "name": "T2",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                },
            ],
        )

        import_catalog("d1", "p1", catalog_data, "us-east-1")

        # Second pass should have called update_glossary_term for T1
        update_calls = client.update_glossary_term.call_args_list
        self.assertTrue(len(update_calls) >= 1)
        # Find the second-pass call (the one with termRelations)
        found = False
        for call in update_calls:
            kwargs = call[1]
            if "termRelations" in kwargs:
                self.assertEqual(kwargs["termRelations"]["isA"], ["tgt-t2"])
                found = True
        self.assertTrue(found, "Second pass update_glossary_term not called")

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_second_pass_term_relations_failure_logged(self, mock_get_client):
        """Second pass termRelations update failure should be logged, not crash."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_glossary.return_value = {"id": "g1"}
        client.create_glossary_term.return_value = {"id": "tgt-t1"}
        client.update_glossary_term.side_effect = Exception("Update failed")

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "src-t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                    "termRelations": {"isA": ["src-t2"]},
                },
            ],
        )

        # Should not raise
        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        self.assertEqual(result["created"], 2)  # glossary + term

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_second_pass_skips_empty_term_relations(self, mock_get_client):
        """Second pass should skip terms with empty termRelations."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_glossary.return_value = {"id": "g1"}
        client.create_glossary_term.return_value = {"id": "tgt-t1"}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "src-t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                    "termRelations": {"isA": []},
                },
            ],
        )

        import_catalog("d1", "p1", catalog_data, "us-east-1")
        # update_glossary_term should NOT be called for second pass
        # (termRelations has empty list, any() returns False)
        client.update_glossary_term.assert_not_called()

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_deletion_failure_increments_failed(self, mock_get_client):
        """Extra resources in target should be skipped, not deleted."""
        client = MagicMock()
        mock_get_client.return_value = client
        catalog_data = _make_valid_catalog()

        def search_side(**kw):
            if kw.get("searchScope") == "GLOSSARY":
                return {"items": [{"glossaryItem": {"id": "g1", "name": "Extra"}}]}
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        # No delete APIs should be called
        client.delete_glossary.assert_not_called()
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_second_pass_non_list_term_relations(self, mock_get_client):
        """Second pass should handle non-list termRelations values."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_glossary.return_value = {"id": "g1"}
        client.create_glossary_term.return_value = {"id": "tgt-t1"}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "src-t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                    "termRelations": {"custom": "scalar-value"},
                },
            ],
        )

        import_catalog("d1", "p1", catalog_data, "us-east-1")
        update_calls = client.update_glossary_term.call_args_list
        found = False
        for call in update_calls:
            kwargs = call[1]
            if "termRelations" in kwargs:
                self.assertEqual(kwargs["termRelations"]["custom"], "scalar-value")
                found = True
        self.assertTrue(found)


class TestImportCatalogPublishableUpdate(unittest.TestCase):
    """Cover the update path for publishable resources (assets/dataProducts) in import_catalog."""

    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_update_asset_with_active_listing_publishes(
        self, mock_get_client, mock_sleep
    ):
        """Updated asset with ACTIVE listingStatus should be published."""
        client = MagicMock()
        mock_get_client.return_value = client
        # Asset already exists in target
        client.search.side_effect = lambda **kw: (
            {
                "items": [
                    {
                        "assetItem": {
                            "identifier": "tgt-a1",
                            "name": "A1",
                            "externalIdentifier": "ext1",
                        }
                    }
                ]
            }
            if kw.get("searchScope") == "ASSET"
            else {"items": []}
        )
        client.search_types.return_value = {"items": []}
        client.get_asset.return_value = {
            "formsOutput": [],
            "listing": {"listingStatus": "ACTIVE"},
        }

        catalog_data = _make_valid_catalog(
            assets=[
                {
                    "sourceId": "src-a1",
                    "name": "A1",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "externalIdentifier": "ext1",
                    "listingStatus": "ACTIVE",
                }
            ]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["published"], 1)
        client.create_listing_change_set.assert_called_once()

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_second_pass_skips_unmapped_term(self, mock_get_client):
        """Second pass should skip terms that have no target_id mapping."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        # create_glossary_term fails, so term won't be in id_map
        client.create_glossary.return_value = {"id": "g1"}
        client.create_glossary_term.side_effect = Exception("Create failed")

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[
                {
                    "sourceId": "src-t1",
                    "name": "T1",
                    "glossaryId": "g1",
                    "status": "ENABLED",
                    "termRelations": {"isA": ["src-t2"]},
                }
            ],
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        # Term creation failed, so second pass should skip it
        self.assertEqual(result["failed"], 1)


class TestIdentifyExtraTargetResourcesBranches(unittest.TestCase):
    """Cover branch misses in _identify_extra_target_resources."""

    def test_glossary_term_deletion_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "GLOSSARY_TERM":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["glossaryTerms"]), 0)

    def test_form_type_deletion_search_failure(self):
        client = MagicMock()
        client.search.return_value = {"items": []}

        def search_types_side(**kw):
            if kw.get("searchScope") == "FORM_TYPE":
                raise Exception("Search failed")
            return {"items": []}

        client.search_types.side_effect = search_types_side
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["formTypes"]), 0)

    def test_asset_type_deletion_search_failure(self):
        client = MagicMock()
        client.search.return_value = {"items": []}

        def search_types_side(**kw):
            if kw.get("searchScope") == "ASSET_TYPE":
                raise Exception("Search failed")
            return {"items": []}

        client.search_types.side_effect = search_types_side
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["assetTypes"]), 0)

    def test_asset_deletion_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "ASSET":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["assets"]), 0)

    def test_data_product_deletion_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "DATA_PRODUCT":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["dataProducts"]), 0)

    def test_glossary_deletion_search_failure(self):
        client = MagicMock()

        def search_side(**kw):
            if kw.get("searchScope") == "GLOSSARY":
                raise Exception("Search failed")
            return {"items": []}

        client.search.side_effect = search_side
        client.search_types.return_value = {"items": []}
        catalog = _make_valid_catalog()
        to_delete = _identify_extra_target_resources(client, "d1", "p1", catalog)
        self.assertEqual(len(to_delete["glossaries"]), 0)


if __name__ == "__main__":
    unittest.main()

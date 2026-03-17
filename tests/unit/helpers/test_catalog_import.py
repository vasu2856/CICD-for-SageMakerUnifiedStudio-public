"""Unit tests for catalog import functionality."""

import unittest
from unittest.mock import MagicMock, patch, call

from botocore.exceptions import ClientError

from smus_cicd.helpers.catalog_import import (
    _build_identifier_map,
    _delete_resource,
    _identify_resources_to_delete,
    _import_resource,
    _normalize_external_identifier,
    _publish_resource,
    _resolve_cross_references,
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
            "resourceTypes": ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"],
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
            "items": [{
                "assetItem": {
                    "identifier": "target-a1",
                    "name": "Asset1",
                    "externalIdentifier": "arn:aws:s3:us-west-2:999888777666:bucket/data",
                }
            }]
        }
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            assets=[{
                "sourceId": "source-a1",
                "name": "DifferentName",
                "externalIdentifier": "arn:aws:s3:us-east-1:123456789012:bucket/data",
            }]
        )

        id_map = _build_identifier_map(mock_client, "domain-1", "project-1", catalog_data)
        self.assertEqual(id_map["assets"]["source-a1"], "target-a1")

    def test_name_based_mapping_fallback(self):
        """Test fallback to name when no externalIdentifier."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "items": [{
                "glossaryItem": {"id": "target-g1", "name": "MyGlossary"}
            }]
        }
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "source-g1", "name": "MyGlossary"}]
        )

        id_map = _build_identifier_map(mock_client, "domain-1", "project-1", catalog_data)
        self.assertEqual(id_map["glossaries"]["source-g1"], "target-g1")

    def test_no_match_leaves_unmapped(self):
        """Test that unmatched resources are not in the map."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "source-g1", "name": "NoMatch"}]
        )

        id_map = _build_identifier_map(mock_client, "domain-1", "project-1", catalog_data)
        self.assertNotIn("source-g1", id_map["glossaries"])

    def test_form_types_mapping(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {
            "items": [{
                "formTypeItem": {
                    "revision": "target-ft1",
                    "name": "MyForm",
                    "owningProjectId": "project-1",
                }
            }]
        }

        catalog_data = _make_valid_catalog(
            formTypes=[{"sourceId": "source-ft1", "name": "MyForm"}]
        )

        id_map = _build_identifier_map(mock_client, "domain-1", "project-1", catalog_data)
        self.assertEqual(id_map["formTypes"]["source-ft1"], "target-ft1")


class TestResolveCrossReferences(unittest.TestCase):
    """Test _resolve_cross_references function."""

    def test_resolve_glossary_term_glossary_id(self):
        resource = {"sourceId": "t1", "name": "Term1", "glossaryId": "src-g1"}
        id_map = {"glossaries": {"src-g1": "tgt-g1"}, "glossaryTerms": {}, "formTypes": {}, "assetTypes": {}, "assets": {}, "dataProducts": {}}
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], "tgt-g1")

    def test_resolve_asset_type_identifier(self):
        resource = {"sourceId": "a1", "name": "Asset1", "typeIdentifier": "src-at1"}
        id_map = {"glossaries": {}, "glossaryTerms": {}, "formTypes": {}, "assetTypes": {"src-at1": "tgt-at1"}, "assets": {}, "dataProducts": {}}
        resolved = _resolve_cross_references(resource, "assets", id_map)
        self.assertEqual(resolved["typeIdentifier"], "tgt-at1")

    def test_no_mapping_keeps_original(self):
        resource = {"sourceId": "t1", "name": "Term1", "glossaryId": "src-g1"}
        id_map = {"glossaries": {}, "glossaryTerms": {}, "formTypes": {}, "assetTypes": {}, "assets": {}, "dataProducts": {}}
        resolved = _resolve_cross_references(resource, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], "src-g1")


class TestImportResource(unittest.TestCase):
    """Test _import_resource function."""

    def _empty_id_map(self):
        return {rt: {} for rt in ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"]}

    def test_create_glossary(self):
        client = MagicMock()
        client.create_glossary.return_value = {"id": "new-g1"}
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "description": "desc", "status": "ENABLED"}

        success, is_update = _import_resource(client, "d1", "p1", resource, "glossaries", id_map)
        self.assertTrue(success)
        self.assertFalse(is_update)
        self.assertEqual(id_map["glossaries"]["src-g1"], "new-g1")

    def test_update_glossary(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        id_map["glossaries"]["src-g1"] = "existing-g1"
        resource = {"sourceId": "src-g1", "name": "G1", "description": "updated", "status": "ENABLED"}

        success, is_update = _import_resource(client, "d1", "p1", resource, "glossaries", id_map)
        self.assertTrue(success)
        self.assertTrue(is_update)
        client.update_glossary.assert_called_once()

    def test_conflict_exception_treated_as_update(self):
        client = MagicMock()
        error_response = {"Error": {"Code": "ConflictException", "Message": "exists"}}
        client.create_glossary.side_effect = ClientError(error_response, "CreateGlossary")
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "status": "ENABLED"}

        success, is_update = _import_resource(client, "d1", "p1", resource, "glossaries", id_map)
        self.assertTrue(success)
        self.assertTrue(is_update)

    def test_api_failure_returns_false(self):
        client = MagicMock()
        client.create_glossary.side_effect = Exception("API Error")
        id_map = self._empty_id_map()
        resource = {"sourceId": "src-g1", "name": "G1", "status": "ENABLED"}

        success, is_update = _import_resource(client, "d1", "p1", resource, "glossaries", id_map)
        self.assertFalse(success)

    def test_create_asset_with_external_identifier(self):
        client = MagicMock()
        client.create_asset.return_value = {"id": "new-a1"}
        id_map = self._empty_id_map()
        resource = {
            "sourceId": "src-a1", "name": "A1", "description": "desc",
            "typeIdentifier": "type1", "formsInput": [], "externalIdentifier": "ext-id-1",
        }

        success, _ = _import_resource(client, "d1", "p1", resource, "assets", id_map)
        self.assertTrue(success)
        call_kwargs = client.create_asset.call_args[1]
        self.assertEqual(call_kwargs["externalIdentifier"], "ext-id-1")

    def test_missing_source_id_returns_false(self):
        client = MagicMock()
        id_map = self._empty_id_map()
        resource = {"name": "G1"}  # no sourceId

        success, _ = _import_resource(client, "d1", "p1", resource, "glossaries", id_map)
        self.assertFalse(success)



class TestDeleteResource(unittest.TestCase):
    """Test _delete_resource function."""

    def test_delete_glossary(self):
        client = MagicMock()
        result = _delete_resource(client, "d1", "p1", "g1", "glossaries")
        self.assertTrue(result)
        client.delete_glossary.assert_called_once_with(domainIdentifier="d1", identifier="g1")

    def test_delete_asset(self):
        client = MagicMock()
        result = _delete_resource(client, "d1", "p1", "a1", "assets")
        self.assertTrue(result)
        client.delete_asset.assert_called_once_with(domainIdentifier="d1", identifier="a1")

    def test_delete_failure(self):
        client = MagicMock()
        client.delete_glossary.side_effect = Exception("Delete failed")
        result = _delete_resource(client, "d1", "p1", "g1", "glossaries")
        self.assertFalse(result)


class TestPublishResource(unittest.TestCase):
    """Test _publish_resource function."""

    def test_publish_asset(self):
        client = MagicMock()
        result = _publish_resource(client, "d1", "a1", "assets")
        self.assertTrue(result)
        client.create_listing_change_set.assert_called_once_with(
            domainIdentifier="d1", entityIdentifier="a1", entityType="ASSET", action="PUBLISH"
        )

    def test_publish_data_product(self):
        client = MagicMock()
        result = _publish_resource(client, "d1", "dp1", "dataProducts")
        self.assertTrue(result)
        client.create_listing_change_set.assert_called_once_with(
            domainIdentifier="d1", entityIdentifier="dp1", entityType="DATA_PRODUCT", action="PUBLISH"
        )

    def test_publish_non_publishable_type(self):
        client = MagicMock()
        result = _publish_resource(client, "d1", "g1", "glossaries")
        self.assertFalse(result)
        client.create_listing_change_set.assert_not_called()

    def test_publish_failure(self):
        client = MagicMock()
        client.create_listing_change_set.side_effect = Exception("Publish failed")
        result = _publish_resource(client, "d1", "a1", "assets")
        self.assertFalse(result)


class TestIdentifyResourcesToDelete(unittest.TestCase):
    """Test _identify_resources_to_delete function."""

    def test_identifies_extra_resources(self):
        client = MagicMock()
        # Target has glossary "Extra" not in bundle
        client.search.side_effect = lambda **kwargs: {
            "items": [{"glossaryItem": {"id": "extra-g1", "name": "Extra"}}]
        } if kwargs.get("searchScope") == "GLOSSARY" else {"items": []}
        client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(glossaries=[{"sourceId": "g1", "name": "Kept"}])
        to_delete = _identify_resources_to_delete(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["glossaries"]), 1)
        self.assertEqual(to_delete["glossaries"][0]["name"], "Extra")

    def test_no_deletions_when_all_match(self):
        client = MagicMock()
        client.search.side_effect = lambda **kwargs: {
            "items": [{"glossaryItem": {"id": "g1", "name": "Kept"}}]
        } if kwargs.get("searchScope") == "GLOSSARY" else {"items": []}
        client.search_types.return_value = {"items": []}

        catalog_data = _make_valid_catalog(glossaries=[{"sourceId": "g1", "name": "Kept"}])
        to_delete = _identify_resources_to_delete(client, "d1", "p1", catalog_data)
        self.assertEqual(len(to_delete["glossaries"]), 0)


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
        client.create_glossary.side_effect = lambda **kw: (call_order.append("glossary"), {"id": "g1"})[1]
        client.create_glossary_term.side_effect = lambda **kw: (call_order.append("glossaryTerm"), {"id": "t1"})[1]
        client.create_form_type.side_effect = lambda **kw: (call_order.append("formType"), {"revision": "ft1"})[1]
        client.create_asset_type.side_effect = lambda **kw: (call_order.append("assetType"), {"revision": "at1"})[1]
        client.create_asset.side_effect = lambda **kw: (call_order.append("asset"), {"id": "a1"})[1]
        client.create_data_product.side_effect = lambda **kw: (call_order.append("dataProduct"), {"id": "dp1"})[1]

        catalog_data = _make_valid_catalog(
            glossaries=[{"sourceId": "g1", "name": "G1", "status": "ENABLED"}],
            glossaryTerms=[{"sourceId": "t1", "name": "T1", "glossaryId": "g1", "status": "ENABLED"}],
            formTypes=[{"sourceId": "ft1", "name": "FT1", "model": {}}],
            assetTypes=[{"sourceId": "at1", "name": "AT1", "formsInput": {}}],
            assets=[{"sourceId": "a1", "name": "A1", "typeIdentifier": "at1", "formsInput": []}],
            dataProducts=[{"sourceId": "dp1", "name": "DP1", "items": []}],
        )

        import_catalog("d1", "p1", catalog_data, "us-east-1")

        # Verify order: glossary < glossaryTerm < formType < assetType < asset < dataProduct
        self.assertEqual(call_order, ["glossary", "glossaryTerm", "formType", "assetType", "asset", "dataProduct"])

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_deletion_reverse_order(self, mock_get_client):
        """Test resources are deleted in reverse dependency order."""
        client = MagicMock()
        mock_get_client.return_value = client

        # No resources in bundle
        catalog_data = _make_valid_catalog()

        # Target has resources to delete
        def search_side_effect(**kwargs):
            scope = kwargs.get("searchScope")
            if scope == "GLOSSARY":
                return {"items": [{"glossaryItem": {"id": "g1", "name": "ExtraG"}}]}
            if scope == "ASSET":
                return {"items": [{"assetItem": {"identifier": "a1", "name": "ExtraA"}}]}
            return {"items": []}

        client.search.side_effect = search_side_effect
        client.search_types.return_value = {"items": []}

        delete_order = []
        client.delete_glossary.side_effect = lambda **kw: delete_order.append("glossary")
        client.delete_asset.side_effect = lambda **kw: delete_order.append("asset")

        import_catalog("d1", "p1", catalog_data, "us-east-1")

        # Assets should be deleted before glossaries (reverse order)
        self.assertIn("asset", delete_order)
        self.assertIn("glossary", delete_order)
        self.assertLess(delete_order.index("asset"), delete_order.index("glossary"))

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_publish_when_source_listed(self, mock_get_client):
        """Test automatic publishing when source asset has listingStatus=LISTED."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}

        catalog_data = _make_valid_catalog(
            assets=[{"sourceId": "a1", "name": "A1", "typeIdentifier": "t1", "formsInput": [], "listingStatus": "LISTED"}]
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
            assets=[{"sourceId": "a1", "name": "A1", "typeIdentifier": "t1", "formsInput": []}]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")
        client.create_listing_change_set.assert_not_called()
        self.assertEqual(result["published"], 0)

    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_no_publish_when_skip_publish(self, mock_get_client):
        """Test publish API is NOT called when skip_publish=True even if source was LISTED."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.return_value = {"id": "new-a1"}

        catalog_data = _make_valid_catalog(
            assets=[{"sourceId": "a1", "name": "A1", "typeIdentifier": "t1", "formsInput": [], "listingStatus": "LISTED"}]
        )

        result = import_catalog("d1", "p1", catalog_data, "us-east-1", skip_publish=True)
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
            assets=[{"sourceId": "a1", "name": "A1", "typeIdentifier": "t1", "formsInput": [], "listingStatus": "LISTED"}]
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
        self.assertIn("deleted", result)
        self.assertIn("failed", result)
        self.assertIn("published", result)

    def test_invalid_json_raises_before_api_calls(self):
        """Test that malformed JSON raises ValueError before any API calls."""
        with self.assertRaises(ValueError):
            import_catalog("d1", "p1", {"metadata": {}}, "us-east-1")


if __name__ == "__main__":
    unittest.main()

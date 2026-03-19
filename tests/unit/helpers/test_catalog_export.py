"""Unit tests for catalog export functionality.

Tests the simplified CatalogExporter that exports ALL project-owned catalog
resources when enabled, with support for externalIdentifier, formsOutput→formsInput,
termRelations, and optional --updated-after CLI flag.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from smus_cicd.helpers.catalog_export import (
    ALL_RESOURCE_TYPES,
    SORT_CLAUSE,
    _enrich_asset_items,
    _enrich_data_product_items,
    _search_resources,
    _search_type_resources,
    _serialize_resource,
    export_catalog,
)


class TestSearchResources(unittest.TestCase):
    """Test _search_resources function."""

    def test_single_page(self):
        """Test searching resources with single page of results."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "items": [
                {"glossaryItem": {"id": "g1", "name": "Glossary 1"}},
                {"glossaryItem": {"id": "g2", "name": "Glossary 2"}},
            ]
        }

        results = _search_resources(
            mock_client, "domain-123", "project-456", "GLOSSARY"
        )

        self.assertEqual(len(results), 2)
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args[1]
        self.assertEqual(call_args["searchScope"], "GLOSSARY")
        self.assertEqual(call_args["owningProjectIdentifier"], "project-456")
        self.assertEqual(call_args["domainIdentifier"], "domain-123")
        self.assertEqual(call_args["sort"], SORT_CLAUSE)

    def test_pagination(self):
        """Test searching resources with pagination."""
        mock_client = MagicMock()
        mock_client.search.side_effect = [
            {
                "items": [{"glossaryItem": {"id": "g1", "name": "Glossary 1"}}],
                "nextToken": "token-1",
            },
            {
                "items": [{"glossaryItem": {"id": "g2", "name": "Glossary 2"}}],
            },
        ]

        results = _search_resources(
            mock_client, "domain-123", "project-456", "GLOSSARY"
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_client.search.call_count, 2)
        # Second call should include nextToken
        second_call_args = mock_client.search.call_args_list[1][1]
        self.assertEqual(second_call_args["nextToken"], "token-1")

    def test_with_updated_after_filter(self):
        """Test searching resources with --updated-after CLI flag filter."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        _search_resources(
            mock_client,
            "domain-123",
            "project-456",
            "ASSET",
            updated_after="2025-01-01T00:00:00Z",
        )

        call_args = mock_client.search.call_args[1]
        self.assertIn("filters", call_args)
        self.assertEqual(call_args["filters"]["filter"]["attribute"], "updatedAt")
        self.assertEqual(
            call_args["filters"]["filter"]["value"], "2025-01-01T00:00:00Z"
        )

    def test_without_updated_after_filter(self):
        """Test that no filter is applied when --updated-after is not provided."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        _search_resources(mock_client, "domain-123", "project-456", "ASSET")

        call_args = mock_client.search.call_args[1]
        self.assertNotIn("filters", call_args)

    def test_owning_project_filter_applied_for_all_scopes(self):
        """Test owningProjectIdentifier is applied for all search scopes."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        for scope in ["GLOSSARY", "GLOSSARY_TERM", "ASSET", "DATA_PRODUCT"]:
            _search_resources(mock_client, "domain-123", "project-456", scope)
            call_args = mock_client.search.call_args[1]
            self.assertEqual(
                call_args["owningProjectIdentifier"],
                "project-456",
                f"owningProjectIdentifier not set for scope {scope}",
            )

    def test_sort_clause_applied(self):
        """Test sort by updatedAt DESC is applied to all queries."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        _search_resources(mock_client, "domain-123", "project-456", "GLOSSARY")

        call_args = mock_client.search.call_args[1]
        self.assertEqual(call_args["sort"], SORT_CLAUSE)

    def test_empty_results(self):
        """Test handling of empty search results."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        results = _search_resources(
            mock_client, "domain-123", "project-456", "GLOSSARY"
        )

        self.assertEqual(results, [])

    def test_api_error_propagation(self):
        """Test that API errors propagate up."""
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("AccessDenied")

        with self.assertRaises(Exception) as ctx:
            _search_resources(mock_client, "domain-123", "project-456", "GLOSSARY")
        self.assertIn("AccessDenied", str(ctx.exception))


class TestSearchTypeResources(unittest.TestCase):
    """Test _search_type_resources function."""

    def test_form_types(self):
        """Test searching form types with project ownership filter."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {
            "items": [
                {
                    "formTypeItem": {
                        "name": "FormType1",
                        "owningProjectId": "project-456",
                    }
                },
                {
                    "formTypeItem": {
                        "name": "FormType2",
                        "owningProjectId": "other-project",
                    }
                },
            ]
        }

        results = _search_type_resources(
            mock_client, "domain-123", "project-456", "FORM_TYPE"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["formTypeItem"]["name"], "FormType1")

    def test_asset_types(self):
        """Test searching asset types."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {
            "items": [
                {
                    "assetTypeItem": {
                        "name": "AssetType1",
                        "owningProjectId": "project-456",
                    }
                }
            ]
        }

        results = _search_type_resources(
            mock_client, "domain-123", "project-456", "ASSET_TYPE"
        )

        self.assertEqual(len(results), 1)
        call_args = mock_client.search_types.call_args[1]
        self.assertEqual(call_args["searchScope"], "ASSET_TYPE")
        self.assertFalse(call_args["managed"])

    def test_owning_project_filter_applied(self):
        """Test owningProjectId filtering is done client-side for SearchTypes API."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {
            "items": [
                {
                    "formTypeItem": {
                        "name": "OwnedType",
                        "owningProjectId": "project-456",
                    }
                },
                {
                    "formTypeItem": {
                        "name": "OtherType",
                        "owningProjectId": "other-project",
                    }
                },
            ]
        }

        results = _search_type_resources(
            mock_client, "domain-123", "project-456", "FORM_TYPE"
        )

        call_args = mock_client.search_types.call_args[1]
        # owningProjectIdentifier is NOT a valid param for search_types
        self.assertNotIn("owningProjectIdentifier", call_args)
        # Client-side filter should only return project-owned items
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["formTypeItem"]["name"], "OwnedType")

    def test_managed_false(self):
        """Test managed=False is set for all SearchTypes queries."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        for scope in ["FORM_TYPE", "ASSET_TYPE"]:
            _search_type_resources(mock_client, "domain-123", "project-456", scope)
            call_args = mock_client.search_types.call_args[1]
            self.assertFalse(call_args["managed"])

    def test_with_updated_after_filter(self):
        """Test --updated-after CLI flag filter for SearchTypes."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        _search_type_resources(
            mock_client,
            "domain-123",
            "project-456",
            "FORM_TYPE",
            updated_after="2025-01-01T00:00:00Z",
        )

        call_args = mock_client.search_types.call_args[1]
        self.assertIn("filters", call_args)
        self.assertEqual(
            call_args["filters"]["filter"]["value"], "2025-01-01T00:00:00Z"
        )

    def test_pagination(self):
        """Test pagination for SearchTypes API."""
        mock_client = MagicMock()
        mock_client.search_types.side_effect = [
            {
                "items": [
                    {
                        "formTypeItem": {
                            "name": "FT1",
                            "owningProjectId": "project-456",
                        }
                    }
                ],
                "nextToken": "token-1",
            },
            {
                "items": [
                    {
                        "formTypeItem": {
                            "name": "FT2",
                            "owningProjectId": "project-456",
                        }
                    }
                ],
            },
        ]

        results = _search_type_resources(
            mock_client, "domain-123", "project-456", "FORM_TYPE"
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_client.search_types.call_count, 2)

    def test_sort_clause_applied(self):
        """Test sort by updatedAt DESC is applied."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        _search_type_resources(mock_client, "domain-123", "project-456", "FORM_TYPE")

        call_args = mock_client.search_types.call_args[1]
        self.assertEqual(call_args["sort"], SORT_CLAUSE)

    def test_api_error_propagation(self):
        """Test that API errors propagate up."""
        mock_client = MagicMock()
        mock_client.search_types.side_effect = Exception("ServiceError")

        with self.assertRaises(Exception) as ctx:
            _search_type_resources(
                mock_client, "domain-123", "project-456", "FORM_TYPE"
            )
        self.assertIn("ServiceError", str(ctx.exception))


class TestEnrichAssetItems(unittest.TestCase):
    """Test _enrich_asset_items function."""

    def test_enriches_with_get_asset(self):
        """Test that assets are enriched with formsOutput from GetAsset."""
        mock_client = MagicMock()
        mock_client.get_asset.return_value = {
            "ResponseMetadata": {},
            "id": "asset-1",
            "name": "TestAsset",
            "typeIdentifier": "CustomType",
            "formsOutput": [
                {"formName": "MyForm", "typeName": "MyFormType", "content": "{}"}
            ],
        }

        items = [{"assetItem": {"identifier": "asset-1", "name": "TestAsset"}}]
        result = _enrich_asset_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        asset = result[0]["assetItem"]
        self.assertEqual(len(asset["formsOutput"]), 1)
        self.assertNotIn("ResponseMetadata", asset)

    def test_falls_back_on_error(self):
        """Test that original item is kept if GetAsset fails."""
        mock_client = MagicMock()
        mock_client.get_asset.side_effect = Exception("AccessDenied")

        items = [{"assetItem": {"identifier": "asset-1", "name": "TestAsset"}}]
        result = _enrich_asset_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assetItem"]["name"], "TestAsset")

    def test_skips_items_without_identifier(self):
        """Test items without identifier are passed through unchanged."""
        mock_client = MagicMock()

        items = [{"assetItem": {"name": "NoIdAsset"}}]
        result = _enrich_asset_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        mock_client.get_asset.assert_not_called()


class TestEnrichDataProductItems(unittest.TestCase):
    """Test _enrich_data_product_items function."""

    def test_enriches_with_get_data_product(self):
        """Test that data products are enriched with items from GetDataProduct."""
        mock_client = MagicMock()
        mock_client.get_data_product.return_value = {
            "ResponseMetadata": {},
            "id": "dp-1",
            "name": "TestDP",
            "items": [{"identifier": "asset-1", "itemType": "ASSET", "revision": "1"}],
            "status": "CREATED",
        }

        items = [{"dataProductItem": {"id": "dp-1", "name": "TestDP"}}]
        result = _enrich_data_product_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        dp = result[0]["dataProductItem"]
        self.assertEqual(len(dp["items"]), 1)
        self.assertEqual(dp["items"][0]["identifier"], "asset-1")
        self.assertNotIn("ResponseMetadata", dp)

    def test_falls_back_on_error(self):
        """Test that original item is kept if GetDataProduct fails."""
        mock_client = MagicMock()
        mock_client.get_data_product.side_effect = Exception("AccessDenied")

        items = [{"dataProductItem": {"id": "dp-1", "name": "TestDP"}}]
        result = _enrich_data_product_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["dataProductItem"]["name"], "TestDP")

    def test_skips_items_without_id(self):
        """Test items without id are passed through unchanged."""
        mock_client = MagicMock()

        items = [{"dataProductItem": {"name": "NoIdDP"}}]
        result = _enrich_data_product_items(mock_client, "domain-123", items)

        self.assertEqual(len(result), 1)
        mock_client.get_data_product.assert_not_called()


class TestSerializeResource(unittest.TestCase):
    """Test _serialize_resource function."""

    def test_serialize_glossary(self):
        """Test serializing a glossary."""
        resource = {
            "glossaryItem": {
                "id": "glossary-123",
                "name": "Business Glossary",
                "description": "Main glossary",
                "status": "ENABLED",
            }
        }

        result = _serialize_resource(resource, "glossaries")

        self.assertEqual(result["sourceId"], "glossary-123")
        self.assertEqual(result["name"], "Business Glossary")
        self.assertEqual(result["description"], "Main glossary")
        self.assertEqual(result["status"], "ENABLED")

    def test_serialize_glossary_term_with_term_relations(self):
        """Test serializing a glossary term with termRelations."""
        resource = {
            "glossaryTermItem": {
                "id": "term-123",
                "name": "Customer",
                "shortDescription": "A customer entity",
                "longDescription": "Detailed description",
                "glossaryId": "glossary-123",
                "status": "ENABLED",
                "termRelations": {"isA": ["term-456"], "hasA": ["term-789"]},
            }
        }

        result = _serialize_resource(resource, "glossaryTerms")

        self.assertEqual(result["sourceId"], "term-123")
        self.assertEqual(result["name"], "Customer")
        self.assertEqual(result["glossaryId"], "glossary-123")
        self.assertEqual(
            result["termRelations"],
            {"isA": ["term-456"], "hasA": ["term-789"]},
        )

    def test_serialize_glossary_term_empty_term_relations(self):
        """Test serializing a glossary term with no termRelations defaults to empty dict."""
        resource = {
            "glossaryTermItem": {
                "id": "term-123",
                "name": "Customer",
            }
        }

        result = _serialize_resource(resource, "glossaryTerms")
        self.assertEqual(result["termRelations"], {})

    def test_serialize_form_type_with_model(self):
        """Test serializing a form type with complete model structure."""
        resource = {
            "formTypeItem": {
                "revision": "rev-123",
                "name": "CustomForm",
                "description": "Custom metadata form",
                "model": {
                    "smithy": "structure MyForm { @required field1: String, @range(min: 0) field2: Integer }"
                },
            }
        }

        result = _serialize_resource(resource, "formTypes")

        self.assertEqual(result["sourceId"], "rev-123")
        self.assertEqual(result["name"], "CustomForm")
        self.assertIn("smithy", result["model"])
        self.assertIn("@required", result["model"]["smithy"])

    def test_serialize_asset_type(self):
        """Test serializing an asset type."""
        resource = {
            "assetTypeItem": {
                "revision": "rev-456",
                "name": "CustomAssetType",
                "description": "Custom asset type",
                "formsOutput": {"form1": {}},
            }
        }

        result = _serialize_resource(resource, "assetTypes")

        self.assertEqual(result["sourceId"], "rev-456")
        self.assertEqual(result["name"], "CustomAssetType")
        self.assertEqual(result["formsInput"], {"form1": {}})

    def test_serialize_asset_with_external_identifier(self):
        """Test serializing an asset with externalIdentifier."""
        resource = {
            "assetItem": {
                "identifier": "asset-789",
                "name": "DataAsset",
                "description": "A data asset",
                "typeIdentifier": "CustomAssetType",
                "formsOutput": [{"formName": "metadata"}],
                "externalIdentifier": "arn:aws:glue:us-east-1:123456789:table/db/tbl",
            }
        }

        result = _serialize_resource(resource, "assets")

        self.assertEqual(result["sourceId"], "asset-789")
        self.assertEqual(result["name"], "DataAsset")
        self.assertEqual(result["typeIdentifier"], "CustomAssetType")
        self.assertEqual(result["formsInput"], [{"formName": "metadata"}])
        self.assertNotIn("inputForms", result)
        self.assertEqual(
            result["externalIdentifier"],
            "arn:aws:glue:us-east-1:123456789:table/db/tbl",
        )

    def test_serialize_asset_without_external_identifier(self):
        """Test serializing an asset without externalIdentifier omits the field."""
        resource = {
            "assetItem": {
                "identifier": "asset-789",
                "name": "DataAsset",
                "description": "A data asset",
                "typeIdentifier": "CustomAssetType",
                "formsOutput": [],
            }
        }

        result = _serialize_resource(resource, "assets")

        self.assertNotIn("externalIdentifier", result)

    def test_serialize_asset_forms_output_to_forms_input(self):
        """Test serializing an asset maps formsOutput to formsInput."""
        resource = {
            "assetItem": {
                "identifier": "asset-1",
                "name": "Asset1",
                "formsOutput": [
                    {
                        "formName": "form1",
                        "typeName": "ft1",
                        "content": '{"key": "val"}',
                    },
                    {
                        "formName": "form2",
                        "typeName": "ft2",
                        "content": '{"a": 1}',
                    },
                ],
            }
        }

        result = _serialize_resource(resource, "assets")

        self.assertEqual(len(result["formsInput"]), 2)
        self.assertEqual(result["formsInput"][0]["formName"], "form1")
        self.assertNotIn("inputForms", result)

    def test_serialize_data_product(self):
        """Test serializing a data product."""
        resource = {
            "dataProductItem": {
                "id": "dp-123",
                "name": "CustomerDataProduct",
                "description": "Customer data product",
                "items": [{"assetId": "asset-1"}, {"assetId": "asset-2"}],
            }
        }

        result = _serialize_resource(resource, "dataProducts")

        self.assertEqual(result["sourceId"], "dp-123")
        self.assertEqual(result["name"], "CustomerDataProduct")
        self.assertEqual(len(result["items"]), 2)

    def test_serialize_unknown_type_returns_empty(self):
        """Test serializing an unknown resource type returns empty dict."""
        result = _serialize_resource({"unknown": {}}, "unknownType")
        self.assertEqual(result, {})


class TestExportCatalog(unittest.TestCase):
    """Test export_catalog function."""

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_exports_all_resource_types(self, mock_get_client):
        """Test that export_catalog exports ALL resource types."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.search.side_effect = [
            {"items": [{"glossaryItem": {"id": "g1", "name": "G1"}}]},
            {
                "items": [
                    {
                        "glossaryTermItem": {
                            "id": "t1",
                            "name": "T1",
                            "termRelations": {},
                        }
                    }
                ]
            },
            {"items": [{"assetItem": {"identifier": "a1", "name": "A1"}}]},
            {"items": [{"dataProductItem": {"id": "dp1", "name": "DP1"}}]},
        ]
        mock_client.get_asset.return_value = {
            "ResponseMetadata": {},
            "id": "a1",
            "name": "A1",
            "typeIdentifier": "CustomType",
            "formsOutput": [{"formName": "form1"}],
        }
        mock_client.get_data_product.return_value = {
            "ResponseMetadata": {},
            "id": "dp1",
            "name": "DP1",
            "items": [{"identifier": "a1", "itemType": "ASSET"}],
        }
        mock_client.search_types.side_effect = [
            {
                "items": [
                    {
                        "formTypeItem": {
                            "revision": "f1",
                            "name": "F1",
                            "owningProjectId": "proj-1",
                        }
                    }
                ]
            },
            {
                "items": [
                    {
                        "assetTypeItem": {
                            "revision": "at1",
                            "name": "AT1",
                            "owningProjectId": "proj-1",
                        }
                    }
                ]
            },
        ]

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertEqual(len(result["glossaries"]), 1)
        self.assertEqual(len(result["glossaryTerms"]), 1)
        self.assertEqual(len(result["assets"]), 1)
        self.assertEqual(len(result["dataProducts"]), 1)
        self.assertEqual(len(result["formTypes"]), 1)
        self.assertEqual(len(result["assetTypes"]), 1)

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_json_structure(self, mock_get_client):
        """Test the output JSON structure matches the schema."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        expected_keys = {
            "metadata",
            "glossaries",
            "glossaryTerms",
            "formTypes",
            "assetTypes",
            "assets",
            "dataProducts",
        }
        self.assertEqual(set(result.keys()), expected_keys)

        metadata = result["metadata"]
        self.assertEqual(metadata["sourceProjectId"], "proj-1")
        self.assertEqual(metadata["sourceDomainId"], "domain-1")
        self.assertIn("exportTimestamp", metadata)
        self.assertEqual(
            set(metadata["resourceTypes"]),
            {
                "glossaries",
                "glossaryTerms",
                "formTypes",
                "assetTypes",
                "assets",
                "dataProducts",
            },
        )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_api_routing_search_api(self, mock_get_client):
        """Test correct API routing: Search API for glossaries, terms, assets, data products."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog("domain-1", "proj-1", "us-east-1")

        # Search API should be called 4 times (glossaries, glossaryTerms, assets, dataProducts)
        self.assertEqual(mock_client.search.call_count, 4)
        scopes_called = [
            call[1]["searchScope"] for call in mock_client.search.call_args_list
        ]
        self.assertIn("GLOSSARY", scopes_called)
        self.assertIn("GLOSSARY_TERM", scopes_called)
        self.assertIn("ASSET", scopes_called)
        self.assertIn("DATA_PRODUCT", scopes_called)

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_api_routing_search_types_api(self, mock_get_client):
        """Test correct API routing: SearchTypes API for formTypes, assetTypes."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog("domain-1", "proj-1", "us-east-1")

        # SearchTypes API should be called 2 times (formTypes, assetTypes)
        self.assertEqual(mock_client.search_types.call_count, 2)
        scopes_called = [
            call[1]["searchScope"] for call in mock_client.search_types.call_args_list
        ]
        self.assertIn("FORM_TYPE", scopes_called)
        self.assertIn("ASSET_TYPE", scopes_called)

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_owning_project_filter_on_all_queries(self, mock_get_client):
        """Test owningProjectIdentifier is applied to all search queries, and client-side filter for search_types."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog("domain-1", "proj-1", "us-east-1")

        # Search API calls should have owningProjectIdentifier
        for call in mock_client.search.call_args_list:
            self.assertEqual(
                call[1]["owningProjectIdentifier"],
                "proj-1",
                f"owningProjectIdentifier missing for search call: {call}",
            )
        # SearchTypes API calls should NOT have owningProjectIdentifier
        # (filtering is done client-side)
        for call in mock_client.search_types.call_args_list:
            self.assertNotIn(
                "owningProjectIdentifier",
                call[1],
                f"owningProjectIdentifier should not be in search_types call: {call}",
            )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_updated_after_filter_applied_to_all_types(self, mock_get_client):
        """Test --updated-after CLI flag filter is applied uniformly to ALL resource types."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog(
            "domain-1",
            "proj-1",
            "us-east-1",
            updated_after="2025-06-01T00:00:00Z",
        )

        # All Search API calls should have the filter
        for call in mock_client.search.call_args_list:
            self.assertIn("filters", call[1])
            self.assertEqual(
                call[1]["filters"]["filter"]["value"],
                "2025-06-01T00:00:00Z",
            )

        # All SearchTypes API calls should have the filter
        for call in mock_client.search_types.call_args_list:
            self.assertIn("filters", call[1])
            self.assertEqual(
                call[1]["filters"]["filter"]["value"],
                "2025-06-01T00:00:00Z",
            )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_no_filter_when_updated_after_not_provided(self, mock_get_client):
        """Test no filter is applied when --updated-after is not provided."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog("domain-1", "proj-1", "us-east-1")

        for call in mock_client.search.call_args_list:
            self.assertNotIn("filters", call[1])
        for call in mock_client.search_types.call_args_list:
            self.assertNotIn("filters", call[1])

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_external_identifier_exported_for_assets(self, mock_get_client):
        """Test externalIdentifier is exported for assets when present."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = [
            {"items": []},  # glossaries
            {"items": []},  # glossaryTerms
            {
                "items": [
                    {
                        "assetItem": {
                            "identifier": "a1",
                            "name": "Asset1",
                        }
                    }
                ]
            },  # assets
            {"items": []},  # dataProducts
        ]
        mock_client.get_asset.return_value = {
            "ResponseMetadata": {},
            "id": "a1",
            "name": "Asset1",
            "typeIdentifier": "CustomType",
            "externalIdentifier": "arn:aws:glue:us-east-1:123:table/db/tbl",
            "formsOutput": [],
        }
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertEqual(
            result["assets"][0]["externalIdentifier"],
            "arn:aws:glue:us-east-1:123:table/db/tbl",
        )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_input_forms_exported_for_assets(self, mock_get_client):
        """Test formsOutput from get_asset is exported as formsInput for assets."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = [
            {"items": []},  # glossaries
            {"items": []},  # glossaryTerms
            {
                "items": [
                    {
                        "assetItem": {
                            "identifier": "a1",
                            "name": "Asset1",
                        }
                    }
                ]
            },  # assets
            {"items": []},  # dataProducts
        ]
        mock_client.get_asset.return_value = {
            "ResponseMetadata": {},
            "id": "a1",
            "name": "Asset1",
            "typeIdentifier": "CustomType",
            "formsOutput": [
                {
                    "formName": "form1",
                    "typeName": "ft1",
                    "content": "{}",
                },
            ],
        }
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertIn("formsInput", result["assets"][0])
        self.assertEqual(len(result["assets"][0]["formsInput"]), 1)
        self.assertEqual(result["assets"][0]["formsInput"][0]["formName"], "form1")
        self.assertNotIn("inputForms", result["assets"][0])

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_term_relations_exported_for_glossary_terms(self, mock_get_client):
        """Test termRelations field is exported for glossary terms."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = [
            {"items": []},  # glossaries
            {
                "items": [
                    {
                        "glossaryTermItem": {
                            "id": "t1",
                            "name": "Term1",
                            "termRelations": {"isA": ["t2"], "hasA": ["t3"]},
                        }
                    }
                ]
            },  # glossaryTerms
            {"items": []},  # assets
            {"items": []},  # dataProducts
        ]
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertEqual(
            result["glossaryTerms"][0]["termRelations"],
            {"isA": ["t2"], "hasA": ["t3"]},
        )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_error_propagation_on_api_failure(self, mock_get_client):
        """Test that API errors propagate and no partial JSON is produced."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = Exception("ThrottlingException")

        with self.assertRaises(Exception) as ctx:
            export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertIn("ThrottlingException", str(ctx.exception))

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_empty_project_produces_valid_json(self, mock_get_client):
        """Test that an empty project produces valid JSON with empty arrays."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        for rt in ALL_RESOURCE_TYPES:
            self.assertEqual(result[rt], [], f"{rt} should be empty")

        # Should still be valid JSON
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        self.assertEqual(set(parsed.keys()), set(result.keys()))

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_simplified_signature_no_resource_types_param(self, mock_get_client):
        """Test that export_catalog does NOT accept resource_types parameter."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        # The simplified function should work with just domain_id, project_id, region
        result = export_catalog("domain-1", "proj-1", "us-east-1")
        self.assertIn("metadata", result)

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_no_metadata_forms_key_in_output(self, mock_get_client):
        """Test that the output does NOT contain a metadataForms key (simplified)."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertNotIn("metadataForms", result)


class TestExportedFieldsNotEmpty(unittest.TestCase):
    """Verify that enriched fields in exported resources are populated, not empty.

    These tests simulate the full export_catalog pipeline (search → enrich → serialize)
    with realistic API responses to catch cases where the Search API returns summary
    data missing fields that only the Get* APIs provide.
    """

    def _build_mock_client(self):
        """Build a mock client with realistic Search + Get API responses.

        Search API responses contain only summary fields (what the real API returns).
        Get API responses contain full details (formsOutput, items, listing, etc.).
        """
        mock_client = MagicMock()

        # Search API returns summary data only
        mock_client.search.side_effect = [
            # glossaries
            {
                "items": [
                    {
                        "glossaryItem": {
                            "id": "g1",
                            "name": "BusinessGlossary",
                            "description": "Main glossary",
                            "status": "ENABLED",
                        }
                    }
                ]
            },
            # glossaryTerms
            {
                "items": [
                    {
                        "glossaryTermItem": {
                            "id": "t1",
                            "name": "Revenue",
                            "shortDescription": "Total revenue",
                            "longDescription": "Total revenue from all sources",
                            "glossaryId": "g1",
                            "status": "ENABLED",
                            "termRelations": {
                                "isA": ["t2"],
                                "hasA": [],
                            },
                        }
                    }
                ]
            },
            # assets — Search API returns summary WITHOUT formsOutput or listing
            {
                "items": [
                    {
                        "assetItem": {
                            "identifier": "a1",
                            "name": "CustomerTable",
                            "typeIdentifier": "CustomAssetType",
                            # No formsOutput, no listing, no description
                        }
                    }
                ]
            },
            # dataProducts — Search API returns summary WITHOUT items
            {
                "items": [
                    {
                        "dataProductItem": {
                            "id": "dp1",
                            "name": "CustomerDataProduct",
                            # No items, no description, no status
                        }
                    }
                ]
            },
        ]

        # GetAsset returns full details
        mock_client.get_asset.return_value = {
            "ResponseMetadata": {},
            "id": "a1",
            "name": "CustomerTable",
            "description": "Customer dimension table",
            "typeIdentifier": "CustomAssetType",
            "externalIdentifier": "arn:aws:glue:us-east-1:123456789:table/db/customers",
            "formsOutput": [
                {
                    "formName": "S3Location",
                    "typeName": "amazon.datazone.S3ObjectCollectionFormType",
                    "content": '{"bucketArn":"arn:aws:s3:::my-bucket"}',
                    "typeRevision": "1",
                }
            ],
            "listing": {"listingId": "lst-1", "listingStatus": "LISTED"},
            "owningProjectId": "proj-1",
            "revision": "1",
            "typeRevision": "3",
        }

        # GetDataProduct returns full details
        mock_client.get_data_product.return_value = {
            "ResponseMetadata": {},
            "id": "dp1",
            "name": "CustomerDataProduct",
            "description": "Bundled customer data",
            "items": [
                {
                    "identifier": "a1",
                    "itemType": "ASSET",
                    "revision": "1",
                }
            ],
            "status": "CREATED",
            "listing": {"listingId": "lst-dp1", "listingStatus": "LISTED"},
            "owningProjectId": "proj-1",
        }

        # SearchTypes returns type resources with owningProjectId
        mock_client.search_types.side_effect = [
            # formTypes
            {
                "items": [
                    {
                        "formTypeItem": {
                            "revision": "ft-rev-1",
                            "name": "S3LocationForm",
                            "description": "S3 location metadata",
                            "model": {
                                "smithy": "structure S3Location { bucketArn: String }"
                            },
                            "owningProjectId": "proj-1",
                        }
                    }
                ]
            },
            # assetTypes
            {
                "items": [
                    {
                        "assetTypeItem": {
                            "revision": "at-rev-1",
                            "name": "CustomAssetType",
                            "description": "Custom asset type for tables",
                            "formsOutput": {
                                "S3LocationForm": {
                                    "typeIdentifier": "S3LocationForm",
                                    "typeRevision": "1",
                                    "required": True,
                                }
                            },
                            "owningProjectId": "proj-1",
                        }
                    }
                ]
            },
        ]

        return mock_client

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_glossary_fields_populated(self, mock_get_client):
        """Verify glossary fields are non-empty after full export pipeline."""
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        g = result["glossaries"][0]
        self.assertEqual(g["sourceId"], "g1")
        self.assertEqual(g["name"], "BusinessGlossary")
        self.assertEqual(g["description"], "Main glossary")
        self.assertEqual(g["status"], "ENABLED")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_glossary_term_fields_populated(self, mock_get_client):
        """Verify glossary term fields are non-empty after full export pipeline."""
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        t = result["glossaryTerms"][0]
        self.assertEqual(t["sourceId"], "t1")
        self.assertEqual(t["name"], "Revenue")
        self.assertEqual(t["shortDescription"], "Total revenue")
        self.assertEqual(t["longDescription"], "Total revenue from all sources")
        self.assertEqual(t["glossaryId"], "g1")
        self.assertEqual(t["status"], "ENABLED")
        self.assertEqual(t["termRelations"], {"isA": ["t2"], "hasA": []})

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_form_type_fields_populated(self, mock_get_client):
        """Verify form type fields including model are non-empty after full export."""
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        ft = result["formTypes"][0]
        self.assertEqual(ft["sourceId"], "ft-rev-1")
        self.assertEqual(ft["name"], "S3LocationForm")
        self.assertEqual(ft["description"], "S3 location metadata")
        self.assertIn("smithy", ft["model"])
        self.assertTrue(len(ft["model"]["smithy"]) > 0)

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_asset_type_fields_populated(self, mock_get_client):
        """Verify asset type fields including formsInput are non-empty after full export."""
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        at = result["assetTypes"][0]
        self.assertEqual(at["sourceId"], "at-rev-1")
        self.assertEqual(at["name"], "CustomAssetType")
        self.assertEqual(at["description"], "Custom asset type for tables")
        self.assertIsInstance(at["formsInput"], dict)
        self.assertIn("S3LocationForm", at["formsInput"])

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_asset_fields_populated_after_enrichment(self, mock_get_client):
        """Verify asset fields from GetAsset enrichment are non-empty.

        The Search API returns only summary data (identifier, name, typeIdentifier).
        After enrichment via GetAsset, formsInput, description, externalIdentifier,
        and listingStatus should all be populated.
        """
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        a = result["assets"][0]
        self.assertEqual(a["sourceId"], "a1")
        self.assertEqual(a["name"], "CustomerTable")
        self.assertEqual(a["description"], "Customer dimension table")
        self.assertEqual(a["typeIdentifier"], "CustomAssetType")
        # formsInput comes from GetAsset's formsOutput — must not be empty
        self.assertIsInstance(a["formsInput"], list)
        self.assertEqual(len(a["formsInput"]), 1)
        self.assertEqual(a["formsInput"][0]["formName"], "S3Location")
        # externalIdentifier from GetAsset
        self.assertIn("externalIdentifier", a)
        self.assertIn("arn:aws:glue", a["externalIdentifier"])

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_asset_listing_status_populated_after_enrichment(self, mock_get_client):
        """Verify listingStatus is captured from GetAsset's listing.listingStatus field."""
        mock_client = self._build_mock_client()
        mock_get_client.return_value = mock_client

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        a = result["assets"][0]
        # GetAsset returns listing.listingStatus — code must extract it
        self.assertIn("listingStatus", a)
        self.assertEqual(a["listingStatus"], "LISTED")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_data_product_items_populated_after_enrichment(self, mock_get_client):
        """Verify data product items from GetDataProduct enrichment are non-empty.

        The Search API's DataProductResultItem does NOT include an 'items' field.
        After enrichment via GetDataProduct, items should be populated.
        """
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        dp = result["dataProducts"][0]
        self.assertEqual(dp["sourceId"], "dp1")
        self.assertEqual(dp["name"], "CustomerDataProduct")
        self.assertEqual(dp["description"], "Bundled customer data")
        # items comes from GetDataProduct — must not be empty
        self.assertIsInstance(dp["items"], list)
        self.assertEqual(len(dp["items"]), 1)
        self.assertEqual(dp["items"][0]["identifier"], "a1")
        self.assertEqual(dp["items"][0]["itemType"], "ASSET")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_data_product_listing_status_populated_after_enrichment(
        self, mock_get_client
    ):
        """Verify listingStatus is captured from GetDataProduct's listing.listingStatus field.

        Same pattern as assets: GetDataProduct nests listing status under
        listing.listingStatus, not at the top level.
        """
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        dp = result["dataProducts"][0]
        self.assertIn("listingStatus", dp)
        self.assertEqual(dp["listingStatus"], "LISTED")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_data_product_items_empty_without_enrichment(self, mock_get_client):
        """Verify that without enrichment, data product items would be empty.

        This documents the Search API limitation: DataProductResultItem has no
        'items' field, so serializing directly from search results yields [].
        """
        # Serialize directly from search result (no enrichment)
        search_result = {"dataProductItem": {"id": "dp1", "name": "DP1"}}
        result = _serialize_resource(search_result, "dataProducts")
        self.assertEqual(result["items"], [], "Search result has no items field")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_asset_forms_empty_without_enrichment(self, mock_get_client):
        """Verify that without enrichment, asset formsInput would be empty.

        This documents the Search API limitation: AssetItem from search has no
        'formsOutput' field, so serializing directly from search results yields [].
        """
        # Serialize directly from search result (no enrichment)
        search_result = {
            "assetItem": {"identifier": "a1", "name": "A1", "typeIdentifier": "T1"}
        }
        result = _serialize_resource(search_result, "assets")
        self.assertEqual(result["formsInput"], [], "Search result has no formsOutput")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_all_resource_types_have_source_id_and_name(self, mock_get_client):
        """Verify every exported resource has non-None sourceId and name."""
        mock_get_client.return_value = self._build_mock_client()
        result = export_catalog("domain-1", "proj-1", "us-east-1")

        for resource_type in ALL_RESOURCE_TYPES:
            for resource in result[resource_type]:
                self.assertIsNotNone(
                    resource.get("sourceId"),
                    f"{resource_type} resource missing sourceId: {resource}",
                )
                self.assertIsNotNone(
                    resource.get("name"),
                    f"{resource_type} resource missing name: {resource}",
                )


if __name__ == "__main__":
    unittest.main()

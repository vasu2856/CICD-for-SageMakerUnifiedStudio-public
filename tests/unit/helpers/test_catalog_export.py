"""Unit tests for catalog export functionality.

Tests the simplified CatalogExporter that exports ALL project-owned catalog
resources when enabled, with support for externalIdentifier, inputForms,
termRelations, and optional --updated-after CLI flag.
"""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from smus_cicd.helpers.catalog_export import (
    ALL_RESOURCE_TYPES,
    SEARCH_API_RESOURCE_TYPES,
    SEARCH_TYPES_API_RESOURCE_TYPES,
    SORT_CLAUSE,
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
        self.assertEqual(
            call_args["filters"]["filter"]["attribute"], "updatedAt"
        )
        self.assertEqual(
            call_args["filters"]["filter"]["value"], "2025-01-01T00:00:00Z"
        )

    def test_without_updated_after_filter(self):
        """Test that no filter is applied when --updated-after is not provided."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        _search_resources(
            mock_client, "domain-123", "project-456", "ASSET"
        )

        call_args = mock_client.search.call_args[1]
        self.assertNotIn("filters", call_args)

    def test_owning_project_filter_applied_for_all_scopes(self):
        """Test owningProjectIdentifier is applied for all search scopes."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        for scope in ["GLOSSARY", "GLOSSARY_TERM", "ASSET", "DATA_PRODUCT"]:
            _search_resources(
                mock_client, "domain-123", "project-456", scope
            )
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

        _search_resources(
            mock_client, "domain-123", "project-456", "GLOSSARY"
        )

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
            _search_resources(
                mock_client, "domain-123", "project-456", "GLOSSARY"
            )
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
        """Test owningProjectIdentifier is passed to SearchTypes API."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        _search_type_resources(
            mock_client, "domain-123", "project-456", "FORM_TYPE"
        )

        call_args = mock_client.search_types.call_args[1]
        self.assertEqual(call_args["owningProjectIdentifier"], "project-456")

    def test_managed_false(self):
        """Test managed=False is set for all SearchTypes queries."""
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        for scope in ["FORM_TYPE", "ASSET_TYPE"]:
            _search_type_resources(
                mock_client, "domain-123", "project-456", scope
            )
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

        _search_type_resources(
            mock_client, "domain-123", "project-456", "FORM_TYPE"
        )

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
                "inputForms": [{"formName": "input-form", "content": "{}"}],
                "externalIdentifier": "arn:aws:glue:us-east-1:123456789:table/db/tbl",
            }
        }

        result = _serialize_resource(resource, "assets")

        self.assertEqual(result["sourceId"], "asset-789")
        self.assertEqual(result["name"], "DataAsset")
        self.assertEqual(result["typeIdentifier"], "CustomAssetType")
        self.assertEqual(result["formsInput"], [{"formName": "metadata"}])
        self.assertEqual(
            result["inputForms"],
            [{"formName": "input-form", "content": "{}"}],
        )
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

    def test_serialize_asset_with_input_forms(self):
        """Test serializing an asset preserves inputForms."""
        resource = {
            "assetItem": {
                "identifier": "asset-1",
                "name": "Asset1",
                "inputForms": [
                    {"formName": "form1", "typeIdentifier": "ft1", "content": '{"key": "val"}'},
                    {"formName": "form2", "typeIdentifier": "ft2", "content": '{"a": 1}'},
                ],
                "formsOutput": [],
            }
        }

        result = _serialize_resource(resource, "assets")

        self.assertEqual(len(result["inputForms"]), 2)
        self.assertEqual(result["inputForms"][0]["formName"], "form1")

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
            {"items": [{"glossaryTermItem": {"id": "t1", "name": "T1", "termRelations": {}}}]},
            {"items": [{"assetItem": {"identifier": "a1", "name": "A1", "inputForms": []}}]},
            {"items": [{"dataProductItem": {"id": "dp1", "name": "DP1"}}]},
        ]
        mock_client.search_types.side_effect = [
            {"items": [{"formTypeItem": {"revision": "f1", "name": "F1", "owningProjectId": "proj-1"}}]},
            {"items": [{"assetTypeItem": {"revision": "at1", "name": "AT1", "owningProjectId": "proj-1"}}]},
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
            "metadata", "glossaries", "glossaryTerms",
            "formTypes", "assetTypes", "assets", "dataProducts",
        }
        self.assertEqual(set(result.keys()), expected_keys)

        metadata = result["metadata"]
        self.assertEqual(metadata["sourceProjectId"], "proj-1")
        self.assertEqual(metadata["sourceDomainId"], "domain-1")
        self.assertIn("exportTimestamp", metadata)
        self.assertEqual(
            set(metadata["resourceTypes"]),
            {"glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"},
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
        """Test owningProjectIdentifier is applied to ALL search queries."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog("domain-1", "proj-1", "us-east-1")

        for call in mock_client.search.call_args_list:
            self.assertEqual(
                call[1]["owningProjectIdentifier"], "proj-1",
                f"owningProjectIdentifier missing for search call: {call}",
            )
        for call in mock_client.search_types.call_args_list:
            self.assertEqual(
                call[1]["owningProjectIdentifier"], "proj-1",
                f"owningProjectIdentifier missing for search_types call: {call}",
            )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_updated_after_filter_applied_to_all_types(self, mock_get_client):
        """Test --updated-after CLI flag filter is applied uniformly to ALL resource types."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        export_catalog(
            "domain-1", "proj-1", "us-east-1",
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
            {"items": [
                {
                    "assetItem": {
                        "identifier": "a1",
                        "name": "Asset1",
                        "externalIdentifier": "arn:aws:glue:us-east-1:123:table/db/tbl",
                        "formsOutput": [],
                        "inputForms": [],
                    }
                }
            ]},  # assets
            {"items": []},  # dataProducts
        ]
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertEqual(
            result["assets"][0]["externalIdentifier"],
            "arn:aws:glue:us-east-1:123:table/db/tbl",
        )

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_input_forms_exported_for_assets(self, mock_get_client):
        """Test inputForms field is exported for assets."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = [
            {"items": []},  # glossaries
            {"items": []},  # glossaryTerms
            {"items": [
                {
                    "assetItem": {
                        "identifier": "a1",
                        "name": "Asset1",
                        "formsOutput": [],
                        "inputForms": [
                            {"formName": "form1", "typeIdentifier": "ft1", "content": "{}"},
                        ],
                    }
                }
            ]},  # assets
            {"items": []},  # dataProducts
        ]
        mock_client.search_types.return_value = {"items": []}

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        self.assertIn("inputForms", result["assets"][0])
        self.assertEqual(len(result["assets"][0]["inputForms"]), 1)
        self.assertEqual(result["assets"][0]["inputForms"][0]["formName"], "form1")

    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_term_relations_exported_for_glossary_terms(self, mock_get_client):
        """Test termRelations field is exported for glossary terms."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = [
            {"items": []},  # glossaries
            {"items": [
                {
                    "glossaryTermItem": {
                        "id": "t1",
                        "name": "Term1",
                        "termRelations": {"isA": ["t2"], "hasA": ["t3"]},
                    }
                }
            ]},  # glossaryTerms
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


if __name__ == "__main__":
    unittest.main()

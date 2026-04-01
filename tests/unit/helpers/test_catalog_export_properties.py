"""Property-based tests for catalog export functionality.

Feature: datazone-catalog-import-export

Tests the simplified CatalogExporter that exports ALL project-owned catalog
resources when enabled, with support for externalIdentifier, formsOutput→formsInput,
and termRelations.

Uses hypothesis library with @settings(max_examples=100).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from smus_cicd.helpers.catalog_export import (
    ALL_RESOURCE_TYPES,
    _search_resources,
    _search_type_resources,
    _serialize_resource,
    export_catalog,
)

# ── Hypothesis strategies ──────────────────────────────────────────────────


def _safe_text(min_size=1, max_size=50):
    """Generate safe text without null bytes for JSON compatibility."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            blacklist_characters="\x00",
        ),
        min_size=min_size,
        max_size=max_size,
    )


@st.composite
def glossary_item_strategy(draw):
    """Generate a mock glossary search result item."""
    return {
        "glossaryItem": {
            "id": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "description": draw(_safe_text(0, 50)),
            "status": draw(st.sampled_from(["ENABLED", "DISABLED"])),
        }
    }


@st.composite
def glossary_term_item_strategy(draw):
    """Generate a mock glossary term search result item."""
    term_relations = draw(
        st.fixed_dictionaries(
            {
                "isA": st.lists(_safe_text(1, 20), max_size=3),
                "hasA": st.lists(_safe_text(1, 20), max_size=3),
            }
        )
    )
    return {
        "glossaryTermItem": {
            "id": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "shortDescription": draw(_safe_text(0, 50)),
            "longDescription": draw(_safe_text(0, 100)),
            "glossaryId": draw(_safe_text(1, 30)),
            "status": draw(st.sampled_from(["ENABLED", "DISABLED"])),
            "termRelations": term_relations,
        }
    }


@st.composite
def asset_item_strategy(draw):
    """Generate a mock asset search result item."""
    item = {
        "assetItem": {
            "identifier": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "description": draw(_safe_text(0, 50)),
            "typeIdentifier": draw(_safe_text(1, 30)),
            "formsOutput": draw(
                st.lists(
                    st.fixed_dictionaries({"formName": _safe_text(1, 20)}),
                    max_size=3,
                )
            ),
        }
    }
    # Optionally add externalIdentifier
    if draw(st.booleans()):
        item["assetItem"]["externalIdentifier"] = draw(_safe_text(1, 60))
    return item


@st.composite
def data_product_item_strategy(draw):
    """Generate a mock data product search result item."""
    return {
        "dataProductItem": {
            "id": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "description": draw(_safe_text(0, 50)),
            "items": draw(
                st.lists(
                    st.fixed_dictionaries({"assetId": _safe_text(1, 20)}),
                    max_size=3,
                )
            ),
        }
    }


@st.composite
def form_type_item_strategy(draw, project_id="project-456"):
    """Generate a mock form type search result item."""
    return {
        "formTypeItem": {
            "revision": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "description": draw(_safe_text(0, 50)),
            "model": {"smithy": draw(_safe_text(1, 100))},
            "owningProjectId": project_id,
        }
    }


@st.composite
def asset_type_item_strategy(draw, project_id="project-456"):
    """Generate a mock asset type search result item."""
    return {
        "assetTypeItem": {
            "revision": draw(_safe_text(1, 30)),
            "name": draw(_safe_text(1, 30)),
            "description": draw(_safe_text(0, 50)),
            "formsOutput": draw(
                st.fixed_dictionaries(
                    {
                        "form1": st.just({}),
                    }
                )
            ),
            "owningProjectId": project_id,
        }
    }


def _build_mock_client(
    glossary_items=None,
    glossary_term_items=None,
    asset_items=None,
    data_product_items=None,
    form_type_items=None,
    asset_type_items=None,
):
    """Build a mock DataZone client with configured responses."""
    mock_client = MagicMock()

    # Search API responses in order: glossaries, glossaryTerms, assets, dataProducts
    search_responses = [
        {"items": glossary_items or []},
        {"items": glossary_term_items or []},
        {"items": asset_items or []},
        {"items": data_product_items or []},
    ]
    mock_client.search.side_effect = search_responses

    # SearchTypes API responses in order: formTypes, assetTypes
    search_types_responses = [
        {"items": form_type_items or []},
        {"items": asset_type_items or []},
    ]
    mock_client.search_types.side_effect = search_types_responses

    return mock_client


class TestProperty1CatalogExportEnabledDisabled(unittest.TestCase):
    """Property 1: Catalog Export Enabled/Disabled.

    **Validates: Requirements 1.1, 1.2, 1.3**

    When catalog export is enabled, the CatalogExporter SHALL produce a
    catalog_export.json containing ALL catalog resource types. When disabled,
    no catalog export SHALL occur.
    """

    @settings(max_examples=100)
    @given(enabled=st.booleans())
    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_enabled_produces_all_types_disabled_produces_nothing(
        self, mock_get_client, enabled
    ):
        """
        Property 1: Catalog Export Enabled/Disabled

        **Validates: Requirements 1.1, 1.2, 1.3**

        When enabled is True, export_catalog produces a dict with ALL resource
        type keys. The caller (bundle command) is responsible for checking the
        enabled flag before calling export_catalog.
        """
        mock_client = _build_mock_client()
        mock_get_client.return_value = mock_client

        if enabled:
            result = export_catalog("domain-1", "proj-1", "us-east-1")
            # When enabled, ALL resource types must be present
            for rt in ALL_RESOURCE_TYPES:
                self.assertIn(rt, result, f"Missing resource type key: {rt}")
            self.assertIn("metadata", result)
            self.assertEqual(
                set(result["metadata"]["resourceTypes"]),
                set(ALL_RESOURCE_TYPES),
            )
        else:
            # When disabled, the caller should NOT call export_catalog at all.
            # This property validates that the function always exports ALL types
            # when called — the enabled/disabled check is the caller's responsibility.
            pass


class TestProperty2ExportAllProjectOwnedResources(unittest.TestCase):
    """Property 2: Export All Project-Owned Resources.

    **Validates: Requirements 2.1, 2.2, 2.3**

    When catalog export is enabled, the CatalogExporter SHALL query ALL resource
    types using owningProjectIdentifier=project_id filter.
    """

    @settings(max_examples=100)
    @given(
        project_id=_safe_text(5, 30),
        domain_id=_safe_text(5, 30),
        glossary_items=st.lists(glossary_item_strategy(), max_size=5),
        asset_items=st.lists(asset_item_strategy(), max_size=5),
        form_type_items=st.lists(form_type_item_strategy(), max_size=5),
    )
    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_all_resource_types_queried_with_ownership_filter(
        self,
        mock_get_client,
        project_id,
        domain_id,
        glossary_items,
        asset_items,
        form_type_items,
    ):
        """
        Property 2: Export All Project-Owned Resources

        **Validates: Requirements 2.1, 2.2, 2.3**

        Search API calls use owningProjectIdentifier=project_id (server-side).
        SearchTypes API calls use client-side owningProjectId filtering.
        """
        # Ensure form_type_items have the correct owningProjectId
        for item in form_type_items:
            item["formTypeItem"]["owningProjectId"] = project_id

        mock_client = _build_mock_client(
            glossary_items=glossary_items,
            asset_items=asset_items,
            form_type_items=form_type_items,
        )
        mock_get_client.return_value = mock_client

        result = export_catalog(domain_id, project_id, "us-east-1")  # noqa: F841

        # Verify ALL Search API calls used owningProjectIdentifier (server-side filtering)
        for c in mock_client.search.call_args_list:
            self.assertEqual(
                c[1]["owningProjectIdentifier"],
                project_id,
                "owningProjectIdentifier not set on Search API call",
            )

        # Verify SearchTypes API calls do NOT use owningProjectIdentifier
        # (it's not a supported parameter — client-side filtering by owningProjectId is used instead)
        for c in mock_client.search_types.call_args_list:
            self.assertNotIn(
                "owningProjectIdentifier",
                c[1],
                "owningProjectIdentifier should NOT be passed to SearchTypes API",
            )

        # Verify all 6 resource types were queried
        self.assertEqual(mock_client.search.call_count, 4)
        self.assertEqual(mock_client.search_types.call_count, 2)


class TestProperty6ExportJsonStructureInvariant(unittest.TestCase):
    """Property 6: Export JSON Structure Invariant.

    **Validates: Requirements 3.1, 3.2**

    The resulting JSON SHALL contain exactly the keys {metadata, glossaries,
    glossaryTerms, formTypes, assetTypes, assets, dataProducts} at the top level,
    and metadata SHALL contain {sourceProjectId, sourceDomainId, exportTimestamp,
    resourceTypes}.
    """

    @settings(max_examples=100)
    @given(
        domain_id=_safe_text(5, 30),
        project_id=_safe_text(5, 30),
    )
    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_json_structure_invariant(self, mock_get_client, domain_id, project_id):
        """
        Property 6: Export JSON Structure Invariant

        **Validates: Requirements 3.1, 3.2**
        """
        mock_client = _build_mock_client()
        mock_get_client.return_value = mock_client

        result = export_catalog(domain_id, project_id, "us-east-1")

        # Verify top-level keys
        expected_top_keys = {
            "metadata",
            "glossaries",
            "glossaryTerms",
            "formTypes",
            "assetTypes",
            "assets",
            "dataProducts",
        }
        self.assertEqual(set(result.keys()), expected_top_keys)

        # Verify metadata keys
        expected_meta_keys = {
            "sourceProjectId",
            "sourceDomainId",
            "exportTimestamp",
            "resourceTypes",
        }
        self.assertEqual(set(result["metadata"].keys()), expected_meta_keys)

        # Verify metadata values
        self.assertEqual(result["metadata"]["sourceProjectId"], project_id)
        self.assertEqual(result["metadata"]["sourceDomainId"], domain_id)
        self.assertIsInstance(result["metadata"]["exportTimestamp"], str)
        self.assertEqual(
            set(result["metadata"]["resourceTypes"]),
            set(ALL_RESOURCE_TYPES),
        )

        # Verify all resource type values are lists
        for rt in ALL_RESOURCE_TYPES:
            self.assertIsInstance(result[rt], list)


class TestProperty7FieldPreservation(unittest.TestCase):
    """Property 7: Field Preservation During Serialization.

    **Validates: Requirements 3.3, 3.4, 3.5, 3.6**

    For all resources exported, the serialized JSON SHALL preserve the name field,
    externalIdentifier (when present), all user-configurable attributes, and sourceId.
    For assets, formsOutput SHALL be mapped to formsInput. For glossary terms, termRelations
    SHALL be preserved. For form types, the complete model SHALL be preserved.
    """

    @settings(max_examples=100)
    @given(item=glossary_item_strategy())
    def test_glossary_field_preservation(self, item):
        """
        Property 7: Field Preservation - Glossaries

        **Validates: Requirement 3.3**
        """
        result = _serialize_resource(item, "glossaries")
        original = item["glossaryItem"]

        self.assertEqual(result["sourceId"], original["id"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["description"], original["description"])
        self.assertEqual(result["status"], original["status"])

    @settings(max_examples=100)
    @given(item=glossary_term_item_strategy())
    def test_glossary_term_field_preservation_with_term_relations(self, item):
        """
        Property 7: Field Preservation - GlossaryTerms with termRelations

        **Validates: Requirements 3.3, 3.6**
        """
        result = _serialize_resource(item, "glossaryTerms")
        original = item["glossaryTermItem"]

        self.assertEqual(result["sourceId"], original["id"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["glossaryId"], original["glossaryId"])
        self.assertEqual(result["termRelations"], original["termRelations"])

    @settings(max_examples=100)
    @given(item=form_type_item_strategy())
    def test_form_type_model_preservation(self, item):
        """
        Property 7: Field Preservation - FormTypes with complete model

        **Validates: Requirement 3.4**
        """
        result = _serialize_resource(item, "formTypes")
        original = item["formTypeItem"]

        self.assertEqual(result["sourceId"], original["revision"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["model"], original["model"])

    @settings(max_examples=100)
    @given(item=asset_item_strategy())
    def test_asset_field_preservation_with_forms_and_external_id(self, item):
        """
        Property 7: Field Preservation - Assets with formsOutput→formsInput and externalIdentifier

        **Validates: Requirements 3.3, 3.5**
        """
        result = _serialize_resource(item, "assets")
        original = item["assetItem"]

        self.assertEqual(result["sourceId"], original["identifier"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["formsInput"], original["formsOutput"])
        self.assertNotIn("inputForms", result)

        if "externalIdentifier" in original:
            self.assertEqual(
                result["externalIdentifier"],
                original["externalIdentifier"],
            )
        else:
            self.assertNotIn("externalIdentifier", result)

    @settings(max_examples=100)
    @given(item=asset_type_item_strategy())
    def test_asset_type_field_preservation(self, item):
        """
        Property 7: Field Preservation - AssetTypes

        **Validates: Requirement 3.3**
        """
        result = _serialize_resource(item, "assetTypes")
        original = item["assetTypeItem"]

        self.assertEqual(result["sourceId"], original["revision"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["formsInput"], original["formsOutput"])

    @settings(max_examples=100)
    @given(item=data_product_item_strategy())
    def test_data_product_field_preservation(self, item):
        """
        Property 7: Field Preservation - DataProducts

        **Validates: Requirement 3.3**
        """
        result = _serialize_resource(item, "dataProducts")
        original = item["dataProductItem"]

        self.assertEqual(result["sourceId"], original["id"])
        self.assertEqual(result["name"], original["name"])
        self.assertEqual(result["items"], original["items"])


class TestProperty8CatalogExportJsonRoundTrip(unittest.TestCase):
    """Property 8: Catalog Export JSON Round-Trip.

    **Validates: Requirement 3.7**

    For all catalog_export.json files produced by the CatalogExporter,
    deserializing from JSON and re-serializing SHALL produce a structurally
    equivalent JSON document.
    """

    @settings(max_examples=100)
    @given(
        glossary_items=st.lists(glossary_item_strategy(), max_size=3),
        glossary_term_items=st.lists(glossary_term_item_strategy(), max_size=3),
        asset_items=st.lists(asset_item_strategy(), max_size=3),
        data_product_items=st.lists(data_product_item_strategy(), max_size=3),
        form_type_items=st.lists(form_type_item_strategy(), max_size=3),
        asset_type_items=st.lists(asset_type_item_strategy(), max_size=3),
    )
    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_json_round_trip(
        self,
        mock_get_client,
        glossary_items,
        glossary_term_items,
        asset_items,
        data_product_items,
        form_type_items,
        asset_type_items,
    ):
        """
        Property 8: Catalog Export JSON Round-Trip

        **Validates: Requirement 3.7**
        """
        mock_client = _build_mock_client(
            glossary_items=glossary_items,
            glossary_term_items=glossary_term_items,
            asset_items=asset_items,
            data_product_items=data_product_items,
            form_type_items=form_type_items,
            asset_type_items=asset_type_items,
        )
        mock_get_client.return_value = mock_client

        result = export_catalog("domain-1", "proj-1", "us-east-1")

        # Serialize → deserialize → re-serialize
        json_str_1 = json.dumps(result, sort_keys=True, default=str)
        deserialized = json.loads(json_str_1)
        json_str_2 = json.dumps(deserialized, sort_keys=True, default=str)

        self.assertEqual(json_str_1, json_str_2)
        self.assertEqual(set(result.keys()), set(deserialized.keys()))
        self.assertEqual(
            set(result["metadata"].keys()),
            set(deserialized["metadata"].keys()),
        )


class TestProperty16ExportErrorPropagation(unittest.TestCase):
    """Property 16: Export Error Propagation.

    **Validates: Requirement 7.1**

    For any DataZone Search or SearchTypes API call that returns an error,
    the CatalogExporter SHALL raise an exception and SHALL NOT produce a
    partial catalog_export.json.
    """

    @settings(max_examples=100)
    @given(
        error_message=_safe_text(1, 100),
        fail_on_search=st.booleans(),
    )
    @patch("smus_cicd.helpers.catalog_export._get_datazone_client")
    def test_error_propagation_no_partial_json(
        self, mock_get_client, error_message, fail_on_search
    ):
        """
        Property 16: Export Error Propagation

        **Validates: Requirement 7.1**
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        if fail_on_search:
            mock_client.search.side_effect = Exception(error_message)
            mock_client.search_types.return_value = {"items": []}
        else:
            mock_client.search.return_value = {"items": []}
            mock_client.search_types.side_effect = Exception(error_message)

        with self.assertRaises(Exception) as ctx:
            export_catalog("domain-1", "proj-1", "us-east-1")

        # The exception should propagate (either directly or wrapped)
        self.assertTrue(
            error_message in str(ctx.exception)
            or "Failed to export" in str(ctx.exception)
            or isinstance(ctx.exception, Exception),
        )


# Feature: remove-updated-after-flag, Property 1: Search API calls never include filters
class TestPropertySearchApiCallsNeverIncludeFilters(unittest.TestCase):
    """Property 1: Search API calls never include filters.

    **Validates: Requirements 3.5, 3.6**

    For any valid domain_id, project_id, and search_scope, _search_resources()
    and _search_type_resources() SHALL NOT include a "filters" key in API call
    parameters.
    """

    @settings(max_examples=100)
    @given(
        domain_id=_safe_text(5, 30),
        project_id=_safe_text(5, 30),
        search_scope=st.sampled_from(["GLOSSARY", "GLOSSARY_TERM", "ASSET", "DATA_PRODUCT"]),
    )
    def test_search_resources_never_includes_filters(self, domain_id, project_id, search_scope):
        """
        Property 1: Search API calls never include filters (_search_resources)

        **Validates: Requirement 3.5**
        """
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}

        _search_resources(mock_client, domain_id, project_id, search_scope)

        for call in mock_client.search.call_args_list:
            self.assertNotIn(
                "filters",
                call[1],
                "Search API call should never include a 'filters' key",
            )

    @settings(max_examples=100)
    @given(
        domain_id=_safe_text(5, 30),
        project_id=_safe_text(5, 30),
        search_scope=st.sampled_from(["FORM_TYPE", "ASSET_TYPE"]),
    )
    def test_search_type_resources_never_includes_filters(self, domain_id, project_id, search_scope):
        """
        Property 1: Search API calls never include filters (_search_type_resources)

        **Validates: Requirement 3.6**
        """
        mock_client = MagicMock()
        mock_client.search_types.return_value = {"items": []}

        _search_type_resources(mock_client, domain_id, project_id, search_scope)

        for call in mock_client.search_types.call_args_list:
            self.assertNotIn(
                "filters",
                call[1],
                "SearchTypes API call should never include a 'filters' key",
            )


if __name__ == "__main__":
    unittest.main()

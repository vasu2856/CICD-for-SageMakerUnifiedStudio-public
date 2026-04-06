"""Property-based tests for catalog import functionality.

Feature: datazone-catalog-import-export
"""

import unittest
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from smus_cicd.helpers.catalog_import import (
    CREATION_ORDER,
    REQUIRED_TOP_LEVEL_KEYS,
    _build_identifier_map,
    _normalize_external_identifier,
    _resolve_cross_references,
    _validate_catalog_json,
    import_catalog,
)

# --- Strategies ---


@st.composite
def resource_name_strategy(draw):
    """Generate a valid resource name."""
    return draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        )
    )


@st.composite
def aws_account_id_strategy(draw):
    """Generate a 12-digit AWS account ID."""
    return draw(st.from_regex(r"\d{12}", fullmatch=True))


@st.composite
def aws_region_strategy(draw):
    """Generate a valid AWS region string."""
    return draw(
        st.sampled_from(
            [
                "us-east-1",
                "us-west-2",
                "eu-west-1",
                "ap-southeast-1",
                "sa-east-1",
                "ca-central-1",
                "me-south-1",
            ]
        )
    )


@st.composite
def external_identifier_strategy(draw):
    """Generate an externalIdentifier that may contain AWS account/region info."""
    account = draw(aws_account_id_strategy())
    region = draw(aws_region_strategy())
    resource_name = draw(resource_name_strategy())
    pattern = draw(
        st.sampled_from(
            [
                f"arn:aws:s3:{region}:{account}:bucket/{resource_name}",
                f"resource-{account}-{region}-{resource_name}",
                f"{resource_name}",  # no AWS info
            ]
        )
    )
    return pattern


@st.composite
def catalog_resource_strategy(draw, resource_type):
    """Generate a catalog resource of the given type."""
    name = draw(resource_name_strategy())
    source_id = f"source-{draw(st.integers(min_value=1, max_value=10000))}"

    if resource_type == "glossaries":
        return {
            "sourceId": source_id,
            "name": name,
            "description": "desc",
            "status": "ENABLED",
        }
    elif resource_type == "glossaryTerms":
        return {
            "sourceId": source_id,
            "name": name,
            "shortDescription": "short",
            "longDescription": "long",
            "glossaryId": f"glossary-{draw(st.integers(min_value=1, max_value=100))}",
            "status": "ENABLED",
            "termRelations": {},
        }
    elif resource_type == "formTypes":
        return {"sourceId": source_id, "name": name, "description": "desc", "model": {}}
    elif resource_type == "assetTypes":
        return {
            "sourceId": source_id,
            "name": name,
            "description": "desc",
            "formsInput": {},
        }
    elif resource_type == "assets":
        return {
            "sourceId": source_id,
            "name": name,
            "description": "desc",
            "typeIdentifier": f"type-{draw(st.integers(min_value=1, max_value=100))}",
            "formsInput": [],
        }
    elif resource_type == "dataProducts":
        return {"sourceId": source_id, "name": name, "description": "desc", "items": []}
    return {}


@st.composite
def catalog_data_strategy(draw):
    """Generate valid catalog data."""
    return {
        "metadata": {
            "sourceProjectId": "source-project",
            "sourceDomainId": "source-domain",
            "exportTimestamp": "2025-01-01T00:00:00Z",
            "resourceTypes": list(CREATION_ORDER),
        },
        "glossaries": draw(
            st.lists(catalog_resource_strategy("glossaries"), max_size=3)
        ),
        "glossaryTerms": draw(
            st.lists(catalog_resource_strategy("glossaryTerms"), max_size=3)
        ),
        "formTypes": draw(st.lists(catalog_resource_strategy("formTypes"), max_size=3)),
        "assetTypes": draw(
            st.lists(catalog_resource_strategy("assetTypes"), max_size=3)
        ),
        "assets": draw(st.lists(catalog_resource_strategy("assets"), max_size=3)),
        "dataProducts": draw(
            st.lists(catalog_resource_strategy("dataProducts"), max_size=3)
        ),
    }


class TestProperty9ExternalIdentifierMapping(unittest.TestCase):
    """
    Property 9: ExternalIdentifier-Based Identifier Mapping with Normalization

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

    For all resources R in the catalog_export.json:
    - IF R has an externalIdentifier, normalize it and use for matching
    - IF a match exists in target, map sourceId to target ID
    - IF R has no externalIdentifier, use name for matching
    - IF no match, mark for creation (not in id_map)
    """

    @settings(max_examples=100)
    @given(
        ext_id=external_identifier_strategy(),
        resource_name=resource_name_strategy(),
    )
    def test_external_identifier_normalization_removes_aws_info(
        self, ext_id, resource_name
    ):
        """Normalized externalIdentifier should not contain 12-digit account IDs or region strings."""
        normalized = _normalize_external_identifier(ext_id)
        # Should not contain any 12-digit number
        import re

        account_matches = re.findall(r"\b\d{12}\b", normalized)
        self.assertEqual(
            len(account_matches),
            0,
            f"Normalized ID still contains account ID: {normalized}",
        )

    @settings(max_examples=100)
    @given(
        account=aws_account_id_strategy(),
        region=aws_region_strategy(),
        resource_name=resource_name_strategy(),
    )
    def test_same_resource_different_accounts_normalize_equal(
        self, account, region, resource_name
    ):
        """Two externalIdentifiers for the same resource in different accounts should normalize to the same value."""
        ext_id_1 = f"arn:aws:s3:{region}:{account}:bucket/{resource_name}"
        ext_id_2 = f"arn:aws:s3:{region}:999888777666:bucket/{resource_name}"
        norm_1 = _normalize_external_identifier(ext_id_1)
        norm_2 = _normalize_external_identifier(ext_id_2)
        self.assertEqual(norm_1, norm_2)

    @settings(max_examples=100)
    @given(resource_name=resource_name_strategy())
    def test_name_fallback_when_no_external_id(self, resource_name):
        """When no externalIdentifier, name-based matching should be used."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "items": [{"glossaryItem": {"id": "target-g1", "name": resource_name}}]
        }
        mock_client.search_types.return_value = {"items": []}

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": [],
            },
            "glossaries": [{"sourceId": "src-g1", "name": resource_name}],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }

        id_map = _build_identifier_map(mock_client, "d1", "p1", catalog_data)
        # Should map by name
        self.assertEqual(id_map["glossaries"]["src-g1"], "target-g1")

    @settings(max_examples=100)
    @given(resource_name=resource_name_strategy())
    def test_no_match_means_creation(self, resource_name):
        """When no match in target, resource should not be in id_map (marked for creation)."""
        mock_client = MagicMock()
        mock_client.search.return_value = {"items": []}
        mock_client.search_types.return_value = {"items": []}

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": [],
            },
            "glossaries": [{"sourceId": "src-g1", "name": resource_name}],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }

        id_map = _build_identifier_map(mock_client, "d1", "p1", catalog_data)
        self.assertNotIn("src-g1", id_map["glossaries"])


class TestProperty10CrossReferenceResolution(unittest.TestCase):
    """
    Property 10: Cross-Reference Resolution

    **Validates: Requirement 4.6**

    For all resources R that contain cross-resource references, the CatalogImporter
    SHALL replace every source identifier with the corresponding target identifier.
    """

    @settings(max_examples=100)
    @given(
        source_glossary_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        target_glossary_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
    )
    def test_glossary_term_glossary_id_resolved(
        self, source_glossary_id, target_glossary_id
    ):
        """GlossaryTerm.glossaryId should be replaced with target glossary ID."""
        term = {"sourceId": "t1", "name": "Term1", "glossaryId": source_glossary_id}
        id_map = {
            "glossaries": {source_glossary_id: target_glossary_id},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(term, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], target_glossary_id)

    @settings(max_examples=100)
    @given(
        source_type_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        target_type_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
    )
    def test_asset_type_identifier_resolved(self, source_type_id, target_type_id):
        """Asset.typeIdentifier should be replaced with target asset type ID."""
        asset = {"sourceId": "a1", "name": "Asset1", "typeIdentifier": source_type_id}
        id_map = {
            "glossaries": {},
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {source_type_id: target_type_id},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(asset, "assets", id_map)
        self.assertEqual(resolved["typeIdentifier"], target_type_id)

    @settings(max_examples=100)
    @given(
        source_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
    )
    def test_unmapped_reference_preserved(self, source_id):
        """When no mapping exists, original reference should be preserved."""
        term = {"sourceId": "t1", "name": "Term1", "glossaryId": source_id}
        id_map = {
            "glossaries": {},  # No mapping
            "glossaryTerms": {},
            "formTypes": {},
            "assetTypes": {},
            "assets": {},
            "dataProducts": {},
        }
        resolved = _resolve_cross_references(term, "glossaryTerms", id_map)
        self.assertEqual(resolved["glossaryId"], source_id)


class TestProperty11DependencyOrderedCreation(unittest.TestCase):
    """
    Property 11: Dependency-Ordered Creation

    **Validates: Requirement 5.6**

    The CatalogImporter SHALL create resources in dependency order:
    Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → DataProducts
    """

    @settings(max_examples=100)
    @given(catalog_data=catalog_data_strategy())
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_creation_order_respected(self, mock_get_client, catalog_data):
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        call_order = []
        client.create_glossary.side_effect = lambda **kw: (
            call_order.append("glossaries"),
            {"id": "g"},
        )[1]
        client.create_glossary_term.side_effect = lambda **kw: (
            call_order.append("glossaryTerms"),
            {"id": "t"},
        )[1]
        client.create_form_type.side_effect = lambda **kw: (
            call_order.append("formTypes"),
            {"revision": "ft"},
        )[1]
        client.create_asset_type.side_effect = lambda **kw: (
            call_order.append("assetTypes"),
            {"revision": "at"},
        )[1]
        client.create_asset.side_effect = lambda **kw: (
            call_order.append("assets"),
            {"id": "a"},
        )[1]
        client.create_data_product.side_effect = lambda **kw: (
            call_order.append("dataProducts"),
            {"id": "dp"},
        )[1]

        import_catalog("d1", "p1", catalog_data, "us-east-1")

        # Verify: for any two resource types, the one earlier in CREATION_ORDER
        # should have all its entries before the later one's first entry
        for i, rt_early in enumerate(CREATION_ORDER):
            for rt_late in CREATION_ORDER[i + 1 :]:
                early_indices = [j for j, t in enumerate(call_order) if t == rt_early]
                late_indices = [j for j, t in enumerate(call_order) if t == rt_late]
                if early_indices and late_indices:
                    self.assertLess(
                        max(early_indices),
                        min(late_indices),
                        f"All {rt_early} must be created before any {rt_late}",
                    )


class TestProperty12ExtraResourcesNotDeleted(unittest.TestCase):
    """
    Property 12: Extra Resources Are Logged, Not Deleted

    **Validates: Updated Requirement 5.4**

    The CatalogImporter SHALL NOT delete resources that exist in the target
    project but are not present in the bundle. Instead, they are logged and
    counted as skipped.
    """

    @settings(max_examples=100)
    @given(
        has_glossary=st.booleans(),
        has_term=st.booleans(),
        has_asset=st.booleans(),
    )
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_extra_resources_skipped_not_deleted(
        self, mock_get_client, has_glossary, has_term, has_asset
    ):
        client = MagicMock()
        mock_get_client.return_value = client

        # Empty bundle means everything in target is extra
        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": list(CREATION_ORDER),
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }

        def search_side_effect(**kwargs):
            scope = kwargs.get("searchScope")
            if scope == "GLOSSARY" and has_glossary:
                return {"items": [{"glossaryItem": {"id": "g1", "name": "G1"}}]}
            if scope == "GLOSSARY_TERM" and has_term:
                return {"items": [{"glossaryTermItem": {"id": "t1", "name": "T1"}}]}
            if scope == "ASSET" and has_asset:
                return {"items": [{"assetItem": {"identifier": "a1", "name": "A1"}}]}
            return {"items": []}

        client.search.side_effect = search_side_effect
        client.search_types.return_value = {"items": []}

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        # No delete APIs should ever be called
        client.delete_glossary.assert_not_called()
        client.delete_glossary_term.assert_not_called()
        client.delete_asset.assert_not_called()
        client.delete_asset_type.assert_not_called()
        client.delete_form_type.assert_not_called()
        client.delete_data_product.assert_not_called()

        # Extra resources should be counted as skipped
        expected_skipped = sum([has_glossary, has_term, has_asset])
        self.assertEqual(result["skipped"], expected_skipped)


class TestProperty13ImportErrorResilience(unittest.TestCase):
    """
    Property 13: Import Error Resilience

    **Validates: Requirements 5.10, 5.14, 7.3**

    For any import where K out of N resources fail, the CatalogImporter SHALL still
    attempt all N resources and report K failures.
    """

    @settings(max_examples=100)
    @given(
        num_resources=st.integers(min_value=1, max_value=8),
        num_failures=st.integers(min_value=0, max_value=8),
    )
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_all_resources_attempted_despite_failures(
        self, mock_get_client, num_resources, num_failures
    ):
        num_failures = min(num_failures, num_resources)
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        call_count = [0]

        def create_with_failures(**kwargs):
            call_count[0] += 1
            if call_count[0] <= num_failures:
                raise Exception("API Error")
            return {"id": f"g-{call_count[0]}"}

        client.create_glossary.side_effect = create_with_failures

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": ["glossaries"],
            },
            "glossaries": [
                {"sourceId": f"g{i}", "name": f"G{i}", "status": "ENABLED"}
                for i in range(num_resources)
            ],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        # All resources were attempted
        self.assertEqual(call_count[0], num_resources)
        self.assertEqual(result["failed"], num_failures)
        self.assertEqual(result["created"], num_resources - num_failures)


class TestProperty14ImportSummaryCounts(unittest.TestCase):
    """
    Property 14: Import Summary Counts

    **Validates: Requirements 5.12, 6.3**

    created + updated + deleted + failed = total processed.
    published count = number of successfully published assets/data products.
    """

    @settings(max_examples=100)
    @given(catalog_data=catalog_data_strategy())
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_summary_counts_add_up(self, mock_get_client, catalog_data):
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        # Deterministic success/failure based on resource name hash
        def make_create_side_effect(id_key):
            def side_effect(**kwargs):
                name = kwargs.get("name", "")
                if hash(name) % 4 == 0:
                    raise Exception("API Error")
                return {id_key: f"new-{name}"}

            return side_effect

        client.create_glossary.side_effect = make_create_side_effect("id")
        client.create_glossary_term.side_effect = make_create_side_effect("id")
        client.create_form_type.side_effect = make_create_side_effect("revision")
        client.create_asset_type.side_effect = make_create_side_effect("revision")
        client.create_asset.side_effect = make_create_side_effect("id")
        client.create_data_product.side_effect = make_create_side_effect("id")

        total_in_bundle = sum(len(catalog_data.get(rt, [])) for rt in CREATION_ORDER)

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        # created + updated + failed = total resources in bundle
        self.assertEqual(
            result["created"] + result["updated"] + result["failed"],
            total_in_bundle,
        )
        # skipped is separate (extra resources in target, not in bundle)
        self.assertGreaterEqual(result["skipped"], 0)
        # All counts are non-negative
        self.assertGreaterEqual(result["created"], 0)
        self.assertGreaterEqual(result["updated"], 0)
        self.assertGreaterEqual(result["failed"], 0)
        self.assertGreaterEqual(result["published"], 0)


class TestProperty15AutomaticPublishing(unittest.TestCase):
    """
    Property 15: Automatic Publishing Based on Source State

    **Validates: Requirement 5.13**

    When skip_publish=False, the CatalogImporter SHALL invoke publish API only for
    assets and data products that had listingStatus=LISTED in the source.
    When skip_publish=True, no publish API calls should be made.
    """

    @settings(max_examples=100)
    @given(
        num_assets=st.integers(min_value=0, max_value=5),
        num_data_products=st.integers(min_value=0, max_value=5),
    )
    @patch("smus_cicd.helpers.catalog_import.time.sleep", return_value=None)
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_publish_called_for_listed_resources(
        self, mock_get_client, mock_sleep, num_assets, num_data_products
    ):
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}

        # All creates succeed
        client.create_asset.side_effect = lambda **kw: {"id": f"a-{kw.get('name')}"}
        client.create_data_product.side_effect = lambda **kw: {
            "id": f"dp-{kw.get('name')}"
        }
        # Publish verification returns ACTIVE
        client.get_asset.return_value = {"listing": {"listingStatus": "ACTIVE"}}
        client.get_data_product.return_value = {"listing": {"listingStatus": "ACTIVE"}}

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": ["assets", "dataProducts"],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [
                {
                    "sourceId": f"a{i}",
                    "name": f"Asset{i}",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "listingStatus": "ACTIVE",
                }
                for i in range(num_assets)
            ],
            "dataProducts": [
                {
                    "sourceId": f"dp{i}",
                    "name": f"DP{i}",
                    "items": [],
                    "listingStatus": "ACTIVE",
                }
                for i in range(num_data_products)
            ],
        }

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        expected_publish_calls = num_assets + num_data_products
        self.assertEqual(
            client.create_listing_change_set.call_count, expected_publish_calls
        )
        self.assertEqual(result["published"], expected_publish_calls)

    @settings(max_examples=100)
    @given(num_assets=st.integers(min_value=1, max_value=5))
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_no_publish_when_skip_publish(self, mock_get_client, num_assets):
        """When skip_publish=True, no publish API calls should be made."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.side_effect = lambda **kw: {"id": f"a-{kw.get('name')}"}

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": ["assets"],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [
                {
                    "sourceId": f"a{i}",
                    "name": f"Asset{i}",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                    "listingStatus": "ACTIVE",
                }
                for i in range(num_assets)
            ],
            "dataProducts": [],
        }

        result = import_catalog(
            "d1", "p1", catalog_data, "us-east-1", skip_publish=True
        )

        client.create_listing_change_set.assert_not_called()
        self.assertEqual(result["published"], 0)

    @settings(max_examples=100)
    @given(num_assets=st.integers(min_value=1, max_value=5))
    @patch("smus_cicd.helpers.catalog_import._get_datazone_client")
    def test_no_publish_when_source_not_listed(self, mock_get_client, num_assets):
        """When source assets have no listingStatus, no publish API calls should be made."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.search.return_value = {"items": []}
        client.search_types.return_value = {"items": []}
        client.create_asset.side_effect = lambda **kw: {"id": f"a-{kw.get('name')}"}

        catalog_data = {
            "metadata": {
                "sourceProjectId": "sp",
                "sourceDomainId": "sd",
                "exportTimestamp": "t",
                "resourceTypes": ["assets"],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [
                {
                    "sourceId": f"a{i}",
                    "name": f"Asset{i}",
                    "typeIdentifier": "t1",
                    "formsInput": [],
                }
                for i in range(num_assets)
            ],
            "dataProducts": [],
        }

        result = import_catalog("d1", "p1", catalog_data, "us-east-1")

        client.create_listing_change_set.assert_not_called()
        self.assertEqual(result["published"], 0)


class TestProperty17MalformedJsonValidation(unittest.TestCase):
    """
    Property 17: Malformed JSON Validation

    **Validates: Requirement 7.4**

    For all JSON inputs missing required top-level keys or metadata keys,
    the CatalogImporter SHALL raise a validation error before any API calls.
    """

    @settings(max_examples=100)
    @given(missing_key=st.sampled_from(list(REQUIRED_TOP_LEVEL_KEYS)))
    def test_missing_top_level_key_raises(self, missing_key):
        """Missing any required top-level key should raise ValueError."""
        catalog_data = {
            "metadata": {
                "sourceProjectId": "p",
                "sourceDomainId": "d",
                "exportTimestamp": "t",
                "resourceTypes": [],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        del catalog_data[missing_key]

        with self.assertRaises(ValueError):
            _validate_catalog_json(catalog_data)

    @settings(max_examples=100)
    @given(
        missing_key=st.sampled_from(
            ["sourceProjectId", "sourceDomainId", "exportTimestamp", "resourceTypes"]
        )
    )
    def test_missing_metadata_key_raises(self, missing_key):
        """Missing any required metadata key should raise ValueError."""
        catalog_data = {
            "metadata": {
                "sourceProjectId": "p",
                "sourceDomainId": "d",
                "exportTimestamp": "t",
                "resourceTypes": [],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        del catalog_data["metadata"][missing_key]

        with self.assertRaises(ValueError):
            _validate_catalog_json(catalog_data)

    @settings(max_examples=100)
    @given(missing_key=st.sampled_from(list(REQUIRED_TOP_LEVEL_KEYS)))
    def test_import_catalog_rejects_before_api_calls(self, missing_key):
        """import_catalog should raise before making any API calls."""
        catalog_data = {
            "metadata": {
                "sourceProjectId": "p",
                "sourceDomainId": "d",
                "exportTimestamp": "t",
                "resourceTypes": [],
            },
            "glossaries": [],
            "glossaryTerms": [],
            "formTypes": [],
            "assetTypes": [],
            "assets": [],
            "dataProducts": [],
        }
        del catalog_data[missing_key]

        with self.assertRaises(ValueError):
            import_catalog("d1", "p1", catalog_data, "us-east-1")


if __name__ == "__main__":
    unittest.main()

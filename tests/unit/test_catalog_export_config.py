"""Unit tests for simplified catalog export configuration parsing.

Tests the manifest content.catalog section which ONLY supports:
- enabled (boolean): Enable/disable catalog export
- skipPublish (boolean): Skip publishing assets/data products during deploy (default: false)
- connectionName (string): Connection name for catalog access
- assets.access (array): Subscription/access requests

NO filter fields (include, names, assetTypes, updatedAfter, etc.) are supported.
"""

import unittest

from smus_cicd.application.application_manifest import (
    ApplicationManifest,
    CatalogAssetsConfig,
    CatalogConfig,
)


def _make_manifest_data(catalog_data=None):
    """Helper to create minimal manifest data with optional catalog config."""
    data = {
        "applicationName": "test-app",
        "content": {},
        "stages": {
            "dev": {
                "domain": {"region": "us-east-1"},
                "project": {"name": "test-project"},
                "stage": "DEV",
            }
        },
    }
    if catalog_data is not None:
        data["content"]["catalog"] = catalog_data
    return data


class TestSimplifiedCatalogConfig(unittest.TestCase):
    """Test simplified catalog configuration parsing."""

    # --- enabled field tests ---

    def test_parse_catalog_enabled_true(self):
        """Test parsing with enabled: true exports all catalog resources."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({"enabled": True}))
        self.assertIsNotNone(manifest.content.catalog)
        self.assertTrue(manifest.content.catalog.enabled)

    def test_parse_catalog_enabled_false(self):
        """Test parsing with enabled: false disables catalog export."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data({"enabled": False})
        )
        self.assertIsNotNone(manifest.content.catalog)
        self.assertFalse(manifest.content.catalog.enabled)

    def test_parse_catalog_enabled_omitted_defaults_false(self):
        """Test that enabled defaults to false when omitted."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({}))
        self.assertIsNotNone(manifest.content.catalog)
        self.assertFalse(manifest.content.catalog.enabled)

    def test_parse_catalog_section_omitted(self):
        """Test that catalog is None when entire section is omitted."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data())
        self.assertIsNone(manifest.content.catalog)

    # --- publish field tests ---

    def test_parse_catalog_skip_publish_true(self):
        """Test parsing with skipPublish: true to skip publishing."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data({"enabled": True, "skipPublish": True})
        )
        self.assertTrue(manifest.content.catalog.skipPublish)

    def test_parse_catalog_skip_publish_false(self):
        """Test parsing with skipPublish: false (publish based on source state)."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data({"enabled": True, "skipPublish": False})
        )
        self.assertFalse(manifest.content.catalog.skipPublish)

    def test_parse_catalog_skip_publish_omitted_defaults_false(self):
        """Test that skipPublish defaults to false when omitted."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({"enabled": True}))
        self.assertFalse(manifest.content.catalog.skipPublish)

    # --- connectionName field tests ---

    def test_parse_catalog_with_connection_name(self):
        """Test parsing with connectionName."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data({"connectionName": "default.domain"})
        )
        self.assertEqual(manifest.content.catalog.connectionName, "default.domain")

    def test_parse_catalog_connection_name_omitted(self):
        """Test that connectionName defaults to None when omitted."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({"enabled": True}))
        self.assertIsNone(manifest.content.catalog.connectionName)

    # --- assets.access tests (subscription requests) ---

    def test_parse_catalog_assets_access_with_search(self):
        """Test parsing assets.access array with search selector."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "enabled": True,
                    "assets": {
                        "access": [
                            {
                                "selector": {
                                    "search": {
                                        "assetType": "GlueTable",
                                        "identifier": "covid19_db.countries_aggregated",
                                    }
                                },
                                "permission": "READ",
                                "requestReason": "Required for analytics pipeline",
                            }
                        ]
                    },
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertIsNotNone(catalog.assets)
        self.assertIsNotNone(catalog.assets.access)
        self.assertEqual(len(catalog.assets.access), 1)

        access = catalog.assets.access[0]
        self.assertEqual(access.selector.search.assetType, "GlueTable")
        self.assertEqual(
            access.selector.search.identifier, "covid19_db.countries_aggregated"
        )
        self.assertEqual(access.permission, "READ")
        self.assertEqual(access.requestReason, "Required for analytics pipeline")

    def test_parse_catalog_assets_access_with_asset_id(self):
        """Test parsing assets.access with direct assetId selector."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "assets": {
                        "access": [
                            {
                                "selector": {"assetId": "asset-123"},
                                "permission": "WRITE",
                            }
                        ]
                    }
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertEqual(len(catalog.assets.access), 1)
        self.assertEqual(catalog.assets.access[0].selector.assetId, "asset-123")
        self.assertEqual(catalog.assets.access[0].permission, "WRITE")

    def test_parse_catalog_assets_access_multiple(self):
        """Test parsing multiple access requests."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "assets": {
                        "access": [
                            {
                                "selector": {"assetId": "asset-1"},
                                "permission": "READ",
                            },
                            {
                                "selector": {"assetId": "asset-2"},
                                "permission": "WRITE",
                            },
                        ]
                    }
                }
            )
        )
        self.assertEqual(len(manifest.content.catalog.assets.access), 2)

    def test_parse_catalog_assets_empty_access(self):
        """Test parsing with empty access array."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data({"assets": {"access": []}})
        )
        self.assertIsNotNone(manifest.content.catalog.assets)
        # Empty list results in None access
        self.assertIsNone(manifest.content.catalog.assets.access)

    def test_parse_catalog_no_assets_section(self):
        """Test parsing without assets section."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({"enabled": True}))
        self.assertIsNone(manifest.content.catalog.assets)

    # --- backward compatibility ---

    def test_backward_compatibility_access_assets_property(self):
        """Test backward compatibility property for accessAssets."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "assets": {
                        "access": [
                            {
                                "selector": {"assetId": "asset-123"},
                                "permission": "READ",
                            }
                        ]
                    }
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertEqual(len(catalog.accessAssets), 1)
        self.assertEqual(catalog.accessAssets[0].selector.assetId, "asset-123")

    def test_backward_compatibility_access_assets_empty(self):
        """Test accessAssets returns empty list when no assets configured."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({"enabled": True}))
        self.assertEqual(manifest.content.catalog.accessAssets, [])

    def test_backward_compatibility_old_access_assets_field(self):
        """Test backward compatibility with old accessAssets field location."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "accessAssets": [
                        {
                            "selector": {"assetId": "legacy-asset"},
                            "permission": "READ",
                        }
                    ]
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertEqual(len(catalog.accessAssets), 1)
        self.assertEqual(catalog.accessAssets[0].selector.assetId, "legacy-asset")

    # --- no filter fields accepted ---

    def test_no_filter_fields_in_catalog_config(self):
        """Test that CatalogConfig has no filter-related attributes."""
        config = CatalogConfig()
        self.assertFalse(hasattr(config, "glossaries"))
        self.assertFalse(hasattr(config, "dataProducts"))
        self.assertFalse(hasattr(config, "metadataForms"))
        self.assertFalse(hasattr(config, "updatedAfter"))

    def test_no_filter_fields_in_assets_config(self):
        """Test that CatalogAssetsConfig has no filter-related attributes."""
        config = CatalogAssetsConfig()
        self.assertFalse(hasattr(config, "include"))
        self.assertFalse(hasattr(config, "updatedAfter"))
        self.assertFalse(hasattr(config, "names"))
        self.assertFalse(hasattr(config, "assetTypes"))

    def test_filter_fields_ignored_in_manifest_parsing(self):
        """Test that old filter fields in manifest data are silently ignored."""
        # These old fields should not cause errors but should not be stored
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "enabled": True,
                    "glossaries": {"include": ["glossaries"]},
                    "dataProducts": {"names": ["SomeProduct"]},
                    "metadataForms": {"include": ["formTypes"]},
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertTrue(catalog.enabled)
        # Old filter sections should not exist on the simplified CatalogConfig
        self.assertFalse(hasattr(catalog, "glossaries"))
        self.assertFalse(hasattr(catalog, "dataProducts"))
        self.assertFalse(hasattr(catalog, "metadataForms"))

    # --- full configuration test ---

    def test_parse_full_simplified_catalog_config(self):
        """Test parsing a complete simplified catalog configuration."""
        manifest = ApplicationManifest.from_dict(
            _make_manifest_data(
                {
                    "enabled": True,
                    "skipPublish": False,
                    "connectionName": "default.domain",
                    "assets": {
                        "access": [
                            {
                                "selector": {
                                    "search": {
                                        "assetType": "GlueTable",
                                        "identifier": "db.table",
                                    }
                                },
                                "permission": "READ",
                                "requestReason": "Analytics pipeline",
                            }
                        ]
                    },
                }
            )
        )
        catalog = manifest.content.catalog
        self.assertTrue(catalog.enabled)
        self.assertFalse(catalog.skipPublish)
        self.assertEqual(catalog.connectionName, "default.domain")
        self.assertEqual(len(catalog.assets.access), 1)

    def test_parse_catalog_defaults_only(self):
        """Test that all defaults are correct for minimal catalog config."""
        manifest = ApplicationManifest.from_dict(_make_manifest_data({}))
        catalog = manifest.content.catalog
        self.assertFalse(catalog.enabled)
        self.assertFalse(catalog.skipPublish)
        self.assertIsNone(catalog.connectionName)
        self.assertIsNone(catalog.assets)


if __name__ == "__main__":
    unittest.main()

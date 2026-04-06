# Implementation Plan: DataZone Catalog Import/Export

## Overview

Implement catalog resource export during `bundle` and import during `deploy` by adding new helper modules, extending the manifest schema, and wiring into existing command flows. The simplified approach exports ALL catalog resources when enabled via a boolean flag, uses externalIdentifier (with normalization) or name for mapping, and logs extra resources in the target project for visibility without deleting them. The manifest `content.catalog` section only supports `enabled` (boolean), `skipPublish` (boolean), and `assets.access` (array for subscription requests) — no filter options of any kind. Publishing is source-state-based: assets and data products are published only if they were published (listingStatus == "ACTIVE") in the source project, unless `skipPublish` is set to true. After calling the asynchronous publish API, the importer polls to verify the listing becomes ACTIVE before counting it as published.

## Tasks

- [x] 1. Extend manifest schema and data model for simplified catalog export
  - Update manifest schema to support simple `content.catalog.enabled` boolean flag and optional `skipPublish` boolean. The manifest `content.catalog` section ONLY supports: `enabled`, `skipPublish`, and `assets.access` — no filter options (`include`, `names`, `assetTypes`, etc.) whatsoever.
  - [x] 1.1 Update `CatalogConfig` dataclass in `application_manifest.py`
    - Remove all filter-related classes (`CatalogAssetsConfig`, `CatalogGlossariesConfig`, `CatalogDataProductsConfig`, `CatalogMetadataFormsConfig`) and any filter fields (`include`, `names`, `assetTypes`)
    - Update `CatalogConfig` to have ONLY: `enabled: bool = False`, `skipPublish: bool = False`, `connectionName: Optional[str] = None`, and `assets: Optional[CatalogAssetsConfig] = None` (for subscription requests only)
    - Update `from_dict` parsing to handle simplified structure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 1.2 Update `application-manifest-schema.yaml` with simplified catalog section
    - Replace complex filter configuration with simple `enabled: boolean` field
    - Add `skipPublish: boolean` field (default: false) to skip source-state-based publishing
    - Keep `assets.access` array for subscription requests (unchanged)
    - Remove ALL filter fields: `assets.include`, `glossaries.include`, `dataProducts.names`, `metadataForms.include`, and any other filter-related fields
    - Ensure the `content.catalog` section ONLY supports: `enabled` (boolean), `skipPublish` (boolean), and `assets.access` (array for subscription requests)
    - _Requirements: 1.1, 1.4, 1.5, 1.6_
  - [x] 1.3 Write unit tests for manifest parsing of simplified catalog config
    - Test parsing with `enabled: true`
    - Test parsing with `enabled: false` or omitted
    - Test parsing with `skipPublish: true` and `skipPublish: false`
    - Test parsing with `assets.access` array (subscription requests)
    - Test that no filter fields (`include`, `names`, `assetTypes`) are accepted in the manifest
    - Verify backward compatibility
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 1.4 Document changes in `TASK_1_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `src/smus_cicd/application/application_manifest.py`, `src/smus_cicd/application/application-manifest-schema.yaml`, `tests/unit/test_catalog_export_config.py`

- [x] 2. Implement CatalogExporter helper with simplified export
  - Create CatalogExporter that exports ALL project-owned catalog resources when enabled, with support for externalIdentifier, inputForms, and termRelations.
  - [x] 2.1 Create `src/smus_cicd/helpers/catalog_export.py` with `export_catalog()` function
    - Implement `export_catalog(domain_id, project_id, region)` returning catalog JSON dict
    - Export ALL resource types owned by the project: Glossaries, GlossaryTerms, FormTypes, AssetTypes, Assets, Data Products
    - Apply `owningProjectIdentifier=project_id` filter to Search API queries (Search API supports this parameter)
    - For SearchTypes API, use client-side filtering by `owningProjectId` on response items (SearchTypes API does NOT support `owningProjectIdentifier` parameter)
    - Implement `_search_resources()` for Search API with pagination and `owningProjectIdentifier`
    - Implement `_search_type_resources()` for SearchTypes API with pagination and client-side `owningProjectId` filtering
    - Implement `_enrich_asset_items()` to call `get_asset` per asset to retrieve full details including `formsOutput` (Search API only returns summary data)
    - Implement `_serialize_resource()` to extract name, user-configurable fields, sourceId (using `identifier` or `id` fallback for assets), and externalIdentifier (when present)
    - Export `inputForms` field for assets
    - Export `termRelations` field for glossary terms
    - Use sort by updatedAt DESC for all queries
    - No manifest-based filters are applied
    - _Requirements: 1.2, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11_
  - [x] 2.2 Write unit tests for CatalogExporter
    - Mock DataZone client with boto3 stubber
    - Test API routing per resource type
    - Test owningProjectIdentifier parameter is applied to Search API queries
    - Test SearchTypes API uses client-side owningProjectId filtering (not owningProjectIdentifier parameter)
    - Test `_enrich_asset_items` calls get_asset per asset to retrieve formsOutput
    - Test `_enrich_asset_items` falls back to search data on get_asset failure
    - Test `sourceId` resolution uses `identifier` (Search API) or `id` (GetAsset API) fallback
    - Test pagination handling
    - Test JSON structure output
    - Test externalIdentifier export for assets
    - Test inputForms export for assets
    - Test termRelations export for glossary terms
    - Test error propagation on API failure
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.8_
  - [x] 2.3 Write property test: Catalog export enabled/disabled (Property 1)
    - **Property 1: Catalog Export Enabled/Disabled**
    - **Validates: Requirements 1.1, 1.2, 1.3**
  - [x] 2.4 Write property test: Export all project-owned resources (Property 2)
    - **Property 2: Export All Project-Owned Resources**
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [x] 2.5 Write property test: Export JSON structure invariant (Property 6)
    - **Property 6: Export JSON Structure Invariant**
    - **Validates: Requirements 3.1, 3.2**
  - [x] 2.7 Write property test: Field preservation (Property 7)
    - **Property 7: Field Preservation During Serialization**
    - **Validates: Requirements 3.3, 3.4, 3.5, 3.6**
  - [x] 2.8 Write property test: Catalog export JSON round-trip (Property 8)
    - **Property 8: Catalog Export JSON Round-Trip**
    - **Validates: Requirement 3.7**
  - [x] 2.9 Write property test: Export error propagation (Property 16)
    - **Property 16: Export Error Propagation**
    - **Validates: Requirement 7.1**
  - [x] 2.10 Document changes in `TASK_2_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `src/smus_cicd/helpers/catalog_export.py`, `tests/unit/helpers/test_catalog_export.py`, `tests/unit/helpers/test_catalog_export_properties.py`

- [x] 3. Integrate CatalogExporter into bundle command
  - Wire simplified catalog export into bundle command flow.
  - [x] 3.1 Add catalog export step to `bundle.py`
    - After QuickSight export and before ZIP creation, check `manifest.content.catalog.enabled`
    - If enabled, call `export_catalog()` with domain_id, project_id, and region
    - Write `catalog/catalog_export.json` to temp_bundle_dir
    - Increment total_files_added
    - _Requirements: 1.2, 2.9_
  - [x] 3.2 Write unit test for bundle command catalog export integration
    - Verify catalog_export.json appears in bundle ZIP when enabled
    - Verify it is skipped when disabled or omitted
    - Verify no manifest-based filter values are read or passed
    - _Requirements: 2.9_
  - [x] 3.4 Document changes in `TASK_3_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `src/smus_cicd/commands/bundle.py`, `src/smus_cicd/cli.py`, `tests/unit/test_bundle.py`

- [x] 4. Checkpoint - Ensure all tests pass
  - Verify all unit and property tests pass before proceeding to import implementation.
  - Files Changed: None (checkpoint only)

- [x] 5. Implement CatalogImporter helper with externalIdentifier mapping and automatic publishing
  - Create CatalogImporter that uses externalIdentifier (with normalization) or name for mapping, logs extra resources in target (no deletion), and optionally publishes assets and data products.
  - [x] 5.1 Create `src/smus_cicd/helpers/catalog_import.py` with core import logic
    - Implement `_validate_catalog_json(catalog_data)` to check required keys
    - Implement `_normalize_external_identifier(external_id)` to remove AWS account ID and region
    - Implement `_build_identifier_map(client, domain_id, project_id, catalog_data)` to query target project using normalized externalIdentifier (when present) or name
    - Implement `_resolve_cross_references(resource, resource_type, id_map)` to replace source IDs
    - Implement `_import_resource(client, domain_id, project_id, resource, resource_type, id_map)` to call create or update API
    - Implement `_identify_extra_target_resources(client, domain_id, project_id, catalog_data)` to find resources in target not in bundle (logged, not deleted)
    - Implement `_publish_resource(client, domain_id, resource_id, resource_type)` to call publish API for assets and data products
    - Implement `import_catalog(domain_id, project_id, catalog_data, region, publish=True)` orchestrating validation, mapping, creation, update, logging extras, and optional publishing
    - Creation order: Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → Data Products
    - Extra resources in target are logged for visibility but never deleted
    - When publish=True, publish assets and data products after creation/update
    - Preserve `inputForms` field when importing assets
    - Preserve `termRelations` field when importing glossary terms
    - Log errors per resource, continue processing, return `{created, updated, skipped, failed, published}` summary
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.6, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 7.3, 7.4_
  - [x] 5.2 Write unit tests for CatalogImporter
    - Mock DataZone client with boto3 stubber
    - Test externalIdentifier-based mapping with normalization
    - Test name-based mapping fallback
    - Test cross-reference resolution
    - Test dependency ordering for creation
    - Test extra resources in target are logged but not deleted
    - Test automatic publishing when publish=True
    - Test publish API is not called when publish=False
    - Test error resilience (including publish failures)
    - Test ConflictException handling
    - Test JSON validation
    - Test identification of extra resources in target
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 5.3, 5.4, 5.6, 5.10, 5.13, 5.14, 7.4_
  - [x] 5.3 Write property test: ExternalIdentifier-based identifier mapping with normalization (Property 9)
    - **Property 9: ExternalIdentifier-Based Identifier Mapping with Normalization**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
  - [x] 5.4 Write property test: Cross-reference resolution (Property 10)
    - **Property 10: Cross-Reference Resolution**
    - **Validates: Requirement 4.6**
  - [x] 5.5 Write property test: Dependency-ordered creation (Property 11)
    - **Property 11: Dependency-Ordered Creation**
    - **Validates: Requirement 5.6**
  - [x] 5.6 Write property test: Extra resources not deleted (Property 12)
    - **Property 12: Extra Resources Not Deleted**
    - **Validates: Requirement 5.4**
  - [x] 5.7 Write property test: Import error resilience (Property 13)
    - **Property 13: Import Error Resilience**
    - **Validates: Requirements 5.10, 5.14, 7.3**
  - [x] 5.8 Write property test: Import summary counts (Property 14)
    - **Property 14: Import Summary Counts**
    - **Validates: Requirements 5.12, 6.3**
  - [x] 5.9 Write property test: Automatic publishing when enabled (Property 15)
    - **Property 15: Automatic Publishing When Enabled**
    - **Validates: Requirement 5.13**
  - [x] 5.10 Write property test: Malformed JSON validation (Property 17)
    - **Property 17: Malformed JSON Validation**
    - **Validates: Requirement 7.4**
  - [x] 5.11 Document changes in `TASK_5_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `src/smus_cicd/helpers/catalog_import.py`, `tests/unit/helpers/test_catalog_import.py`, `tests/unit/helpers/test_catalog_import_properties.py`

- [x] 6. Integrate CatalogImporter into deploy command with publish support
  - Wire catalog import with automatic publishing support into deploy command flow. Extra resources in target are logged, not deleted.
  - [x] 6.1 Add `_import_catalog_from_bundle()` function to `deploy.py`
    - Extract `catalog/catalog_export.json` from bundle ZIP
    - Skip silently if file not present (backward compatible)
    - Check `deployment_configuration.catalog.disable` — skip if true
    - Validate JSON
    - Get `skipPublish` flag from `manifest.content.catalog.skipPublish` (default: false)
    - Call `import_catalog()` with skip_publish flag
    - Report summary counts including skipped (extra in target) and publishes
    - Return False if all imports fail
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.13_
  - [x] 6.2 Wire `_import_catalog_from_bundle()` into `_deploy_bundle_to_target()`
    - Call after existing `_process_catalog_assets` and before return
    - Include result in overall deployment success calculation
    - _Requirements: 6.1_
  - [x] 6.3 Write unit test for deploy command catalog import integration
    - Verify import is invoked when catalog_export.json is in bundle
    - Verify skip when file is absent
    - Verify skip when catalog.disable is true
    - Verify failure reporting when all imports fail
    - Verify skipped counts are reported for extra resources in target
    - Verify published counts are reported when publish=true
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.13_
  - [x] 6.4 Document changes in `TASK_6_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `src/smus_cicd/commands/deploy.py`, `tests/unit/commands/test_deploy_catalog_import.py`

- [x] 7. Integration tests for catalog export with project ownership
  - End-to-end tests for simplified catalog export with project ownership verification.
  - [x] 7.1 Create test app directory `tests/integration/catalog-import-export/` with manifest
    - Create `manifest.yaml` with `content.catalog.enabled: true` and `publish: false`
    - Ensure manifest contains NO filter fields (no `include`, `names`, `assetTypes` in manifest)
    - Include stages with `deployment_configuration.catalog` for import testing
    - Add a stage with `deployment_configuration.catalog.disable: true` for skip testing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.2_
  - [x] 7.2 Write integration test: end-to-end catalog export during bundle
    - Run `deploy --targets dev` to create project
    - Create catalog resources via DataZone API (ensure owningProjectId matches)
    - Run `bundle` command
    - Verify bundle ZIP contains `catalog/catalog_export.json`
    - Verify JSON structure has all required keys
    - Verify all resource types owned by project are exported
    - Verify externalIdentifier is exported for assets
    - Verify inputForms and termRelations are exported
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.8, 2.9, 2.10, 2.11, 3.2_
  - [x] 7.4 Write integration test: catalog export with no project-owned resources
    - Run bundle on empty project
    - Verify catalog_export.json has empty arrays
    - Verify no errors
    - _Requirements: 7.2_
  - [x] 7.5 Document changes in `TASK_7_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `tests/integration/catalog-import-export/manifest.yaml`, `tests/integration/catalog-import-export/test_catalog_export.py`

- [x] 8. Integration tests for catalog import with publishing
  - End-to-end tests for catalog import with externalIdentifier mapping and automatic publishing. Extra resources in target are logged, not deleted.
  - [x] 8.1 Write integration test: end-to-end catalog import during deploy
    - Bundle from source project
    - Deploy to target project
    - Verify resources are created via DataZone APIs
    - Verify externalIdentifier-based mapping works
    - Verify deploy output reports created/updated/skipped/failed counts
    - _Requirements: 5.1, 5.2, 5.3, 5.6, 6.1, 6.3_
  - [x] 8.2 Write integration test: idempotent re-deploy (update existing resources)
    - Deploy same bundle twice to same target project
    - Verify second deploy updates existing resources
    - Verify ConflictException handling works
    - _Requirements: 5.2, 5.10_
  - [x] 8.3 Write integration test: extra resources in target are logged not deleted
    - Deploy bundle with resources A, B, C
    - Create additional resource D directly in target project
    - Deploy bundle again (still only A, B, C)
    - Verify resource D is NOT deleted
    - Verify resource D is logged as extra in target
    - _Requirements: 5.4, 5.12_
  - [x] 8.4 Write integration test: source-state-based publishing
    - Deploy with `skipPublish: false` (default) in manifest
    - Verify only assets and data products with listingStatus == "ACTIVE" in source are published
    - Verify publish API is called for each asset and data product
    - Verify published count is reported in deploy output
    - _Requirements: 5.13, 5.14, 6.3_
  - [x] 8.5 Write integration test: no publishing when disabled
    - Deploy with `content.catalog.publish: false` (or omitted) in manifest
    - Verify assets and data products are NOT published
    - Verify publish API is not called
    - Verify published count is 0 in deploy output
    - _Requirements: 5.13_
  - [x] 8.6 Write integration test: publish failures are logged but don't block
    - Deploy with `skipPublish: false` (default)
    - Mock publish API to fail for one resource
    - Verify other resources continue to be processed
    - Verify failure is logged
    - Verify deploy continues successfully
    - _Requirements: 5.14_
  - [x] 8.7 Write integration test: deploy skips catalog import when disabled
    - Deploy to stage with `deployment_configuration.catalog.disable: true`
    - Verify no catalog resources are created
    - Verify deploy output indicates skip
    - _Requirements: 6.2_
  - [x] 8.8 Write integration test: deploy with bundle missing catalog_export.json
    - Deploy bundle without `catalog/` directory
    - Verify deploy succeeds without errors
    - Verify catalog import is skipped silently
    - _Requirements: 6.1_
  - [x] 8.9 Document changes in `TASK_8_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `tests/integration/catalog-import-export/test_catalog_import.py`

- [x] 9. Integration test: full round-trip export → import → verify with publishing
  - Comprehensive end-to-end validation including externalIdentifier mapping and automatic publishing.
  - [x] 9.1 Write integration test: export from source, import to target, verify resources exist
    - Bundle from source project with all resource types
    - Deploy to target project
    - Query target project via DataZone APIs to verify each resource exists
    - Verify externalIdentifier-based mapping worked correctly
    - Verify cross-references are correctly remapped
    - Verify inputForms and termRelations are preserved
    - _Requirements: 2.1, 2.2, 4.1, 4.2, 4.3, 4.6, 5.1, 5.6_
  - [x] 9.2 Write integration test: round-trip with automatic publishing
    - Bundle from source project with assets and data products
    - Deploy to target project with `skipPublish: false` (default)
    - Verify all assets and data products are automatically published
    - Query target project to verify publish status
    - Verify published count matches number of assets + data products
    - _Requirements: 5.13, 5.14_
  - [x] 9.3 Write integration test: negative scenarios
    - Test export from project with no catalog resources (verify empty JSON, no errors)
    - Test import with malformed catalog_export.json (verify validation error)
    - Test deploy when all catalog imports fail (verify deploy reports failure)
    - _Requirements: 6.4, 7.1, 7.2, 7.3, 7.4_
  - [x] 9.5 Document changes in `TASK_9_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `tests/integration/catalog-import-export/test_catalog_round_trip.py`

- [x] 10. Create example app and GitHub workflow with publish demonstration
  - Provide example application demonstrating simplified catalog import/export with automatic publishing.
  - [x] 10.1 Create example directory `examples/catalog-import-export/` with manifest
    - Create `examples/catalog-import-export/manifest.yaml` with `content.catalog.enabled: true`
    - Default `skipPublish: false` preserves source publish state
    - Ensure manifest contains NO filter fields — only `enabled`, `skipPublish`, and `assets.access` are valid
    - Include dev, test, and prod stages
    - Include `deployment_configuration.catalog` in each target stage
    - Add `README.md` explaining the example and publish feature
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 10.2 Ensure sample catalog resources exist in source project (see MaxdomeCatalogSamplesSetup Brazil package)
    - Source project should have glossaries, glossary terms, form types, asset types, assets, and data products
    - Idempotent: skip creation if resources exist
    - Print summary of created/skipped resources
    - _Requirements: 2.1, 2.2, 2.3, 5.1_
  - [x] 10.3 Create GitHub Actions workflow `.github/workflows/catalog-import-export.yml`
    - Follow existing workflow pattern
    - Use reusable `smus-bundle-deploy.yml` workflow
    - Support dev → test → prod promotion
    - _Requirements: 6.1, 2.9_
  - [x] 10.4 Create `examples/catalog-import-export/app_tests/` with validation tests
    - Create `test_catalog_deployed.py` that verifies catalog resources exist after deploy
    - Query target project via DataZone APIs
    - Verify publish status of assets and data products when publish=true
    - Follow existing `app_tests/` pattern
    - _Requirements: 5.1, 5.6, 5.13, 6.3_
  - [x] 10.5 Document changes in `TASK_10_CHANGES.md` and update `CHANGES_MASTER.md`
  - Files Changed: `examples/catalog-import-export/manifest.yaml`, `examples/catalog-import-export/README.md`, `examples/catalog-import-export/app_tests/test_catalog_deployed.py`, `.github/workflows/catalog-import-export.yml`

- [x] 11. Final checkpoint - Ensure all tests pass
  - Verify all unit, property, and integration tests pass before marking feature complete.
  - Results: 513 passed, 2 failed (pre-existing failures in `test_datazone_properties.py` unrelated to catalog import/export). All 156 catalog-specific tests pass (unit + property tests in 2.97s).
  - Files Changed: None (checkpoint only)

## Notes

- All tasks including tests are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis`
- Unit tests validate specific examples and edge cases using `pytest` with boto3 stubber
- Integration tests run against real DataZone APIs
- Each major task includes a documentation subtask to track changes

## Key Changes from Original Plan

1. **Simplified manifest with NO filter options**: The `content.catalog` section ONLY supports three fields: `enabled` (boolean), `skipPublish` (boolean), and `assets.access` (array for subscription requests). No `include`, `names`, `assetTypes`, or any other filter fields exist in the manifest.

2. **Export all resources**: When `enabled: true`, export ALL catalog resources from the source project without any manifest-based filtering.

3. **Project ownership emphasis**: All export operations filter by project ownership. The Search API uses `owningProjectIdentifier=project_id` as a request parameter for server-side filtering. The SearchTypes API does NOT support `owningProjectIdentifier` — ownership filtering is done client-side by checking `owningProjectId` on response items.

4. **Automatic publishing**: The `content.catalog.publish` boolean field in the manifest (default: true) controls whether the deploy command automatically publishes all imported assets and data products after creation or update.

5. **Enhanced identifier mapping**: Use `externalIdentifier` (with normalization to remove AWS account/region) as primary mapping key, fallback to `name` when externalIdentifier doesn't exist.

6. **Additional fields**: Export and import `formsOutput` (serialized as `formsInput`) for assets and `termRelations` for glossary terms.

7. **Asset enrichment via GetAsset API**: The Search API only returns summary data for assets without `formsOutput`. The `_enrich_asset_items()` function calls `get_asset` per asset to retrieve full details. The GetAsset API returns `id` instead of `identifier`, so `_serialize_resource` handles both via `identifier` or `id` fallback for the `sourceId` field.

8. **No deletion of extra resources**: Resources in the target project that are not in the bundle are logged for visibility but never deleted. The `_delete_resource` function has been removed and `_identify_resources_to_delete` has been renamed to `_identify_extra_target_resources`.

9. **Updated dependency graph**: Assets and FormTypes can reference GlossaryTerms, and Data Products can reference Assets, so dependency order is: Glossaries → GlossaryTerms → (FormTypes, AssetTypes can reference terms) → Assets → Data Products.

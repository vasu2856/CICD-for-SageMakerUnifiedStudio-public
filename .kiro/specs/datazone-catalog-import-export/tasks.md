# Implementation Plan: DataZone Catalog Import/Export

## Overview

Implement catalog resource export during `bundle` and import during `deploy` by adding new helper modules, extending the manifest schema, and wiring into existing command flows. The simplified approach exports ALL catalog resources when enabled via a boolean flag, uses externalIdentifier (with normalization) or name for mapping, and supports full synchronization including deletion of resources missing from the bundle. The manifest `content.catalog` section only supports `enabled` (boolean), `publish` (boolean), and `assets.access` (array for subscription requests) — no filter options of any kind. The `--updated-after` timestamp is purely a CLI flag on the bundle command that filters ALL resource types uniformly.

## Tasks

### Task 1: Extend manifest schema and data model for simplified catalog export

**Status**: Not Started

**Description**: Update manifest schema to support simple `content.catalog.enabled` boolean flag and optional `publish` boolean. The manifest `content.catalog` section ONLY supports: `enabled`, `publish`, and `assets.access` — no filter options (`include`, `names`, `assetTypes`, `updatedAfter`, etc.) whatsoever.

**Subtasks**:
- [ ] 1.1 Update `CatalogConfig` dataclass in `application_manifest.py`
  - Remove all filter-related classes (`CatalogAssetsConfig`, `CatalogGlossariesConfig`, `CatalogDataProductsConfig`, `CatalogMetadataFormsConfig`) and any filter fields (`include`, `names`, `assetTypes`, `updatedAfter`)
  - Update `CatalogConfig` to have ONLY: `enabled: bool = False`, `publish: bool = False`, `connectionName: Optional[str] = None`, and `assets: Optional[CatalogAssetsConfig] = None` (for subscription requests only)
  - No `updatedAfter` field in the manifest — that is purely a CLI flag (`--updated-after`) on the bundle command
  - Update `from_dict` parsing to handle simplified structure
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 1.2 Update `application-manifest-schema.yaml` with simplified catalog section
  - Replace complex filter configuration with simple `enabled: boolean` field
  - Add `publish: boolean` field (default: false) for automatic asset/data product publishing
  - Keep `assets.access` array for subscription requests (unchanged)
  - Remove ALL filter fields: `assets.include`, `assets.updatedAfter`, `glossaries.include`, `glossaries.updatedAfter`, `dataProducts.names`, `dataProducts.updatedAfter`, `metadataForms.include`, `metadataForms.updatedAfter`, and any other filter-related fields
  - Ensure the `content.catalog` section ONLY supports: `enabled` (boolean), `publish` (boolean), and `assets.access` (array for subscription requests)
  - _Requirements: 1.1, 1.4, 1.5, 1.6_

- [ ] 1.3 Write unit tests for manifest parsing of simplified catalog config
  - Test parsing with `enabled: true`
  - Test parsing with `enabled: false` or omitted
  - Test parsing with `publish: true` and `publish: false`
  - Test parsing with `assets.access` array (subscription requests)
  - Test that no filter fields (`include`, `names`, `assetTypes`, `updatedAfter`) are accepted in the manifest
  - Verify backward compatibility
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 1.4 Document changes in `TASK_1_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 2: Implement CatalogExporter helper with simplified export and updatedAfter support

**Status**: Not Started

**Description**: Create CatalogExporter that exports ALL project-owned catalog resources when enabled, with support for externalIdentifier, inputForms, termRelations, and optional --updated-after CLI flag (not from manifest).

**Subtasks**:
- [ ] 2.1 Create `src/smus_cicd/helpers/catalog_export.py` with `export_catalog()` function
  - Implement `export_catalog(domain_id, project_id, region, updated_after=None)` returning catalog JSON dict
  - The `updated_after` parameter comes exclusively from the `--updated-after` CLI flag, NOT from any manifest field
  - Export ALL resource types owned by the project: Glossaries, GlossaryTerms, FormTypes, AssetTypes, Assets, Data Products
  - Apply `owningProjectIdentifier=project_id` filter to ALL search queries (CRITICAL)
  - Implement `_search_resources()` for Search API with pagination and optional updatedAfter filter (from CLI flag only)
  - Implement `_search_type_resources()` for SearchTypes API with pagination and optional updatedAfter filter (from CLI flag only)
  - Implement `_serialize_resource()` to extract name, user-configurable fields, sourceId, and externalIdentifier (when present)
  - Export `inputForms` field for assets
  - Export `termRelations` field for glossary terms
  - Use sort by updatedAt DESC for all queries
  - No manifest-based filters are applied — the only optional filter is the CLI `--updated-after` timestamp applied uniformly to ALL resource types
  - _Requirements: 1.2, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

- [ ] 2.2 Write unit tests for CatalogExporter
  - Mock DataZone client with boto3 stubber
  - Test API routing per resource type
  - Test owningProjectIdentifier filter is applied to all queries
  - Test pagination handling
  - Test `--updated-after` CLI flag filter construction and application (CLI-only, not manifest-based)
  - Test that updatedAfter filter is applied uniformly to ALL resource types when provided via CLI
  - Test JSON structure output
  - Test externalIdentifier export for assets
  - Test inputForms export for assets
  - Test termRelations export for glossary terms
  - Test error propagation on API failure
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.8, 2.12_

- [ ] 2.3 Write property test: Catalog export enabled/disabled (Property 1)
  - **Property 1: Catalog Export Enabled/Disabled**
  - **Validates: Requirements 1.1, 1.2, 1.3**

- [ ] 2.4 Write property test: Export all project-owned resources (Property 2)
  - **Property 2: Export All Project-Owned Resources**
  - **Validates: Requirements 2.1, 2.2, 2.3**

- [ ] 2.5 Write property test: Updated-after filter correctness (Property 3)
  - **Property 3: Updated-After CLI Filter Correctness**
  - **Validates: Requirement 2.12**

- [ ] 2.6 Write property test: Export JSON structure invariant (Property 6)
  - **Property 6: Export JSON Structure Invariant**
  - **Validates: Requirements 3.1, 3.2**

- [ ] 2.7 Write property test: Field preservation (Property 7)
  - **Property 7: Field Preservation During Serialization**
  - **Validates: Requirements 3.3, 3.4, 3.5, 3.6**

- [ ] 2.8 Write property test: Catalog export JSON round-trip (Property 8)
  - **Property 8: Catalog Export JSON Round-Trip**
  - **Validates: Requirement 3.7**

- [ ] 2.9 Write property test: Export error propagation (Property 16)
  - **Property 16: Export Error Propagation**
  - **Validates: Requirement 7.1**

- [ ] 2.10 Document changes in `TASK_2_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 3: Integrate CatalogExporter into bundle command with --updated-after CLI flag

**Status**: Not Started

**Description**: Wire simplified catalog export into bundle command flow with optional --updated-after CLI flag (the ONLY way to filter resources — not via manifest).

**Subtasks**:
- [ ] 3.1 Add --updated-after CLI argument to bundle command
  - Add `--updated-after` argument to bundle command parser
  - Accept ISO 8601 timestamp format (e.g., 2024-01-01T00:00:00Z)
  - Validate timestamp format and raise helpful error if invalid
  - This is the ONLY way to filter catalog resources — no filter options exist in the manifest
  - _Requirements: 2.12_

- [ ] 3.2 Add catalog export step to `bundle.py`
  - After QuickSight export and before ZIP creation, check `manifest.content.catalog.enabled`
  - If enabled, get optional `--updated-after` CLI flag value from `args.updated_after` (NOT from manifest)
  - Call `export_catalog()` with domain_id, project_id, region, and updated_after (from CLI only)
  - Write `catalog/catalog_export.json` to temp_bundle_dir
  - Increment total_files_added
  - _Requirements: 1.2, 2.9, 2.12_

- [ ] 3.3 Write unit test for bundle command catalog export integration
  - Verify catalog_export.json appears in bundle ZIP when enabled
  - Verify it is skipped when disabled or omitted
  - Verify `--updated-after` CLI flag value is passed correctly to export_catalog() (sourced from CLI args, not manifest)
  - Verify no manifest-based filter values are read or passed
  - _Requirements: 2.9, 2.12_

- [ ] 3.4 Document changes in `TASK_3_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 4: Checkpoint - Ensure all tests pass

**Status**: Not Started

**Description**: Verify all unit and property tests pass before proceeding to import implementation.

### Task 5: Implement CatalogImporter helper with externalIdentifier mapping, deletion support, and automatic publishing

**Status**: Not Started

**Description**: Create CatalogImporter that uses externalIdentifier (with normalization) or name for mapping, supports deletion of resources missing from bundle, and optionally publishes assets and data products.

**Subtasks**:
- [ ] 5.1 Create `src/smus_cicd/helpers/catalog_import.py` with core import logic
  - Implement `_validate_catalog_json(catalog_data)` to check required keys
  - Implement `_normalize_external_identifier(external_id)` to remove AWS account ID and region
  - Implement `_build_identifier_map(client, domain_id, project_id, catalog_data)` to query target project using normalized externalIdentifier (when present) or name
  - Implement `_resolve_cross_references(resource, resource_type, id_map)` to replace source IDs
  - Implement `_import_resource(client, domain_id, project_id, resource, resource_type, id_map)` to call create or update API
  - Implement `_identify_resources_to_delete(client, domain_id, project_id, catalog_data)` to find resources in target not in bundle
  - Implement `_delete_resource(client, domain_id, project_id, resource_id, resource_type)` to call delete API
  - Implement `_publish_resource(client, domain_id, resource_id, resource_type)` to call publish API for assets and data products
  - Implement `import_catalog(domain_id, project_id, catalog_data, region, publish=False)` orchestrating validation, mapping, creation, update, deletion, and optional publishing
  - Creation order: Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets
  - Deletion order (reverse): Assets → AssetTypes → FormTypes, GlossaryTerms → Glossaries
  - When publish=True, publish assets and data products after creation/update
  - Preserve `inputForms` field when importing assets
  - Preserve `termRelations` field when importing glossary terms
  - Log errors per resource, continue processing, return `{created, updated, deleted, failed, published}` summary
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 7.3, 7.4_

- [ ] 5.2 Write unit tests for CatalogImporter
  - Mock DataZone client with boto3 stubber
  - Test externalIdentifier-based mapping with normalization
  - Test name-based mapping fallback
  - Test cross-reference resolution
  - Test dependency ordering for creation
  - Test dependency ordering for deletion (reverse)
  - Test automatic publishing when publish=True
  - Test publish API is not called when publish=False
  - Test error resilience (including publish failures)
  - Test ConflictException handling
  - Test JSON validation
  - Test deletion of resources not in bundle
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 5.3, 5.4, 5.5, 5.6, 5.10, 5.13, 5.14, 7.4_

- [ ] 5.3 Write property test: ExternalIdentifier-based identifier mapping with normalization (Property 9)
  - **Property 9: ExternalIdentifier-Based Identifier Mapping with Normalization**
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [ ] 5.4 Write property test: Cross-reference resolution (Property 10)
  - **Property 10: Cross-Reference Resolution**
  - **Validates: Requirement 4.6**

- [ ] 5.5 Write property test: Dependency-ordered creation (Property 11)
  - **Property 11: Dependency-Ordered Creation**
  - **Validates: Requirement 5.6**

- [ ] 5.6 Write property test: Dependency-ordered deletion (Property 12)
  - **Property 12: Dependency-Ordered Deletion**
  - **Validates: Requirements 5.4, 5.5**

- [ ] 5.7 Write property test: Import error resilience (Property 13)
  - **Property 13: Import Error Resilience**
  - **Validates: Requirements 5.10, 5.14, 7.3**

- [ ] 5.8 Write property test: Import summary counts (Property 14)
  - **Property 14: Import Summary Counts**
  - **Validates: Requirements 5.12, 6.3**

- [ ] 5.9 Write property test: Automatic publishing when enabled (Property 15)
  - **Property 15: Automatic Publishing When Enabled**
  - **Validates: Requirement 5.13**

- [ ] 5.10 Write property test: Malformed JSON validation (Property 17)
  - **Property 17: Malformed JSON Validation**
  - **Validates: Requirement 7.4**

- [ ] 5.11 Document changes in `TASK_5_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 6: Integrate CatalogImporter into deploy command with publish support

**Status**: Not Started

**Description**: Wire catalog import with deletion and automatic publishing support into deploy command flow.

**Subtasks**:
- [ ] 6.1 Add `_import_catalog_from_bundle()` function to `deploy.py`
  - Extract `catalog/catalog_export.json` from bundle ZIP
  - Skip silently if file not present (backward compatible)
  - Check `deployment_configuration.catalog.disable` — skip if true
  - Validate JSON
  - Get `publish` flag from `manifest.content.catalog.publish` (default: false)
  - Call `import_catalog()` with publish flag
  - Report summary counts including deletions and publishes
  - Return False if all imports fail
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.13_

- [ ] 6.2 Wire `_import_catalog_from_bundle()` into `_deploy_bundle_to_target()`
  - Call after existing `_process_catalog_assets` and before return
  - Include result in overall deployment success calculation
  - _Requirements: 6.1_

- [ ] 6.3 Write unit test for deploy command catalog import integration
  - Verify import is invoked when catalog_export.json is in bundle
  - Verify skip when file is absent
  - Verify skip when catalog.disable is true
  - Verify failure reporting when all imports fail
  - Verify deletion counts are reported
  - Verify published counts are reported when publish=true
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.13_

- [ ] 6.4 Document changes in `TASK_6_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 7: Integration tests for catalog export with project ownership and updatedAfter

**Status**: Not Started

**Description**: End-to-end tests for simplified catalog export with project ownership verification and --updated-after CLI flag.

**Subtasks**:
- [ ] 7.1 Create test app directory `tests/integration/catalog-import-export/` with manifest
  - Create `manifest.yaml` with `content.catalog.enabled: true` and `publish: false`
  - Ensure manifest contains NO filter fields (no `include`, `names`, `assetTypes`, `updatedAfter` in manifest)
  - Include stages with `deployment_configuration.catalog` for import testing
  - Add a stage with `deployment_configuration.catalog.disable: true` for skip testing
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.2_

- [ ] 7.2 Write integration test: end-to-end catalog export during bundle
  - Run `deploy --targets dev` to create project
  - Create catalog resources via DataZone API (ensure owningProjectId matches)
  - Run `bundle` command
  - Verify bundle ZIP contains `catalog/catalog_export.json`
  - Verify JSON structure has all required keys
  - Verify all resource types owned by project are exported
  - Verify externalIdentifier is exported for assets
  - Verify inputForms and termRelations are exported
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.8, 2.9, 2.10, 2.11, 3.2_

- [ ] 7.3 Write integration test: catalog export with --updated-after CLI flag
  - Run bundle with `--updated-after` CLI flag set to a recent timestamp (not from manifest)
  - Verify only resources modified after that timestamp are included
  - Verify the filter is applied uniformly to ALL resource types
  - Run bundle with `--updated-after` set far in the future and verify empty arrays
  - _Requirements: 2.12, 3.1, 3.2_

- [ ] 7.4 Write integration test: catalog export with no project-owned resources
  - Run bundle on empty project
  - Verify catalog_export.json has empty arrays
  - Verify no errors
  - _Requirements: 7.2_

- [ ] 7.5 Document changes in `TASK_7_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 8: Integration tests for catalog import with deletion and publishing

**Status**: Not Started

**Description**: End-to-end tests for catalog import with externalIdentifier mapping, deletion support, and automatic publishing.

**Subtasks**:
- [ ] 8.1 Write integration test: end-to-end catalog import during deploy
  - Bundle from source project
  - Deploy to target project
  - Verify resources are created via DataZone APIs
  - Verify externalIdentifier-based mapping works
  - Verify deploy output reports created/updated/deleted/failed counts
  - _Requirements: 5.1, 5.2, 5.3, 5.6, 6.1, 6.3_

- [ ] 8.2 Write integration test: idempotent re-deploy (update existing resources)
  - Deploy same bundle twice to same target project
  - Verify second deploy updates existing resources
  - Verify ConflictException handling works
  - _Requirements: 5.2, 5.10_

- [ ] 8.3 Write integration test: deletion of resources not in bundle
  - Deploy bundle with resources A, B, C
  - Create additional resource D directly in target project
  - Deploy bundle again (still only A, B, C)
  - Verify resource D is deleted
  - Verify deletion happens in reverse dependency order
  - _Requirements: 5.4, 5.5, 5.12_

- [ ] 8.4 Write integration test: automatic publishing when enabled
  - Deploy with `content.catalog.publish: true` in manifest
  - Verify assets and data products are automatically published after creation
  - Verify publish API is called for each asset and data product
  - Verify published count is reported in deploy output
  - _Requirements: 5.13, 5.14, 6.3_

- [ ] 8.5 Write integration test: no publishing when disabled
  - Deploy with `content.catalog.publish: false` (or omitted) in manifest
  - Verify assets and data products are NOT published
  - Verify publish API is not called
  - Verify published count is 0 in deploy output
  - _Requirements: 5.13_

- [ ] 8.6 Write integration test: publish failures are logged but don't block
  - Deploy with `content.catalog.publish: true`
  - Mock publish API to fail for one resource
  - Verify other resources continue to be processed
  - Verify failure is logged
  - Verify deploy continues successfully
  - _Requirements: 5.14_

- [ ] 8.7 Write integration test: deploy skips catalog import when disabled
  - Deploy to stage with `deployment_configuration.catalog.disable: true`
  - Verify no catalog resources are created
  - Verify deploy output indicates skip
  - _Requirements: 6.2_

- [ ] 8.8 Write integration test: deploy with bundle missing catalog_export.json
  - Deploy bundle without `catalog/` directory
  - Verify deploy succeeds without errors
  - Verify catalog import is skipped silently
  - _Requirements: 6.1_

- [ ] 8.9 Document changes in `TASK_8_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 9: Integration test: full round-trip export → import → verify with publishing

**Status**: Not Started

**Description**: Comprehensive end-to-end validation including externalIdentifier mapping, deletion, and automatic publishing.

**Subtasks**:
- [ ] 9.1 Write integration test: export from source, import to target, verify resources exist
  - Bundle from source project with all resource types
  - Deploy to target project
  - Query target project via DataZone APIs to verify each resource exists
  - Verify externalIdentifier-based mapping worked correctly
  - Verify cross-references are correctly remapped
  - Verify inputForms and termRelations are preserved
  - _Requirements: 2.1, 2.2, 4.1, 4.2, 4.3, 4.6, 5.1, 5.6_

- [ ] 9.2 Write integration test: round-trip with automatic publishing
  - Bundle from source project with assets and data products
  - Deploy to target project with `content.catalog.publish: true`
  - Verify all assets and data products are automatically published
  - Query target project to verify publish status
  - Verify published count matches number of assets + data products
  - _Requirements: 5.13, 5.14_

- [ ] 9.3 Write integration test: round-trip with --updated-after CLI filter
  - Create resources in source project at different times
  - Bundle with `--updated-after` CLI flag set to middle timestamp (not from manifest)
  - Deploy to target project
  - Verify only resources modified after timestamp are imported
  - _Requirements: 2.12_

- [ ] 9.4 Write integration test: negative scenarios
  - Test export from project with no catalog resources (verify empty JSON, no errors)
  - Test import with malformed catalog_export.json (verify validation error)
  - Test deploy when all catalog imports fail (verify deploy reports failure)
  - Test bundle with invalid --updated-after timestamp format (verify error)
  - _Requirements: 6.4, 7.1, 7.2, 7.3, 7.4_

- [ ] 9.5 Document changes in `TASK_9_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 10: Create example app and GitHub workflow with publish demonstration

**Status**: Not Started

**Description**: Provide example application demonstrating simplified catalog import/export with automatic publishing.

**Subtasks**:
- [ ] 10.1 Create example directory `examples/catalog-import-export/` with manifest
  - Create `examples/catalog-import-export/manifest.yaml` with `content.catalog.enabled: true`
  - Set `content.catalog.publish: true` to demonstrate automatic publishing
  - Ensure manifest contains NO filter fields — only `enabled`, `publish`, and `assets.access` are valid
  - Include dev, test, and prod stages
  - Include `deployment_configuration.catalog` in each target stage
  - Add `README.md` explaining the example, publish feature, and `--updated-after` CLI flag usage
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 10.2 Create sample data seed script `examples/catalog-import-export/seed_catalog_data.py`
  - Script to populate source project with sample catalog resources
  - Accept `--domain-id`, `--project-id`, `--region` CLI args
  - Idempotent: skip creation if resources exist
  - Print summary of created/skipped resources
  - _Requirements: 2.1, 2.2, 2.3, 5.1_

- [ ] 10.3 Create GitHub Actions workflow `.github/workflows/catalog-import-export.yml`
  - Follow existing workflow pattern
  - Use reusable `smus-bundle-deploy.yml` workflow
  - Support dev → test → prod promotion
  - Demonstrate `--updated-after` CLI flag usage in comments (this is the only way to filter, not via manifest)
  - _Requirements: 6.1, 2.9, 2.12_

- [ ] 10.4 Create `examples/catalog-import-export/app_tests/` with validation tests
  - Create `test_catalog_deployed.py` that verifies catalog resources exist after deploy
  - Query target project via DataZone APIs
  - Verify publish status of assets and data products when publish=true
  - Follow existing `app_tests/` pattern
  - _Requirements: 5.1, 5.6, 5.13, 6.3_

- [ ] 10.5 Document changes in `TASK_10_CHANGES.md` and update `CHANGES_MASTER.md`

### Task 11: Final checkpoint - Ensure all tests pass

**Status**: Not Started

**Description**: Verify all unit, property, and integration tests pass before marking feature complete.

## Notes

- All tasks including tests are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis`
- Unit tests validate specific examples and edge cases using `pytest` with boto3 stubber
- Integration tests run against real DataZone APIs
- Each major task includes a documentation subtask to track changes

## Key Changes from Original Plan

1. **Simplified manifest with NO filter options**: The `content.catalog` section ONLY supports three fields: `enabled` (boolean), `publish` (boolean), and `assets.access` (array for subscription requests). No `include`, `names`, `assetTypes`, `updatedAfter`, or any other filter fields exist in the manifest.

2. **Export all resources**: When `enabled: true`, export ALL catalog resources from the source project without any manifest-based filtering.

3. **Project ownership emphasis**: All export operations explicitly filter by `owningProjectIdentifier=project_id` to ensure ONLY resources owned by the source project are exported.

4. **CLI-only `--updated-after` filter**: The `--updated-after` flag is purely a CLI option on the bundle command (not a manifest field). It accepts an ISO 8601 timestamp and filters ALL resource types uniformly by modification timestamp.

5. **Automatic publishing**: The `content.catalog.publish` boolean field in the manifest (default: false) controls whether the deploy command automatically publishes all imported assets and data products after creation or update.

6. **Enhanced identifier mapping**: Use `externalIdentifier` (with normalization to remove AWS account/region) as primary mapping key, fallback to `name` when externalIdentifier doesn't exist.

7. **Additional fields**: Export and import `inputForms` for assets and `termRelations` for glossary terms.

8. **Deletion support**: Deploy command now deletes resources in target project that are missing from the bundle, using reverse dependency order.

9. **Updated dependency graph**: Assets and FormTypes can reference GlossaryTerms, so dependency order is: Glossaries → GlossaryTerms → (FormTypes, AssetTypes can reference terms) → Assets.

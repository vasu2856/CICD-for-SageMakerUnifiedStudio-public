# Requirements Document

## Introduction

This feature adds support for importing and exporting DataZone catalog assets (Glossaries, GlossaryTerms, FormTypes, AssetTypes, Assets, and Data Products) as part of the SMUS CI/CD `bundle` and `deploy` commands. During bundling, the CLI exports all catalog resources from a source project using the DataZone Search and SearchTypes APIs and serializes them to JSON, including each asset's and data product's `listingStatus` to preserve the source publish state. For assets, an additional GetAsset API call per item enriches the search results with full details including `formsOutput` (form data), since the Search API only returns summary data. The Search API supports `owningProjectIdentifier` for server-side ownership filtering, while the SearchTypes API requires client-side filtering by `owningProjectId` on response items. An optional `--updated-after` CLI flag on the bundle command allows filtering resources by modification timestamp. The manifest configuration is intentionally simple: a boolean `enabled` flag to turn catalog export on/off, and an optional `skipPublish` flag to override the default source-state-based publishing behavior. No filter options (include lists, name filters, asset type filters, or date filters) exist in the manifest. During deployment, the CLI reads the exported JSON, maps source identifiers to target project identifiers using externalIdentifier (when present) or name as fallback, creates or updates the resources in the target project via DataZone create/update APIs, and publishes assets and data products that were published in the source project unless `skipPublish` is set to true.

## Glossary

- **CLI**: The `smus-cli` command-line interface for SMUS CI/CD operations
- **Bundle_Command**: The CLI command that packages application content (S3 files, QuickSight dashboards, Git repos, and now catalog assets) into a deployable ZIP archive
- **Deploy_Command**: The CLI command that deploys a bundle archive to a target stage's DataZone project
- **Catalog_Exporter**: The component responsible for querying DataZone Search/SearchTypes APIs and serializing catalog resources to JSON
- **Catalog_Importer**: The component responsible for reading exported catalog JSON, mapping identifiers from source to target project, and creating/updating resources in the target project
- **Identifier_Mapper**: The component that builds a mapping between source project resource identifiers and target project resource identifiers using the `externalIdentifier` field (when present) or `name` field as fallback
- **External_Identifier**: A unique identifier for a resource that may contain AWS account and region information that must be normalized before mapping
- **DataZone_Domain**: An Amazon DataZone domain that contains projects and catalog resources
- **DataZone_Project**: A project within a DataZone domain that owns catalog resources
- **Glossary**: A DataZone business glossary that organizes domain-specific terminology
- **Glossary_Term**: An individual term within a Glossary, containing definitions and metadata
- **Form_Type**: A DataZone metadata form type that defines custom metadata schemas with fields and validation rules
- **Metadata_Form**: An instance of a Form_Type containing actual metadata values for an asset
- **Asset_Type**: A DataZone asset type that defines the structure and metadata for a category of assets
- **Asset**: A DataZone catalog asset representing a data resource with metadata, forms, and optional glossary term associations
- **Data_Product**: A DataZone data product that bundles one or more data assets for publishing and sharing
- **Catalog_Export_JSON**: The JSON file produced during bundling that contains serialized catalog resources from the source project
- **Catalog_Import_JSON**: The JSON file produced during deployment that contains catalog resources with identifiers remapped for the target project
- **Manifest**: The `manifest.yaml` file that defines application content, stages, and deployment configuration
- **Search_API**: The DataZone `search` API used to find Assets, GlossaryTerms, Glossaries, and Data Products. Supports `owningProjectIdentifier` as a request parameter for server-side ownership filtering.
- **SearchTypes_API**: The DataZone `searchTypes` API used to find FormTypes and AssetTypes. Does NOT support `owningProjectIdentifier` as a request parameter — ownership filtering must be done client-side by checking `owningProjectId` on response items.
- **GetAsset_API**: The DataZone `get_asset` API used to retrieve full asset details. Required because the Search API only returns summary data without `formsOutput` (form data). Returns `id` instead of `identifier` for the asset identifier field.


## Requirements

### Requirement 1: Manifest Configuration for Catalog Export

**User Story:** As a developer, I want to enable or disable catalog resource export in my manifest.yaml, so that the bundle command knows whether to export all catalog resources owned by my project.

#### Acceptance Criteria

1. THE Manifest SHALL support a `content.catalog.enabled` boolean field to enable or disable catalog export (default: false)
2. WHEN `content.catalog.enabled` is set to true, THE Bundle_Command SHALL export ALL catalog resource types owned by the source project (Glossaries, GlossaryTerms, FormTypes, AssetTypes, Assets, and Data Products)
3. WHEN `content.catalog.enabled` is set to false or omitted, THE Bundle_Command SHALL NOT export any catalog resources
4. THE Manifest SHALL support an optional `content.catalog.skipPublish` boolean field to override the default source-state-based publishing behavior (default: false). When false, assets and data products are published only if they were published (listingStatus == "ACTIVE") in the source project. When true, all publishing is skipped regardless of source state.
5. THE Manifest SHALL NOT contain any filter options for catalog resources (no `include`, `names`, `assetTypes`, `updatedAfter`, or any other filter fields within the `content.catalog` section or its subsections)
6. THE Manifest `content.catalog` section SHALL only support the following fields: `enabled` (boolean), `skipPublish` (boolean), and `assets.access` (array for subscription requests)
7. THE Catalog_Exporter SHALL export the `formsOutput` data for assets (retrieved via the GetAsset API enrichment step, serialized as `formsInput`)
8. THE Catalog_Exporter SHALL export the `termRelations` field as part of glossary term serialization

### Requirement 2: Export Catalog Resources During Bundle

**User Story:** As a developer, I want the bundle command to export DataZone catalog resources owned by my source project, so that I can promote catalog definitions across stages.

#### Acceptance Criteria

1. WHEN the bundle command runs and `content.catalog.enabled` is true, THE Catalog_Exporter SHALL query the DataZone Search_API for all Assets, GlossaryTerms, Glossaries, and Data Products owned by the source project, using the `owningProjectIdentifier` API parameter for server-side ownership filtering
2. WHEN the bundle command runs and `content.catalog.enabled` is true, THE Catalog_Exporter SHALL query the DataZone SearchTypes_API for all FormTypes and AssetTypes owned by the source project, using client-side filtering by `owningProjectId` on response items (since the SearchTypes API does not support the `owningProjectIdentifier` parameter)
3. THE Catalog_Exporter SHALL ONLY export resources where the `owningProjectId` matches the source project identifier
4. THE Catalog_Exporter SHALL export the complete form type definition including the model (field definitions, types, and validation rules)
5. THE Catalog_Exporter SHALL use a sort clause of `{"attribute": "updatedAt", "order": "DESCENDING"}` for all search queries
6. THE Catalog_Exporter SHALL handle pagination by following `nextToken` until all matching results are retrieved
7. WHEN the Catalog_Exporter retrieves Glossaries, THE Catalog_Exporter SHALL use the Search_API with `searchScope` set to `GLOSSARY`
8. WHEN the Catalog_Exporter retrieves Data Products, THE Catalog_Exporter SHALL use the Search_API with `searchScope` set to `DATA_PRODUCT`
9. THE Catalog_Exporter SHALL serialize all retrieved resources into a single `catalog_export.json` file within the bundle archive under a `catalog/` directory
10. WHEN serializing assets, THE Catalog_Exporter SHALL include the `formsOutput` data (retrieved via the GetAsset API enrichment step) serialized as `formsInput` in the exported JSON, since the Search API does not return form data in its summary results
11. WHEN serializing glossary terms, THE Catalog_Exporter SHALL include the `termRelations` field in the exported JSON
12. WHEN the bundle command is invoked with an optional `--updated-after` CLI flag, THE Catalog_Exporter SHALL filter exported resources to only include those with `updatedAt` timestamp greater than or equal to the specified ISO 8601 timestamp
13. WHEN exporting assets, THE Catalog_Exporter SHALL call the GetAsset API for each asset returned by the Search API to retrieve full asset details including `formsOutput`, `description`, and `listingStatus`, since the Search API only returns summary data
14. WHEN resolving the source identifier for assets, THE Catalog_Exporter SHALL use the `identifier` field (from Search API results) or the `id` field (from GetAsset API results) as a fallback, since these APIs use different field names for the asset identifier

### Requirement 3: Catalog Export JSON Serialization

**User Story:** As a developer, I want the exported catalog data to be stored in a well-structured JSON file, so that it can be reliably read during deployment.

#### Acceptance Criteria

1. THE Catalog_Exporter SHALL produce a JSON file containing a top-level object with keys: `metadata`, `glossaries`, `glossaryTerms`, `formTypes`, `assetTypes`, `assets`, and `dataProducts`
2. THE `metadata` section SHALL include `sourceProjectId`, `sourceDomainId`, `exportTimestamp`, and `resourceTypes` fields
3. WHEN serializing each resource, THE Catalog_Exporter SHALL preserve the `name` field, all user-configurable attributes, and the source identifier
4. WHEN serializing metadata form types, THE Catalog_Exporter SHALL preserve the complete `model` structure including all field definitions, data types, constraints, and validation rules
5. WHEN serializing assets, THE Catalog_Exporter SHALL preserve the `inputForms` field containing the asset's metadata form instances
6. WHEN serializing glossary terms, THE Catalog_Exporter SHALL preserve the `termRelations` field containing relationships to other terms
7. THE Catalog_Export_JSON SHALL be valid JSON that can be deserialized back into equivalent data structures (round-trip property)

### Requirement 4: Identifier Mapping During Deploy

**User Story:** As a developer, I want the deploy command to map source project identifiers to target project identifiers, so that catalog resources reference the correct entities in the target environment.

#### Acceptance Criteria

1. WHEN the deploy command processes a Catalog_Export_JSON, THE Identifier_Mapper SHALL build a mapping from source resource identifiers to target resource identifiers using the `externalIdentifier` field when present, or the `name` field as fallback
2. WHEN a resource has an `externalIdentifier` field, THE Identifier_Mapper SHALL normalize it by removing AWS account ID and region information before using it for mapping
3. THE Identifier_Mapper SHALL query the target project for existing resources by normalized externalIdentifier (when present) or name to find matching target identifiers
4. IF a resource with the same normalized externalIdentifier or name already exists in the target project, THEN THE Identifier_Mapper SHALL map the source identifier to the existing target identifier
5. IF a resource with the same normalized externalIdentifier or name does not exist in the target project, THEN THE Identifier_Mapper SHALL mark the resource for creation
6. THE Identifier_Mapper SHALL resolve cross-resource references (e.g., GlossaryTerm referencing a Glossary, Asset referencing an AssetType, Asset or FormType referencing GlossaryTerms) using the built mapping

### Requirement 5: Create, Update, and Delete Catalog Resources in Target Project

**User Story:** As a developer, I want the deploy command to synchronize catalog resources in the target project with the bundle, so that my catalog definitions are promoted across stages and obsolete resources are removed.

#### Acceptance Criteria

1. WHEN a resource is marked for creation, THE Catalog_Importer SHALL call the corresponding DataZone create API (CreateGlossary, CreateGlossaryTerm, CreateFormType, CreateAssetType, CreateAsset)
2. WHEN creating metadata form types, THE Catalog_Importer SHALL preserve the complete model structure including all field definitions and validation rules
3. WHEN a resource already exists in the target project (matched by normalized externalIdentifier or name), THE Catalog_Importer SHALL call the corresponding DataZone update API to synchronize the resource
4. WHEN a resource exists in the target project but is NOT present in the Catalog_Export_JSON, THE Catalog_Importer SHALL call the corresponding DataZone delete API to remove the resource
5. THE Catalog_Importer SHALL delete resources in reverse dependency order: Assets before AssetTypes, AssetTypes before FormTypes, GlossaryTerms before Glossaries (to avoid breaking references)
6. THE Catalog_Importer SHALL create resources in dependency order: Glossaries before GlossaryTerms, FormTypes before AssetTypes, AssetTypes before Assets (noting that Assets and FormTypes can reference GlossaryTerms)
7. THE Catalog_Importer SHALL create metadata form types before any assets or asset types that reference them
8. WHEN importing assets, THE Catalog_Importer SHALL preserve the `inputForms` field containing the asset's metadata form instances
9. WHEN importing glossary terms, THE Catalog_Importer SHALL preserve the `termRelations` field containing relationships to other terms
10. IF a DataZone API call fails during import, THEN THE Catalog_Importer SHALL log the error, continue processing remaining resources, and report a summary of failures at the end
11. THE Catalog_Importer SHALL produce a Catalog_Import_JSON file with the remapped identifiers before making API calls, for auditability
12. THE Catalog_Importer SHALL report counts of created, updated, deleted, and failed resources in the import summary
13. WHEN `content.catalog.skipPublish` is false (default) in the manifest, THE Catalog_Importer SHALL automatically publish imported assets and data products only if they were published (listingStatus == "ACTIVE") in the source project. WHEN `content.catalog.skipPublish` is true, THE Catalog_Importer SHALL skip all publishing regardless of source state. After calling the asynchronous publish API (`create_listing_change_set`), THE Catalog_Importer SHALL poll the resource's listing status to verify it becomes ACTIVE before counting it as published. If the listing status is FAILED or the verification times out, the resource SHALL be counted as a publish failure.
14. WHEN publishing assets or data products, IF the publish API call fails or the listing verification determines the listing status is FAILED, THEN THE Catalog_Importer SHALL log the error and continue processing remaining resources
15. WHEN importing assets that contain a `DataSourceReferenceForm` in their `formsInput`, THE Catalog_Importer SHALL remap the form's `dataSourceIdentifier.id`, `filterableDataSourceId`, and `dataSourceRunId` to a matching data source in the target project. The target data source SHALL be matched by type and database name: (1) exact `databaseName` match in the data source's `relationalFilterConfigurations`, (2) wildcard `"*"` database filter, (3) first candidate of the same type. The `databaseName` SHALL be extracted from the asset's `GlueTableForm` content. If no matching data source exists in the target project, the `DataSourceReferenceForm` SHALL be stripped from the asset's forms.

### Requirement 6: Deploy Command Integration

**User Story:** As a developer, I want catalog import to be integrated into the existing deploy command flow, so that catalog resources are deployed alongside other bundle content.

#### Acceptance Criteria

1. WHEN the deploy command processes a bundle containing a `catalog/catalog_export.json` file, THE Deploy_Command SHALL invoke the Catalog_Importer after storage and QuickSight deployments
2. WHERE the stage's `deployment_configuration.catalog.disable` is set to true, THE Deploy_Command SHALL skip catalog import for that stage
3. THE Deploy_Command SHALL report the count of created, updated, and failed catalog resources upon completion
4. IF all catalog resource imports fail, THEN THE Deploy_Command SHALL report the deployment as failed

### Requirement 7: Error Handling and Resilience

**User Story:** As a developer, I want robust error handling during catalog export and import, so that partial failures do not silently corrupt my catalog state.

#### Acceptance Criteria

1. IF the DataZone Search_API or SearchTypes_API returns an error during export, THEN THE Catalog_Exporter SHALL raise an exception with a descriptive error message
2. IF the source project has no catalog resources (or no resources matching the `--updated-after` CLI timestamp when provided), THEN THE Catalog_Exporter SHALL produce an empty Catalog_Export_JSON with zero resources and log an informational message
3. IF a create or update API call fails for a specific resource during import, THEN THE Catalog_Importer SHALL log the resource name, type, and error, then continue with the next resource
4. IF the Catalog_Export_JSON is malformed or missing required fields, THEN THE Catalog_Importer SHALL raise a validation error before attempting any API calls

# Requirements Document

## Introduction

This feature adds support for importing and exporting DataZone catalog assets (Glossaries, GlossaryTerms, FormTypes, AssetTypes, and Assets) as part of the SMUS CI/CD `bundle` and `deploy` commands. During bundling, the CLI exports catalog resources from a source project using the DataZone Search and SearchTypes APIs, filtered by `updatedAt` timestamp, and serializes them to JSON. During deployment, the CLI reads the exported JSON, maps source identifiers to target project identifiers by name, and creates or updates the resources in the target project via DataZone create/update APIs.

## Glossary

- **CLI**: The `smus-cli` command-line interface for SMUS CI/CD operations
- **Bundle_Command**: The CLI command that packages application content (S3 files, QuickSight dashboards, Git repos, and now catalog assets) into a deployable ZIP archive
- **Deploy_Command**: The CLI command that deploys a bundle archive to a target stage's DataZone project
- **Catalog_Exporter**: The component responsible for querying DataZone Search/SearchTypes APIs and serializing catalog resources to JSON
- **Catalog_Importer**: The component responsible for reading exported catalog JSON, mapping identifiers from source to target project, and creating/updating resources in the target project
- **Identifier_Mapper**: The component that builds a mapping between source project resource identifiers and target project resource identifiers using the `name` field
- **DataZone_Domain**: An Amazon DataZone domain that contains projects and catalog resources
- **DataZone_Project**: A project within a DataZone domain that owns catalog resources
- **Glossary**: A DataZone business glossary that organizes domain-specific terminology
- **Glossary_Term**: An individual term within a Glossary, containing definitions and metadata
- **Form_Type**: A DataZone metadata form type that defines custom metadata schemas with fields and validation rules
- **Metadata_Form**: An instance of a Form_Type containing actual metadata values for an asset
- **Asset_Type**: A DataZone asset type that defines the structure and metadata for a category of assets
- **Asset**: A DataZone catalog asset representing a data resource with metadata and forms
- **Data_Product**: A DataZone data product that bundles one or more data assets for publishing and sharing
- **Catalog_Export_JSON**: The JSON file produced during bundling that contains serialized catalog resources from the source project
- **Catalog_Import_JSON**: The JSON file produced during deployment that contains catalog resources with identifiers remapped for the target project
- **Manifest**: The `manifest.yaml` file that defines application content, stages, and deployment configuration
- **Search_API**: The DataZone `search` API used to find Assets, GlossaryTerms, and Data Products
- **SearchTypes_API**: The DataZone `searchTypes` API used to find FormTypes and AssetTypes
- **Updated_At_Filter**: A filter on the `updatedAt` attribute that limits exported resources to those modified after a user-specified timestamp
- **Data_Product_Filter**: A filter that limits exported data products to only those explicitly listed in the manifest by name


## Requirements

### Requirement 1: Manifest Configuration for Catalog Export

**User Story:** As a developer, I want to configure catalog resource export in my manifest.yaml, so that the bundle command knows which catalog resource types to export and with what filters.

#### Acceptance Criteria

1. THE Manifest SHALL support a `content.catalog` section with `assets`, `glossaries`, `dataProducts`, and `metadataForms` subsections for organizing catalog resource export configuration
2. WHEN a user specifies `content.catalog.assets.include` in the manifest, THE Bundle_Command SHALL only export the listed asset-related resource types (formTypes, assetTypes, assets)
2a. WHEN a user specifies `content.catalog.metadataForms.include` in the manifest, THE Bundle_Command SHALL export metadata form types and their field definitions
3. WHEN a user specifies `content.catalog.glossaries.include` in the manifest, THE Bundle_Command SHALL only export the listed glossary-related resource types (glossaries, glossaryTerms)
4. WHERE a user specifies `content.catalog.assets.updatedAfter` in the manifest, THE Bundle_Command SHALL only export asset-related resources with `updatedAt` greater than or equal to the specified ISO 8601 timestamp
5. WHERE a user specifies `content.catalog.glossaries.updatedAfter` in the manifest, THE Bundle_Command SHALL only export glossary-related resources with `updatedAt` greater than or equal to the specified ISO 8601 timestamp
6. IF `content.catalog.assets` is present but `include` is omitted, THEN THE Bundle_Command SHALL export all three asset-related resource types (formTypes, assetTypes, assets) by default
7. IF `content.catalog.glossaries` is present but `include` is omitted, THEN THE Bundle_Command SHALL export both glossary-related resource types (glossaries, glossaryTerms) by default
8. WHEN a user specifies `content.catalog.dataProducts.names` in the manifest, THE Bundle_Command SHALL only export data products whose names match the specified list
9. WHERE a user specifies `content.catalog.dataProducts.updatedAfter` in the manifest, THE Bundle_Command SHALL only export data products with `updatedAt` greater than or equal to the specified ISO 8601 timestamp
10. IF `content.catalog.dataProducts` is present but `names` is omitted, THEN THE Bundle_Command SHALL export all data products from the source project
11. WHEN a user specifies `content.catalog.metadataForms.updatedAfter` in the manifest, THE Bundle_Command SHALL only export metadata forms with `updatedAt` greater than or equal to the specified ISO 8601 timestamp
12. IF `content.catalog.metadataForms` is present but `include` is omitted, THEN THE Bundle_Command SHALL export all metadata form types from the source project

### Requirement 2: Export Catalog Resources During Bundle

**User Story:** As a developer, I want the bundle command to export DataZone catalog resources from my source project, so that I can promote catalog definitions across stages.

#### Acceptance Criteria

1. WHEN the bundle command runs and `content.catalog.assets` or `content.catalog.glossaries` is configured, THE Catalog_Exporter SHALL query the DataZone Search_API for Assets and GlossaryTerms owned by the source project
2. WHEN the bundle command runs and `content.catalog.assets` or `content.catalog.metadataForms` is configured, THE Catalog_Exporter SHALL query the DataZone SearchTypes_API for FormTypes and AssetTypes owned by the source project
2a. WHEN the bundle command runs and `content.catalog.metadataForms` is configured, THE Catalog_Exporter SHALL export the complete form type definition including the model (field definitions, types, and validation rules)
3. WHEN the bundle command runs and `content.catalog.dataProducts` is configured, THE Catalog_Exporter SHALL query the DataZone Search_API for Data Products owned by the source project
4. THE Catalog_Exporter SHALL use a sort clause of `{"attribute": "updatedAt", "order": "DESCENDING"}` for all search queries
5. WHERE an `updatedAfter` filter is specified for assets, glossaries, or data products, THE Catalog_Exporter SHALL apply a filter on the `updatedAt` attribute to only include resources modified at or after the specified timestamp
6. WHERE a `names` filter is specified for data products, THE Catalog_Exporter SHALL only export data products whose names match the specified list
7. THE Catalog_Exporter SHALL handle pagination by following `nextToken` until all matching results are retrieved
8. WHEN the Catalog_Exporter retrieves Glossaries, THE Catalog_Exporter SHALL use the Search_API with `searchScope` set to `GLOSSARY`
9. WHEN the Catalog_Exporter retrieves Data Products, THE Catalog_Exporter SHALL use the Search_API with `searchScope` set to `DATA_PRODUCT`
10. THE Catalog_Exporter SHALL serialize all retrieved resources into a single `catalog_export.json` file within the bundle archive under a `catalog/` directory

### Requirement 3: Catalog Export JSON Serialization

**User Story:** As a developer, I want the exported catalog data to be stored in a well-structured JSON file, so that it can be reliably read during deployment.

#### Acceptance Criteria

1. THE Catalog_Exporter SHALL produce a JSON file containing a top-level object with keys: `metadata`, `glossaries`, `glossaryTerms`, `formTypes`, `assetTypes`, `assets`, and `metadataForms`
2. THE `metadata` section SHALL include `sourceProjectId`, `sourceDomainId`, `exportTimestamp`, and `resourceTypes` fields
3. WHEN serializing each resource, THE Catalog_Exporter SHALL preserve the `name` field, all user-configurable attributes, and the source identifier
3a. WHEN serializing metadata form types, THE Catalog_Exporter SHALL preserve the complete `model` structure including all field definitions, data types, constraints, and validation rules
4. THE Catalog_Export_JSON SHALL be valid JSON that can be deserialized back into equivalent data structures (round-trip property)

### Requirement 4: Identifier Mapping During Deploy

**User Story:** As a developer, I want the deploy command to map source project identifiers to target project identifiers, so that catalog resources reference the correct entities in the target environment.

#### Acceptance Criteria

1. WHEN the deploy command processes a Catalog_Export_JSON, THE Identifier_Mapper SHALL build a mapping from source resource identifiers to target resource identifiers using the `name` field
2. THE Identifier_Mapper SHALL query the target project for existing resources by name to find matching target identifiers
3. IF a resource with the same name already exists in the target project, THEN THE Identifier_Mapper SHALL map the source identifier to the existing target identifier
4. IF a resource with the same name does not exist in the target project, THEN THE Identifier_Mapper SHALL mark the resource for creation
5. THE Identifier_Mapper SHALL resolve cross-resource references (e.g., GlossaryTerm referencing a Glossary, Asset referencing an AssetType) using the built mapping

### Requirement 5: Create and Update Catalog Resources in Target Project

**User Story:** As a developer, I want the deploy command to create or update catalog resources in the target project, so that my catalog definitions are promoted across stages.

#### Acceptance Criteria

1. WHEN a resource is marked for creation, THE Catalog_Importer SHALL call the corresponding DataZone create API (CreateGlossary, CreateGlossaryTerm, CreateFormType, CreateAssetType, CreateAsset)
1a. WHEN creating metadata form types, THE Catalog_Importer SHALL preserve the complete model structure including all field definitions and validation rules
2. WHEN a resource already exists in the target project (matched by name), THE Catalog_Importer SHALL call the corresponding DataZone update API to synchronize the resource
3. THE Catalog_Importer SHALL create resources in dependency order: FormTypes before AssetTypes, Glossaries before GlossaryTerms, AssetTypes before Assets
3a. THE Catalog_Importer SHALL create metadata form types before any assets or asset types that reference them
4. IF a DataZone API call fails during import, THEN THE Catalog_Importer SHALL log the error, continue processing remaining resources, and report a summary of failures at the end
5. THE Catalog_Importer SHALL produce a Catalog_Import_JSON file with the remapped identifiers before making API calls, for auditability

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
2. IF the source project has no catalog resources matching the filter criteria, THEN THE Catalog_Exporter SHALL produce an empty Catalog_Export_JSON with zero resources and log an informational message
3. IF a create or update API call fails for a specific resource during import, THEN THE Catalog_Importer SHALL log the resource name, type, and error, then continue with the next resource
4. IF the Catalog_Export_JSON is malformed or missing required fields, THEN THE Catalog_Importer SHALL raise a validation error before attempting any API calls

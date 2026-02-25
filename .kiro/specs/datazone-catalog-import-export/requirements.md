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
- **Form_Type**: A DataZone metadata form type that defines custom metadata schemas
- **Asset_Type**: A DataZone asset type that defines the structure and metadata for a category of assets
- **Asset**: A DataZone catalog asset representing a data resource with metadata and forms
- **Catalog_Export_JSON**: The JSON file produced during bundling that contains serialized catalog resources from the source project
- **Catalog_Import_JSON**: The JSON file produced during deployment that contains catalog resources with identifiers remapped for the target project
- **Manifest**: The `manifest.yaml` file that defines application content, stages, and deployment configuration
- **Search_API**: The DataZone `search` API used to find Assets and GlossaryTerms
- **SearchTypes_API**: The DataZone `searchTypes` API used to find FormTypes and AssetTypes
- **Updated_At_Filter**: A filter on the `updatedAt` attribute that limits exported resources to those modified after a user-specified timestamp
- **Schedule_Asset**: A DataZone catalog asset of managed type `SageMakerUnifiedStudioScheduleAssetType` that represents an Amazon EventBridge Scheduler schedule
- **EventBridge_Schedule**: An Amazon EventBridge Scheduler schedule resource that defines a time-based trigger (cron or rate expression) with a target action
- **Schedule_Exporter**: The sub-component of Catalog_Exporter responsible for retrieving the EventBridge Scheduler schedule definition associated with a Schedule_Asset
- **Schedule_Importer**: The sub-component of Catalog_Importer responsible for creating or updating the EventBridge Scheduler schedule in the target account and linking it to the imported Schedule_Asset

## Requirements

### Requirement 1: Manifest Configuration for Catalog Export

**User Story:** As a developer, I want to configure catalog resource export in my manifest.yaml, so that the bundle command knows which catalog resource types to export and with what filters.

#### Acceptance Criteria

1. THE Manifest SHALL support a `content.catalog.export` section that specifies which resource types to export (glossaries, glossaryTerms, formTypes, assetTypes, assets)
2. WHEN a user specifies `content.catalog.export.resourceTypes` in the manifest, THE Bundle_Command SHALL only export the listed resource types
3. WHERE a user specifies `content.catalog.export.updatedAfter` in the manifest, THE Bundle_Command SHALL only export resources with `updatedAt` greater than or equal to the specified ISO 8601 timestamp
4. IF `content.catalog.export` is present but `resourceTypes` is omitted, THEN THE Bundle_Command SHALL export all five supported resource types by default

### Requirement 2: Export Catalog Resources During Bundle

**User Story:** As a developer, I want the bundle command to export DataZone catalog resources from my source project, so that I can promote catalog definitions across stages.

#### Acceptance Criteria

1. WHEN the bundle command runs and `content.catalog.export` is configured, THE Catalog_Exporter SHALL query the DataZone Search_API for Assets and GlossaryTerms owned by the source project
2. WHEN the bundle command runs and `content.catalog.export` is configured, THE Catalog_Exporter SHALL query the DataZone SearchTypes_API for FormTypes and AssetTypes owned by the source project
3. THE Catalog_Exporter SHALL use a sort clause of `{"attribute": "updatedAt", "order": "DESCENDING"}` for all search queries
4. WHERE an `updatedAfter` filter is specified, THE Catalog_Exporter SHALL apply a filter on the `updatedAt` attribute to only include resources modified at or after the specified timestamp
5. THE Catalog_Exporter SHALL handle pagination by following `nextToken` until all matching results are retrieved
6. WHEN the Catalog_Exporter retrieves Glossaries, THE Catalog_Exporter SHALL use the Search_API with `searchScope` set to `GLOSSARY`
7. THE Catalog_Exporter SHALL serialize all retrieved resources into a single `catalog_export.json` file within the bundle archive under a `catalog/` directory

### Requirement 3: Catalog Export JSON Serialization

**User Story:** As a developer, I want the exported catalog data to be stored in a well-structured JSON file, so that it can be reliably read during deployment.

#### Acceptance Criteria

1. THE Catalog_Exporter SHALL produce a JSON file containing a top-level object with keys: `metadata`, `glossaries`, `glossaryTerms`, `formTypes`, `assetTypes`, `assets`, and `scheduleAssets`
2. THE `metadata` section SHALL include `sourceProjectId`, `sourceDomainId`, `exportTimestamp`, and `resourceTypes` fields
3. WHEN serializing each resource, THE Catalog_Exporter SHALL preserve the `name` field, all user-configurable attributes, and the source identifier
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
2. WHEN a resource already exists in the target project (matched by name), THE Catalog_Importer SHALL call the corresponding DataZone update API to synchronize the resource
3. THE Catalog_Importer SHALL create resources in dependency order: FormTypes before AssetTypes, Glossaries before GlossaryTerms, AssetTypes before Assets
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

### Requirement 8: Schedule Asset Export and Import

**User Story:** As a developer, I want schedule assets and their associated EventBridge Scheduler schedules to be exported and imported alongside other catalog resources, so that time-based triggers are promoted across stages.

#### Acceptance Criteria

1. WHEN the Catalog_Exporter encounters an Asset of managed type `SageMakerUnifiedStudioScheduleAssetType`, THE Schedule_Exporter SHALL retrieve the associated EventBridge Scheduler schedule definition using the EventBridge Scheduler `GetSchedule` API
2. THE Schedule_Exporter SHALL serialize the schedule definition (schedule expression, flexible time window, target, state, description, group name) alongside the asset metadata in the `scheduleAssets` array of the Catalog_Export_JSON, separate from the `assets` array
3. WHEN the Catalog_Importer processes a Schedule_Asset, THE Schedule_Importer SHALL create or update the EventBridge Scheduler schedule in the target account using the `CreateSchedule` or `UpdateSchedule` API
4. IF the EventBridge Scheduler schedule already exists in the target account (matched by name and group), THEN THE Schedule_Importer SHALL update the existing schedule with the exported definition
5. IF the EventBridge Scheduler `GetSchedule` API fails during export for a Schedule_Asset, THEN THE Catalog_Exporter SHALL log a warning and export the asset metadata without the schedule definition
6. IF the EventBridge Scheduler `CreateSchedule` or `UpdateSchedule` API fails during import, THEN THE Schedule_Importer SHALL log the error, continue processing remaining resources, and include the failure in the import summary
7. THE Schedule_Importer SHALL remap the schedule target ARN to reference the correct target account and region

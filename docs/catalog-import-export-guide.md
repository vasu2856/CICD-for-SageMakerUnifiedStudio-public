# DataZone Catalog Import/Export Guide

## Overview

The SMUS CI/CD CLI provides catalog import/export capabilities that allow you to promote DataZone catalog resources (Glossaries, GlossaryTerms, FormTypes, AssetTypes, and Assets) across different stages (dev, test, prod) as part of your deployment pipeline.

This feature enables you to:
- Version control your catalog definitions alongside your application code
- Promote catalog resources consistently across environments
- Maintain catalog consistency between development and production
- Automate catalog deployments as part of your CI/CD workflow

## Supported Resource Types

The catalog import/export feature supports the following DataZone resource types:

| Resource Type | Description |
|---|---|
| **Glossaries** | Business glossaries that organize domain-specific terminology |
| **GlossaryTerms** | Individual terms within glossaries, containing definitions and metadata |
| **FormTypes** | Custom metadata form types that define schemas for catalog resources |
| **AssetTypes** | Asset type definitions that specify structure and metadata for categories of assets |
| **Assets** | Catalog assets representing data resources with metadata and forms |
| **Data Products** | Data products that bundle one or more data assets for publishing and sharing |
| **Metadata Forms** | Metadata form definitions with complete model structure including field definitions, data types, constraints, and validation rules |

## How It Works

### Export During Bundle

When you run the `bundle` command, the CLI:

1. Queries the DataZone Search and SearchTypes APIs to retrieve catalog resources from your source project
2. Filters resources by the `updatedAt` timestamp (if configured)
3. Serializes the resources into a `catalog/catalog_export.json` file within the bundle ZIP archive
4. Preserves resource names, metadata, and cross-references for later import

### Import During Deploy

When you run the `deploy` command, the CLI:

1. Extracts the `catalog/catalog_export.json` file from the bundle
2. Builds a name-based mapping between source and target project identifiers
3. Creates or updates resources in the target project in dependency order
4. Resolves cross-references (e.g., GlossaryTerm → Glossary, Asset → AssetType)
5. Reports a summary of created, updated, and failed resources

## Configuration

### Manifest Configuration

To enable catalog export, add `assets`, `glossaries`, `dataProducts`, and/or `metadataForms` sections under `content.catalog` in your `manifest.yaml`:

```yaml
content:
  catalog:
    assets:
      include:              # Optional: defaults to all three types
        - formTypes
        - assetTypes
        - assets
      updatedAfter: "2025-01-01T00:00:00Z"  # Optional: ISO 8601 timestamp filter
    glossaries:
      include:              # Optional: defaults to both types
        - glossaries
        - glossaryTerms
      updatedAfter: "2025-01-01T00:00:00Z"  # Optional: ISO 8601 timestamp filter
    dataProducts:
      names:                # Optional: defaults to all data products
        - "Sales Analytics Product"
        - "Customer Insights Product"
      updatedAfter: "2025-01-01T00:00:00Z"  # Optional: ISO 8601 timestamp filter
    metadataForms:
      include:              # Optional: defaults to all form types
        - formTypes
      updatedAfter: "2025-01-01T00:00:00Z"  # Optional: ISO 8601 timestamp filter
```

### Configuration Options

#### `assets.include` (optional)

Specifies which asset-related resource types to export. If omitted, all three types (formTypes, assetTypes, assets) are exported by default.

**Example: Export only form types and asset types**
```yaml
content:
  catalog:
    assets:
      include:
        - formTypes
        - assetTypes
```

#### `glossaries.include` (optional)

Specifies which glossary-related resource types to export. If omitted, both types (glossaries, glossaryTerms) are exported by default.

**Example: Export only glossaries**
```yaml
content:
  catalog:
    glossaries:
      include:
        - glossaries
```

#### `assets.updatedAfter` (optional)

Filters exported asset-related resources to only include those modified on or after the specified ISO 8601 timestamp. This is useful for incremental exports.

**Example: Export only asset resources modified since January 1, 2025**
```yaml
content:
  catalog:
    assets:
      include:
        - formTypes
        - assetTypes
        - assets
      updatedAfter: "2025-01-01T00:00:00Z"
```

#### `glossaries.updatedAfter` (optional)

Filters exported glossary-related resources to only include those modified on or after the specified ISO 8601 timestamp.

**Example: Export only glossary resources modified since January 1, 2025**
```yaml
content:
  catalog:
    glossaries:
      include:
        - glossaries
        - glossaryTerms
      updatedAfter: "2025-01-01T00:00:00Z"
```

#### `dataProducts.names` (optional)

Specifies which data products to export by name. If omitted, all data products are exported by default.

**Example: Export only specific data products**
```yaml
content:
  catalog:
    dataProducts:
      names:
        - "Sales Analytics Product"
        - "Customer Insights Product"
```

#### `dataProducts.updatedAfter` (optional)

Filters exported data products to only include those modified on or after the specified ISO 8601 timestamp.

**Example: Export only data products modified since January 1, 2025**
```yaml
content:
  catalog:
    dataProducts:
      names:
        - "Sales Analytics Product"
      updatedAfter: "2025-01-01T00:00:00Z"
```

#### `metadataForms.include` (optional)

Specifies which metadata form types to export. If omitted, all form types are exported by default. Metadata forms preserve the complete model structure including all field definitions, data types, constraints, and validation rules.

**Example: Export metadata form types**
```yaml
content:
  catalog:
    metadataForms:
      include:
        - formTypes
```

#### `metadataForms.updatedAfter` (optional)

Filters exported metadata forms to only include those modified on or after the specified ISO 8601 timestamp.

**Example: Export only metadata forms modified since January 1, 2025**
```yaml
content:
  catalog:
    metadataForms:
      include:
        - formTypes
      updatedAfter: "2025-01-01T00:00:00Z"
```

### Deployment Configuration

To control catalog import behavior per stage, use the `deployment_configuration.catalog` section:

```yaml
targets:
  dev:
    deployment_configuration:
      catalog:
        disable: false  # Enable catalog import (default)
  
  prod:
    deployment_configuration:
      catalog:
        disable: true   # Skip catalog import for this stage
```

## Usage

### Basic Workflow

1. **Configure your manifest** with catalog export settings
2. **Run bundle** to export catalog resources from your source project
3. **Run deploy** to import catalog resources into your target project

### Example: Full Deployment Pipeline

```bash
# Step 1: Bundle from dev environment
smus-cli bundle --manifest manifest.yaml

# Step 2: Deploy to test environment
smus-cli deploy --bundle bundle.zip --targets test

# Step 3: Deploy to prod environment
smus-cli deploy --bundle bundle.zip --targets prod
```

### Example: Incremental Export

To export only recently modified resources:

```yaml
content:
  catalog:
    assets:
      updatedAfter: "2025-02-01T00:00:00Z"
    glossaries:
      updatedAfter: "2025-02-01T00:00:00Z"
    dataProducts:
      updatedAfter: "2025-02-01T00:00:00Z"
    metadataForms:
      updatedAfter: "2025-02-01T00:00:00Z"
```

Then run:
```bash
smus-cli bundle --manifest manifest.yaml
```

### Example: Selective Resource Export

To export only specific resource types:

```yaml
content:
  catalog:
    assets:
      include:
        - formTypes
        - assetTypes
    glossaries:
      include:
        - glossaries
    dataProducts:
      names:
        - "Sales Analytics Product"
    metadataForms:
      include:
        - formTypes
```

## Resource Mapping and Dependencies

### Name-Based Identifier Mapping

The import process uses resource names to map source identifiers to target identifiers. When a resource with the same name already exists in the target project, it will be updated rather than creating a duplicate.

**Important:** Resource names must be unique within each resource type in a project.

### Dependency Order

Resources are created in the following dependency order to ensure references are valid:

1. **Metadata Forms** (no dependencies, created before FormTypes)
2. **FormTypes** (no dependencies)
3. **AssetTypes** (may reference FormTypes)
4. **Assets** (reference AssetTypes)
5. **Glossaries** (no dependencies)
6. **GlossaryTerms** (reference Glossaries)
7. **Data Products** (may reference Assets)

### Cross-Reference Resolution

The import process automatically resolves cross-references between resources:

- **GlossaryTerms** → **Glossaries**: `glossaryId` is remapped to the target glossary
- **Assets** → **AssetTypes**: `typeIdentifier` is remapped to the target asset type
- **AssetTypes** → **FormTypes**: Form references are remapped to target form types
- **Data Products** → **Assets**: Asset references are remapped to target assets

## Export JSON Structure

The exported `catalog/catalog_export.json` file has the following structure:

```json
{
  "metadata": {
    "sourceProjectId": "abc123",
    "sourceDomainId": "dzd_xyz789",
    "exportTimestamp": "2025-02-26T10:30:00Z",
    "resourceTypes": ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts", "metadataForms"]
  },
  "glossaries": [
    {
      "sourceId": "gloss_001",
      "name": "Business Glossary",
      "description": "Core business terminology",
      "status": "ENABLED"
    }
  ],
  "glossaryTerms": [
    {
      "sourceId": "term_001",
      "name": "Customer",
      "shortDescription": "A person or organization that purchases goods or services",
      "longDescription": "...",
      "glossaryId": "gloss_001",
      "status": "ENABLED",
      "termRelations": {}
    }
  ],
  "formTypes": [...],
  "assetTypes": [...],
  "assets": [...],
  "dataProducts": [
    {
      "sourceId": "dp_001",
      "name": "Sales Analytics Product",
      "description": "Comprehensive sales data product",
      "items": [...]
    }
  ],
  "metadataForms": [
    {
      "sourceId": "mf_001",
      "name": "Customer Metadata Form",
      "description": "Metadata form for customer data assets",
      "model": {
        "smithy": "string containing complete metadata form structure with all field definitions"
      },
      "revision": "1",
      "status": "ENABLED"
    }
  ]
}
```

## Error Handling

### Export Errors

| Scenario | Behavior |
|---|---|
| DataZone API error | Export fails with descriptive error message |
| No matching resources | Produces valid JSON with empty arrays, logs informational message |
| Missing permissions | Export fails with permission error |

### Import Errors

| Scenario | Behavior |
|---|---|
| Malformed JSON | Validation error before any API calls |
| Individual resource failure | Logs error, continues with remaining resources |
| All resources fail | Deploy reports failure |
| Missing catalog file | Silently skipped (backward compatible) |
| Catalog disabled for stage | Skipped with log message |

### Partial Failures

The import process is resilient to partial failures. If some resources fail to import:

1. The error is logged with resource name, type, and error message
2. Processing continues with remaining resources
3. A summary reports counts of created, updated, and failed resources

**Example output:**
```
Catalog import summary:
  Created: 15
  Updated: 8
  Failed: 2
```

## Best Practices

### 1. Use Version Control

Commit your `manifest.yaml` with catalog export configuration to version control. This ensures catalog definitions are versioned alongside your application code.

### 2. Test in Lower Environments First

Always test catalog changes in dev/test environments before promoting to production:

```bash
# Deploy to dev first
smus-cli deploy --bundle bundle.zip --targets dev

# Verify catalog resources in dev
# Then promote to test
smus-cli deploy --bundle bundle.zip --targets test

# Finally promote to prod
smus-cli deploy --bundle bundle.zip --targets prod
```

### 3. Use Incremental Exports for Large Catalogs

For projects with many catalog resources, use the `updatedAfter` filter to export only recent changes:

```yaml
content:
  catalog:
    assets:
      updatedAfter: "2025-02-20T00:00:00Z"  # Last deployment date
    glossaries:
      updatedAfter: "2025-02-20T00:00:00Z"  # Last deployment date
    metadataForms:
      updatedAfter: "2025-02-20T00:00:00Z"  # Last deployment date
```

### 4. Disable Catalog Import When Not Needed

If a stage doesn't need catalog updates, disable import to speed up deployments:

```yaml
targets:
  prod:
    deployment_configuration:
      catalog:
        disable: true
```

### 5. Maintain Unique Resource Names

Ensure resource names are unique within each type to avoid mapping conflicts. The import process uses names to match resources between environments.

### 6. Review Import Summaries

Always review the import summary after deployment to ensure all resources were created or updated successfully:

```
Catalog import summary:
  Created: 10
  Updated: 5
  Failed: 0
```

## Limitations

### Current Limitations

1. **Schedule Assets Not Supported**: Assets of type `SageMakerUnifiedStudioScheduleAssetType` are not currently supported for import/export
2. **Name-Based Matching Only**: Resources are matched by name only; renaming a resource in the source will create a new resource in the target
3. **No Deletion Support**: The import process does not delete resources that exist in the target but not in the source
4. **Custom Managed Types**: Only custom (non-managed) FormTypes and AssetTypes are exported; AWS-managed types are excluded
5. **Data Product Name Filtering**: Data products can only be filtered by exact name match; pattern matching is not supported

### Workarounds

**For Schedule Assets**: Manually create schedule assets in each environment or use separate automation for schedule management.

**For Resource Deletion**: Manually delete obsolete resources from target projects or use DataZone APIs directly.

**For Resource Renaming**: To rename a resource across environments:
1. Create the resource with the new name in the source
2. Export and deploy to target
3. Manually delete the old resource from both source and target

## Troubleshooting

### Problem: Export produces empty arrays

**Cause**: No resources match the filter criteria (e.g., `updatedAfter` is too recent)

**Solution**: 
- Check the `updatedAfter` timestamp
- Verify resources exist in the source project
- Remove the `updatedAfter` filter to export all resources

### Problem: Import fails with "Malformed JSON" error

**Cause**: The `catalog_export.json` file is corrupted or manually edited incorrectly

**Solution**:
- Re-run the bundle command to regenerate the export
- Do not manually edit the `catalog_export.json` file

### Problem: Resources not updating in target

**Cause**: Resource names don't match between source and target

**Solution**:
- Verify resource names are identical (case-sensitive)
- Check the import summary for "Created" vs "Updated" counts
- Query the target project to confirm existing resource names

### Problem: Cross-references broken after import

**Cause**: Referenced resources (e.g., Glossaries, AssetTypes) were not exported or failed to import

**Solution**:
- Ensure all resource types are included in `resourceTypes`
- Check the import summary for failures
- Verify dependency resources exist in the target project

### Problem: Permission denied during export or import

**Cause**: Insufficient DataZone permissions

**Solution**:
- Verify your IAM role has DataZone permissions:
  - `datazone:Search`
  - `datazone:SearchTypes`
  - `datazone:CreateGlossary`, `datazone:UpdateGlossary`
  - `datazone:CreateGlossaryTerm`, `datazone:UpdateGlossaryTerm`
  - `datazone:CreateFormType`, `datazone:UpdateFormType`
  - `datazone:CreateAssetType`, `datazone:UpdateAssetType`
  - `datazone:CreateAsset`, `datazone:UpdateAsset`
  - `datazone:CreateDataProduct`, `datazone:UpdateDataProduct`

## Additional Resources

- [SMUS CI/CD CLI Documentation](../README.md)
- [Catalog Import/Export Quick Reference](catalog-import-export-quick-reference.md) - Quick reference card with common configurations
- [Manifest Schema Reference](manifest-schema.md)
- [DataZone API Documentation](https://docs.aws.amazon.com/datazone/latest/APIReference/)
- [Example: Catalog Import/Export](../examples/catalog-import-export/)

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section above
2. Review the [GitHub Issues](https://github.com/aws-samples/CICD-for-SageMakerUnifiedStudio/issues)
3. Consult the [SMUS CI/CD documentation](../README.md)

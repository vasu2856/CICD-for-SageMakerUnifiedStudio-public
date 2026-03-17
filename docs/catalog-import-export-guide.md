# DataZone Catalog Import/Export Guide

## Overview

The SMUS CI/CD CLI provides catalog import/export capabilities that allow you to promote DataZone catalog resources (Glossaries, GlossaryTerms, FormTypes, AssetTypes, Assets, and Data Products) across different stages (dev, test, prod) as part of your deployment pipeline.

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

## How It Works

### Export During Bundle

When you run the `bundle` command with catalog export enabled, the CLI:

1. Queries the DataZone Search and SearchTypes APIs to retrieve ALL catalog resources owned by your source project
2. Optionally filters resources by the `--updated-after` CLI flag (if provided)
3. Serializes the resources into a `catalog/catalog_export.json` file within the bundle ZIP archive
4. Preserves resource names, metadata, cross-references, `inputForms`, and `termRelations` for later import

### Import During Deploy

When you run the `deploy` command, the CLI:

1. Extracts the `catalog/catalog_export.json` file from the bundle
2. Builds an identifier mapping between source and target projects using `externalIdentifier` (with normalization) or name as fallback
3. Creates, updates, or deletes resources in the target project in dependency order
4. Resolves cross-references (e.g., GlossaryTerm → Glossary, Asset → AssetType)
5. Optionally publishes assets and data products when `publish: true` is configured
6. Reports a summary of created, updated, deleted, and failed resources

## Configuration

### Manifest Configuration

The manifest `content.catalog` section is intentionally simple — it only supports three fields:

- `enabled` — boolean to turn catalog export on/off
- `publish` — boolean to enable automatic publishing during deploy
- `assets.access` — array for subscription requests (existing functionality)

No filter options (`include`, `names`, `assetTypes`, `updatedAfter`, etc.) exist in the manifest. When enabled, ALL project-owned catalog resources are exported. To filter by date, use the `--updated-after` CLI flag on the bundle command.

```yaml
content:
  catalog:
    enabled: true    # Export ALL project-owned catalog resources
    publish: false   # Automatically publish assets and data products during deploy (default: false)
```

#### With automatic publishing

```yaml
content:
  catalog:
    enabled: true
    publish: true    # Publish assets and data products after import
```

#### With asset subscription requests (existing functionality)

```yaml
content:
  catalog:
    enabled: true
    publish: false
    assets:
      access:
        - selector:
            search:
              assetType: GlueTable
              identifier: covid19_db.countries_aggregated
          permission: READ
          requestReason: Required for analytics pipeline
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

1. **Configure your manifest** with `content.catalog.enabled: true`
2. **Run bundle** to export catalog resources from your source project
3. **Run deploy** to import catalog resources into your target project

### Example: Full Deployment Pipeline

```bash
# Step 1: Bundle from dev environment (exports ALL catalog resources)
smus-cli bundle --manifest manifest.yaml

# Step 2: Deploy to test environment
smus-cli deploy --bundle bundle.zip --targets test

# Step 3: Deploy to prod environment
smus-cli deploy --bundle bundle.zip --targets prod
```

### Example: Incremental Export with --updated-after

To export only recently modified resources, use the `--updated-after` CLI flag on the bundle command. This filters ALL resource types uniformly by modification timestamp.

```bash
# Export only resources modified since February 1, 2025
smus-cli bundle --manifest manifest.yaml --updated-after "2025-02-01T00:00:00Z"
```

The `--updated-after` flag:
- Accepts an ISO 8601 timestamp (e.g., `2025-02-01T00:00:00Z`)
- Filters ALL resource types uniformly (glossaries, assets, form types, etc.)
- Is optional — when omitted, all project-owned resources are exported
- Is a CLI-only option, not a manifest field

### Example: Deploy with Automatic Publishing

```yaml
# manifest.yaml
content:
  catalog:
    enabled: true
    publish: true   # Automatically publish assets and data products
```

```bash
smus-cli bundle --manifest manifest.yaml
smus-cli deploy --bundle bundle.zip --targets test
```

## Resource Mapping and Dependencies

### Identifier Mapping

The import process uses `externalIdentifier` (with normalization) as the primary mapping key between source and target projects. When a resource doesn't have an `externalIdentifier`, the `name` field is used as a fallback.

- **externalIdentifier**: Normalized by removing AWS account ID and region information before matching
- **name**: Used as fallback when `externalIdentifier` is not present

When a matching resource exists in the target project, it is updated. When no match is found, a new resource is created.

### Dependency Order

Resources are created in the following dependency order to ensure references are valid:

1. **Glossaries** (no dependencies)
2. **GlossaryTerms** (reference Glossaries)
3. **FormTypes** (may reference GlossaryTerms)
4. **AssetTypes** (reference FormTypes, may reference GlossaryTerms)
5. **Assets** (reference AssetTypes, may reference GlossaryTerms)

Resources are deleted in reverse dependency order when they exist in the target but not in the bundle.

### Cross-Reference Resolution

The import process automatically resolves cross-references between resources:

- **GlossaryTerms** → **Glossaries**: `glossaryId` is remapped to the target glossary
- **Assets** → **AssetTypes**: `typeIdentifier` is remapped to the target asset type
- **AssetTypes** → **FormTypes**: Form references are remapped to target form types
- **FormTypes/Assets** → **GlossaryTerms**: Glossary term references are remapped

### Resource Deletion

During import, resources that exist in the target project but are NOT present in the bundle are deleted. Deletion follows reverse dependency order to avoid breaking references:

1. Assets
2. AssetTypes
3. FormTypes
4. GlossaryTerms
5. Glossaries

## Export JSON Structure

The exported `catalog/catalog_export.json` file has the following structure:

```json
{
  "metadata": {
    "sourceProjectId": "abc123",
    "sourceDomainId": "dzd_xyz789",
    "exportTimestamp": "2025-02-26T10:30:00Z",
    "resourceTypes": ["glossaries", "glossaryTerms", "formTypes", "assetTypes", "assets", "dataProducts"]
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
  "assets": [
    {
      "sourceId": "asset_001",
      "name": "Customer Data",
      "description": "Customer data asset",
      "typeIdentifier": "at_001",
      "formsInput": [],
      "inputForms": [],
      "externalIdentifier": "arn:aws:..."
    }
  ],
  "dataProducts": [
    {
      "sourceId": "dp_001",
      "name": "Sales Analytics Product",
      "description": "Comprehensive sales data product",
      "items": [...]
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
| Invalid `--updated-after` format | Validation error with helpful message |

### Import Errors

| Scenario | Behavior |
|---|---|
| Malformed JSON | Validation error before any API calls |
| Individual resource failure | Logs error, continues with remaining resources |
| All resources fail | Deploy reports failure |
| Missing catalog file | Silently skipped (backward compatible) |
| Catalog disabled for stage | Skipped with log message |
| Publish API failure | Logs error, continues with remaining resources |
| Deletion failure | Logs error, continues with remaining resources |

### Partial Failures

The import process is resilient to partial failures. If some resources fail to import:

1. The error is logged with resource name, type, and error message
2. Processing continues with remaining resources
3. A summary reports counts of created, updated, deleted, and failed resources

**Example output:**
```
Catalog import summary:
  Created: 15
  Updated: 8
  Deleted: 2
  Failed: 1
  Published: 12
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

### 3. Use --updated-after for Large Catalogs

For projects with many catalog resources, use the `--updated-after` CLI flag to export only recent changes:

```bash
# Export only resources modified since the last deployment
smus-cli bundle --manifest manifest.yaml --updated-after "2025-02-20T00:00:00Z"
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

Ensure resource names are unique within each type to avoid mapping conflicts. The import process uses `externalIdentifier` (with normalization) or names to match resources between environments.

### 6. Review Import Summaries

Always review the import summary after deployment to ensure all resources were created or updated successfully:

```
Catalog import summary:
  Created: 10
  Updated: 5
  Deleted: 0
  Failed: 0
  Published: 8
```

## Limitations

### Current Limitations

1. **Schedule Assets Not Supported**: Assets of type `SageMakerUnifiedStudioScheduleAssetType` are not currently supported for import/export
2. **Custom Managed Types**: Only custom (non-managed) FormTypes and AssetTypes are exported; AWS-managed types are excluded

### Workarounds

**For Schedule Assets**: Manually create schedule assets in each environment or use separate automation for schedule management.

**For Resource Renaming**: To rename a resource across environments:
1. Create the resource with the new name in the source
2. Export and deploy to target
3. The old resource in the target will be deleted automatically (since it's no longer in the bundle)

## Troubleshooting

### Problem: Export produces empty arrays

**Cause**: No resources are owned by the source project, or the `--updated-after` CLI timestamp is too recent

**Solution**: 
- Verify resources exist in the source project and are owned by it
- If using `--updated-after`, try an earlier timestamp or omit the flag to export all resources

### Problem: Import fails with "Malformed JSON" error

**Cause**: The `catalog_export.json` file is corrupted or manually edited incorrectly

**Solution**:
- Re-run the bundle command to regenerate the export
- Do not manually edit the `catalog_export.json` file

### Problem: Resources not updating in target

**Cause**: Resource `externalIdentifier` or names don't match between source and target

**Solution**:
- Verify resource identifiers or names match
- Check the import summary for "Created" vs "Updated" counts
- Query the target project to confirm existing resources

### Problem: Cross-references broken after import

**Cause**: Referenced resources (e.g., Glossaries, AssetTypes) were not exported or failed to import

**Solution**:
- Ensure catalog export is enabled (all resource types are exported automatically)
- Check the import summary for failures
- Verify dependency resources exist in the target project

### Problem: Permission denied during export or import

**Cause**: Insufficient DataZone permissions

**Solution**:
- Verify your IAM role has DataZone permissions:
  - `datazone:Search`
  - `datazone:SearchTypes`
  - `datazone:CreateGlossary`, `datazone:UpdateGlossary`, `datazone:DeleteGlossary`
  - `datazone:CreateGlossaryTerm`, `datazone:UpdateGlossaryTerm`, `datazone:DeleteGlossaryTerm`
  - `datazone:CreateFormType`, `datazone:UpdateFormType`, `datazone:DeleteFormType`
  - `datazone:CreateAssetType`, `datazone:UpdateAssetType`, `datazone:DeleteAssetType`
  - `datazone:CreateAsset`, `datazone:UpdateAsset`, `datazone:DeleteAsset`
  - `datazone:CreateDataProduct`, `datazone:UpdateDataProduct`, `datazone:DeleteDataProduct`

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

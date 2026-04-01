# DataZone Catalog Import/Export Guide

← [Back to Main README](../README.md)

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

## Key Assumption: Physical Resources Must Have the Same Name

> ⚠️ **IMPORTANT**: Catalog import/export assumes that the underlying physical resources (e.g., Glue Tables, Glue Databases, S3 buckets) referenced by your catalog assets **have the same name in both source and target environments**. The import process matches assets across environments using normalized `externalIdentifier` values or resource names. If the physical resource names differ between environments (e.g., `my-table-dev` vs `my-table-prod`), the matching will fail and resources will be created as new rather than updated. **Additionally, any resources that exist in the target project but are not present in the bundle will be deleted during import.** This means mismatched names can cause the original target resource to be deleted and a duplicate to be created. Ensure your infrastructure provisioning uses consistent resource names across stages, or that your naming conventions allow the normalization logic (which strips AWS account IDs and region strings) to produce matching identifiers.

## How It Works

### Export During Bundle

When you run the `bundle` command with catalog export enabled, the CLI:

1. Queries the DataZone Search and SearchTypes APIs to retrieve ALL catalog resources owned by your source project
2. Serializes the resources into a `catalog/catalog_export.json` file within the bundle ZIP archive
3. Preserves resource names, metadata, cross-references, `formsInput`, and `termRelations` for later import

### Import During Deploy

When you run the `deploy` command, the CLI:

1. Extracts the `catalog/catalog_export.json` file from the bundle
2. Builds an identifier mapping between source and target projects using `externalIdentifier` (with normalization) or name as fallback
3. Creates, updates, or deletes resources in the target project in dependency order
4. Resolves cross-references (e.g., GlossaryTerm → Glossary, Asset → AssetType)
5. Publishes assets and data products that were published in the source project (unless `skipPublish: true` is configured), verifying each listing becomes ACTIVE before counting it as published
6. Reports a summary of created, updated, deleted, published, and failed resources

## Configuration

### Manifest Configuration

The manifest `content.catalog` section is intentionally simple — it only supports three fields:

- `enabled` — boolean to turn catalog export on/off
- `skipPublish` — boolean to skip all publishing regardless of source state (default: false)
- `assets.access` — array for subscription requests (existing functionality)

No filter options (`include`, `names`, `assetTypes`, etc.) exist in the manifest. When enabled, ALL project-owned catalog resources are exported.

Publishing behavior: By default, assets and data products are published during import only if they were published (`listingStatus == "ACTIVE"`) in the source project. This preserves the source publish state across environments. After calling the asynchronous publish API (`create_listing_change_set`), the importer polls the resource to verify the listing becomes ACTIVE before counting it as published. If the listing fails (e.g., the underlying physical resource doesn't exist in the target), it is counted as a publish failure. Set `skipPublish: true` to skip all publishing.

```yaml
content:
  catalog:
    enabled: true         # Export ALL project-owned catalog resources
    # skipPublish: false  # Default: publish assets/data products that were published in source
```

#### With publishing skipped (override)

```yaml
content:
  catalog:
    enabled: true
    skipPublish: true   # Skip all publishing regardless of source state
```

#### With asset subscription requests (existing functionality)

```yaml
content:
  catalog:
    enabled: true
    skipPublish: true
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
stages:
  test:
    stage: TEST
    domain:
      region: us-east-1
    project:
      name: test-catalog-project
    deployment_configuration:
      catalog: {}          # Enable catalog import (default)
  
  prod:
    stage: PROD
    domain:
      region: us-east-1
    project:
      name: prod-catalog-project
    deployment_configuration:
      catalog:
        disable: true      # Skip catalog import for this stage
```

## Usage

### Basic Workflow

1. **Configure your manifest** with `content.catalog.enabled: true`
2. **Run bundle** to export catalog resources from your source project
3. **Run deploy** to import catalog resources into your target project

### Example: Full Deployment Pipeline

```bash
# Step 1: Bundle from dev environment (exports ALL catalog resources)
aws-smus-cicd-cli bundle --manifest manifest.yaml

# Step 2: Deploy to test environment
aws-smus-cicd-cli deploy --bundle bundle.zip --targets test

# Step 3: Deploy to prod environment
aws-smus-cicd-cli deploy --bundle bundle.zip --targets prod
```

### Example: Deploy with Publishing Skipped

```yaml
# manifest.yaml
content:
  catalog:
    enabled: true
    skipPublish: true   # Skip all publishing regardless of source state
```

```bash
aws-smus-cicd-cli bundle --manifest manifest.yaml
aws-smus-cicd-cli deploy --bundle bundle.zip --targets test
```

## Resource Mapping and Dependencies

### Identifier Mapping

The import process uses `externalIdentifier` (with normalization) as the primary mapping key between source and target projects. When a resource doesn't have an `externalIdentifier`, the `name` field is used as a fallback.

- **externalIdentifier**: Normalized by removing AWS account ID and region information before matching
- **name**: Used as fallback when `externalIdentifier` is not present

When a matching resource exists in the target project, it is updated. When no match is found, a new resource is created.

> ⚠️ **IMPORTANT**: This mapping assumes that the underlying physical resources (e.g., Glue Tables, S3 buckets) have the **same name** across environments. For example, if a Glue Table is named `analytics_db.customers` in your dev environment, it must also be named `analytics_db.customers` in your test and prod environments for the asset to be correctly matched and updated rather than duplicated.

### Dependency Order

Resources are created in the following dependency order to ensure references are valid:

1. **Glossaries** (no dependencies)
2. **GlossaryTerms** (reference Glossaries)
3. **FormTypes** (may reference GlossaryTerms)
4. **AssetTypes** (reference FormTypes, may reference GlossaryTerms)
5. **Assets** (reference AssetTypes, may reference GlossaryTerms)
6. **Data Products** (may reference Assets)

Resources are deleted in reverse dependency order when they exist in the target but not in the bundle.

### Cross-Reference Resolution

The import process automatically resolves cross-references between resources:

- **GlossaryTerms** → **Glossaries**: `glossaryId` is remapped to the target glossary
- **Assets** → **AssetTypes**: `typeIdentifier` is remapped to the target asset type
- **AssetTypes** → **FormTypes**: Form references are remapped to target form types
- **FormTypes/Assets** → **GlossaryTerms**: Glossary term references are remapped
- **Data Products** → **Assets**: Item references within data products are preserved

### Resource Deletion

During import, resources that exist in the target project but are NOT present in the bundle are deleted. Deletion follows reverse dependency order to avoid breaking references:

1. Data Products
2. Assets
3. AssetTypes
4. FormTypes
5. GlossaryTerms
6. Glossaries

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
      "externalIdentifier": "arn:aws:...",
      "listingStatus": "ACTIVE"
    }
  ],
  "dataProducts": [
    {
      "sourceId": "dp_001",
      "name": "Sales Analytics Product",
      "description": "Comprehensive sales data product",
      "items": [...],
      "listingStatus": "ACTIVE"
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
| Publish API failure | Logs error, continues with remaining resources |
| Publish listing verification FAILED | Listing failed asynchronously (e.g., missing physical resource); logged as publish failure |
| Publish listing verification timeout | Listing did not become ACTIVE within timeout; logged as publish failure |
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

Always test catalog changes in test environments before promoting to production. Since the bundle is created from dev, deploy to test first to validate:

```bash
# Deploy to test first (bundle was created from dev)
aws-smus-cicd-cli deploy --bundle bundle.zip --targets test

# Verify catalog resources in test
# Then promote to prod
aws-smus-cicd-cli deploy --bundle bundle.zip --targets prod
```

### 3. Disable Catalog Import When Not Needed

If a stage doesn't need catalog updates, disable import to speed up deployments:

```yaml
stages:
  prod:
    stage: PROD
    domain:
      region: us-east-1
    project:
      name: prod-project
    deployment_configuration:
      catalog:
        disable: true
```

### 4. Maintain Consistent Physical Resource Names Across Environments

> ⚠️ **IMPORTANT**: The underlying physical resources (Glue Tables, Glue Databases, S3 buckets, etc.) referenced by catalog assets **must have the same name** in all environments. The import process relies on normalized `externalIdentifier` or resource name matching. If physical resource names differ between stages, assets will not be matched correctly.

Ensure resource names are unique within each type to avoid mapping conflicts.

### 5. Review Import Summaries

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

**Cause**: No resources are owned by the source project

**Solution**: 
- Verify resources exist in the source project and are owned by it

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

### Problem: Import fails because a dependency resource doesn't exist

**Cause**: Resources are imported in dependency order (Glossaries → Glossary Terms → Form Types → Asset Types → Assets → Data Products). If a parent resource fails to import, child resources that depend on it will also fail. For example:
- A Glossary Term references a `glossaryId` that doesn't exist in the target project
- An Asset references a `typeIdentifier` (Asset Type) that wasn't exported or failed to import
- A Data Product references items that don't exist in the target

**Error messages** (visible in logs with `--verbose` or `SMUS_LOG_LEVEL=DEBUG`):
```
Failed to import glossaryTerms MyTerm: An error occurred (ValidationException) ...
Failed to import assets MyAsset: An error occurred (ResourceNotFoundException) ...
Failed to import dataProducts MyProduct: An error occurred (ValidationException) ...
```

**Solution**:
- Ensure all resource types are exported — catalog export captures all types automatically when `content.catalog.enabled: true`
- Verify the source project actually owns the dependency resources (only project-owned resources are exported)
- Check the import summary for failures in parent resource types (e.g., if Glossaries show failures, Glossary Terms will likely fail too)
- Re-run the full `bundle` + `deploy` cycle to ensure a consistent export

### Problem: Export returns empty results for a resource type

**Cause**: The DataZone Search or SearchTypes API could not find resources of that type in the source project. Common reasons:
- The resources are not owned by the project (they may be shared from another project)
- The resources were deleted after the last successful export

**Error messages** (visible in logs):
```
No catalog resources found for project <project_id> in domain <domain_id>
Failed to search target glossaries: An error occurred (AccessDeniedException) ...
Failed to search target assets: An error occurred (ResourceNotFoundException) ...
```

**Solution**:
- Verify resources exist in the DataZone console and are owned by the source project
- Check IAM permissions for `datazone:Search` and `datazone:SearchTypes`

### Problem: Partial import success (some resources created, others failed)

**Cause**: The import process is designed to be resilient — it continues importing remaining resources even when individual resources fail. The deploy summary will show a mix of created/updated and failed counts:
```
✅ Catalog import completed:
   Created: 8
   Updated: 2
   Deleted: 0
   Failed: 3
   Published: 7
```

A `Failed` count greater than zero indicates some resources could not be imported. The import only returns a hard failure (`❌ All catalog imports failed`) when every single resource fails.

**Common causes of partial failures**:
- A dependency resource (Glossary, Asset Type) failed, causing its children (Glossary Terms, Assets) to also fail
- A resource name conflicts with an existing resource owned by a different project
- Transient API throttling or service errors for specific resources
- The target project lacks permissions for certain resource types

**How to debug**:
1. Re-run the deploy with verbose logging enabled:
   ```bash
   SMUS_LOG_LEVEL=DEBUG aws-smus-cicd-cli deploy --targets <target-name>
   ```
2. Look for `Failed to import <resourceType> <name>:` lines in the output — these show the exact API error for each failed resource
3. Check if failures cascade from a parent type:
   - If `glossaries` has failures → expect `glossaryTerms` failures too
   - If `formTypes` or `assetTypes` have failures → expect `assets` failures
   - If `assets` have failures → expect `dataProducts` failures (if they reference those assets)
4. Verify the failed resources exist in the source project by checking the `catalog_export.json` in the bundle:
   ```bash
   unzip -p <bundle>.zip catalog/catalog_export.json | python -m json.tool | grep -A5 '"name"'
   ```
5. Check the target project in the DataZone console to see if conflicting resources exist under a different owner
6. If failures are transient (throttling), re-run the deploy — the import is idempotent and will skip already-created resources

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

### Problem: Published count is 0 even though source assets were published

**Cause**: The `create_listing_change_set` API is asynchronous. The import process polls the resource after publishing to verify the listing becomes ACTIVE. If the underlying physical resource (e.g., Glue Table) doesn't exist in the target environment, the listing will fail asynchronously and be counted as a publish failure rather than a success.

**Solution**:
- Verify the physical resources (Glue Tables, S3 buckets, etc.) exist in the target environment with the same names as in the source
- Check the deploy logs for "Listing FAILED" or "Listing verification timed out" messages
- If the physical resources can't be created in the target, use `skipPublish: true` in the manifest to skip publishing

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

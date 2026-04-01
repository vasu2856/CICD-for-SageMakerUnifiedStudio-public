# Catalog Import/Export Example

This example demonstrates how to use the SMUS CI/CD CLI to export and import DataZone catalog resources (glossaries, glossary terms, form types, asset types, assets, and data products) across stages.

## Overview

When `content.catalog.enabled` is set to `true` in the manifest, the `bundle` command exports **all** catalog resources owned by the source project. During `deploy`, those resources are imported into the target project using identifier mapping (via `externalIdentifier` or `name` fallback).

> ⚠️ **IMPORTANT**: This feature assumes that the underlying physical resources (e.g., Glue Tables, Glue Databases, S3 buckets) have the **same name** in both source and target environments. If physical resource names differ between stages, asset matching will fail and resources will be created as new instead of updated.

### Source-State-Based Publishing

By default, the deploy command publishes imported assets and data products only if they were published (`listingStatus == "ACTIVE"`) in the source project. After calling the asynchronous publish API, the importer verifies the listing becomes ACTIVE before counting it as published. This preserves the source publish state across environments. To skip all publishing regardless of source state, set `skipPublish: true` in the manifest.

### Manifest Configuration

The `content.catalog` section supports only three fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable/disable catalog export during bundle |
| `skipPublish` | boolean | `false` | When true, skip all publishing regardless of source state |
| `assets.access` | array | `[]` | Subscription access requests (unchanged from existing behavior) |

No filter options (`include`, `names`, `assetTypes`, etc.) exist in the manifest.

## Setup

### 1. Prepare Catalog Resources

Ensure your source project has catalog resources (glossaries, glossary terms, form types, asset types, assets, data products). For setting up sample catalog resources, refer to the MaxdomeCatalogSamplesSetup Brazil package.

### 2. Bundle

```bash
smus-cli bundle --manifest examples/catalog-import-export/manifest.yaml
```

### 3. Deploy

```bash
# Deploy to dev
smus-cli deploy --manifest examples/catalog-import-export/manifest.yaml --targets dev

# Deploy to test (creates project if needed)
smus-cli deploy --manifest examples/catalog-import-export/manifest.yaml --targets test

# Deploy to prod
smus-cli deploy --manifest examples/catalog-import-export/manifest.yaml --targets prod
```

### 4. Run Validation Tests

```bash
smus-cli test --manifest examples/catalog-import-export/manifest.yaml --targets test
```

## Deployment Configuration

Each stage includes `deployment_configuration.catalog: {}` to enable catalog import. To disable catalog import for a specific stage, set:

```yaml
deployment_configuration:
  catalog:
    disable: true
```

## How It Works

1. **Bundle**: Exports all project-owned catalog resources to `catalog/catalog_export.json` in the bundle ZIP
2. **Deploy**: Reads the exported JSON, maps source identifiers to target identifiers, and creates/updates/deletes resources in dependency order (Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → Data Products)
3. **Publish** (default): Publishes assets and data products that were published in the source project (skip with `skipPublish: true`)
4. **Delete**: Resources in the target project that are not in the bundle are deleted (reverse dependency order: Data Products → Assets → AssetTypes → FormTypes → GlossaryTerms → Glossaries)

## Resource Types

The following catalog resource types are exported and imported:

- **Glossaries** — Business glossaries organizing domain terminology
- **Glossary Terms** — Individual terms within glossaries (with term relations)
- **Form Types** — Custom metadata form schemas (with complete model definitions)
- **Asset Types** — Asset type definitions
- **Assets** — Data assets with metadata forms and glossary term associations
- **Data Products** — Bundled data products for publishing and sharing

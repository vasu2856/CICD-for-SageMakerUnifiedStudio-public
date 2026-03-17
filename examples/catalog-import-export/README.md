# Catalog Import/Export Example

This example demonstrates how to use the SMUS CI/CD CLI to export and import DataZone catalog resources (glossaries, glossary terms, form types, asset types, assets, and data products) across stages.

## Overview

When `content.catalog.enabled` is set to `true` in the manifest, the `bundle` command exports **all** catalog resources owned by the source project. During `deploy`, those resources are imported into the target project using identifier mapping (via `externalIdentifier` or `name` fallback).

### Automatic Publishing

Setting `content.catalog.publish: true` in the manifest causes the deploy command to automatically publish all imported assets and data products after creation or update. This is useful for making catalog resources immediately discoverable in the target environment.

### Manifest Configuration

The `content.catalog` section supports only three fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable/disable catalog export during bundle |
| `publish` | boolean | `false` | Automatically publish assets and data products during deploy |
| `assets.access` | array | `[]` | Subscription access requests (unchanged from existing behavior) |

No filter options (`include`, `names`, `assetTypes`, `updatedAfter`, etc.) exist in the manifest.

## Filtering with `--updated-after`

The **only** way to filter exported catalog resources is via the `--updated-after` CLI flag on the `bundle` command. This flag accepts an ISO 8601 timestamp and filters **all** resource types uniformly by their `updatedAt` timestamp.

```bash
# Export only resources modified after a specific date
smus-cli bundle --manifest examples/catalog-import-export/manifest.yaml \
    --updated-after 2024-06-01T00:00:00Z

# Export all resources (no filter)
smus-cli bundle --manifest examples/catalog-import-export/manifest.yaml
```

## Setup

### 1. Seed Sample Data (Optional)

Use the seed script to populate your source project with sample catalog resources:

```bash
python examples/catalog-import-export/seed_catalog_data.py \
    --domain-id <your-domain-id> \
    --project-id <your-project-id> \
    --region us-east-1
```

The script is idempotent — it skips resources that already exist.

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
3. **Publish** (when enabled): Automatically publishes assets and data products after import
4. **Delete**: Resources in the target project that are not in the bundle are deleted (reverse dependency order: Data Products → Assets → AssetTypes → FormTypes → GlossaryTerms → Glossaries)

## Resource Types

The following catalog resource types are exported and imported:

- **Glossaries** — Business glossaries organizing domain terminology
- **Glossary Terms** — Individual terms within glossaries (with term relations)
- **Form Types** — Custom metadata form schemas (with complete model definitions)
- **Asset Types** — Asset type definitions
- **Assets** — Data assets with metadata forms and glossary term associations
- **Data Products** — Bundled data products for publishing and sharing

# Catalog Import/Export Quick Reference

## Quick Start

### 1. Enable Catalog Export

Add to your `manifest.yaml`:

```yaml
content:
  catalog:
    enabled: true    # Export ALL project-owned catalog resources
    publish: false   # Optional: auto-publish assets and data products during deploy
```

That's it — no filter options in the manifest. When enabled, all project-owned resources are exported.

### 2. Bundle and Deploy

```bash
# Bundle from source (exports ALL catalog resources)
smus-cli bundle --manifest manifest.yaml

# Deploy to target
smus-cli deploy --bundle bundle.zip --targets test
```

## Supported Resources

| Type | Description |
|---|---|
| `glossaries` | Business glossaries |
| `glossaryTerms` | Terms within glossaries |
| `formTypes` | Custom metadata schemas |
| `assetTypes` | Asset type definitions |
| `assets` | Catalog assets |
| `dataProducts` | Data products bundling assets |

## Manifest Configuration

The `content.catalog` section only supports these fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Enable/disable catalog export |
| `publish` | boolean | `false` | Auto-publish assets and data products during deploy |
| `assets.access` | array | — | Subscription requests (existing functionality) |

No filter options (`include`, `names`, `assetTypes`, `updatedAfter`) exist in the manifest.

### Enable export

```yaml
content:
  catalog:
    enabled: true
```

### Enable export with auto-publishing

```yaml
content:
  catalog:
    enabled: true
    publish: true
```

### With subscription requests

```yaml
content:
  catalog:
    enabled: true
    assets:
      access:
        - selector:
            search:
              assetType: GlueTable
              identifier: covid19_db.countries_aggregated
          permission: READ
          requestReason: Required for analytics pipeline
```

### Disable import for a stage

```yaml
targets:
  prod:
    deployment_configuration:
      catalog:
        disable: true
```

## Incremental Export with --updated-after

Use the `--updated-after` CLI flag to filter by modification date. This is a CLI-only option (not a manifest field) that filters ALL resource types uniformly.

```bash
# Export only resources modified since a specific date
smus-cli bundle --manifest manifest.yaml --updated-after "2025-02-01T00:00:00Z"

# Export all resources (no date filter)
smus-cli bundle --manifest manifest.yaml
```

## Dependency Order

Resources are created in this order:

```
Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → Data Products
```

Resources are deleted in reverse order when missing from the bundle.

## Cross-References

Automatically resolved:
- GlossaryTerms → Glossaries
- Assets → AssetTypes
- AssetTypes → FormTypes
- FormTypes/Assets → GlossaryTerms
- Data Products → Assets (item references preserved)

## Common Commands

```bash
# Bundle with catalog export
smus-cli bundle --manifest manifest.yaml

# Bundle with incremental export (CLI flag, not manifest)
smus-cli bundle --manifest manifest.yaml --updated-after "2025-02-01T00:00:00Z"

# Deploy to dev
smus-cli deploy --bundle bundle.zip --targets dev

# Deploy to multiple stages
smus-cli deploy --bundle bundle.zip --targets dev,test,prod
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Empty export | Verify resources exist and are owned by the project. If using `--updated-after`, try an earlier timestamp or omit the flag. |
| Malformed JSON error | Re-run bundle command |
| Resources not updating | Verify `externalIdentifier` or names match exactly |
| Permission denied | Check IAM permissions for DataZone APIs |
| Cross-references broken | Ensure catalog export is enabled (all types exported automatically) |

## Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "datazone:Search",
        "datazone:SearchTypes",
        "datazone:CreateGlossary",
        "datazone:UpdateGlossary",
        "datazone:DeleteGlossary",
        "datazone:CreateGlossaryTerm",
        "datazone:UpdateGlossaryTerm",
        "datazone:DeleteGlossaryTerm",
        "datazone:CreateFormType",
        "datazone:UpdateFormType",
        "datazone:DeleteFormType",
        "datazone:CreateAssetType",
        "datazone:UpdateAssetType",
        "datazone:DeleteAssetType",
        "datazone:CreateAsset",
        "datazone:UpdateAsset",
        "datazone:DeleteAsset",
        "datazone:CreateDataProduct",
        "datazone:UpdateDataProduct",
        "datazone:DeleteDataProduct"
      ],
      "Resource": "*"
    }
  ]
}
```

## Best Practices

1. ✅ Test in dev/test before prod
2. ✅ Use `--updated-after` CLI flag for incremental exports of large catalogs
3. ✅ Maintain unique resource names
4. ✅ Review import summaries
5. ✅ Version control your manifest
6. ✅ Disable import when not needed

## Limitations

- ❌ Schedule assets not supported
- ❌ AWS-managed types excluded

## Example Output

```
Catalog import summary:
  Created: 15
  Updated: 8
  Deleted: 2
  Failed: 0
  Published: 12
```

## More Information

- [SMUS CI/CD CLI Documentation](../README.md) - Main documentation
- [Full Catalog Import/Export Guide](catalog-import-export-guide.md) - Complete guide with detailed explanations
- [Manifest Schema Reference](manifest-schema.md) - YAML schema reference
- [Example Application](../examples/catalog-import-export/) - Working example

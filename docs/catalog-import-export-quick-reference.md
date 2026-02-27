# Catalog Import/Export Quick Reference

## Quick Start

### 1. Enable Catalog Export

Add to your `manifest.yaml`:

```yaml
content:
  catalog:
    assets:
      include:  # Optional: defaults to all
        - formTypes
        - assetTypes
        - assets
    glossaries:
      include:  # Optional: defaults to all
        - glossaries
        - glossaryTerms
    dataProducts:
      names:    # Optional: defaults to all
        - "Sales Analytics Product"
    metadataForms:
      include:  # Optional: defaults to all
        - formTypes
```

### 2. Bundle and Deploy

```bash
# Bundle from source
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
| `metadataForms` | Metadata forms with complete model structure |

## Common Configurations

### Export All Resources

```yaml
content:
  catalog:
    assets: {}       # Defaults to all asset resource types
    glossaries: {}   # Defaults to all glossary resource types
    dataProducts: {} # Defaults to all data products
    metadataForms: {} # Defaults to all metadata forms
```

### Export Specific Types Only

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
        - "Customer Insights Product"
    metadataForms:
      include:
        - formTypes
```

### Incremental Export (Recent Changes Only)

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

### Disable Import for a Stage

```yaml
targets:
  prod:
    deployment_configuration:
      catalog:
        disable: true
```

## Dependency Order

Resources are created in this order:

```
Metadata Forms → FormTypes → AssetTypes → Assets
Glossaries → GlossaryTerms
Data Products (after Assets)
```

## Cross-References

Automatically resolved:
- GlossaryTerms → Glossaries
- Assets → AssetTypes
- AssetTypes → FormTypes
- AssetTypes → Metadata Forms
- Data Products → Assets

## Common Commands

```bash
# Bundle with catalog export
smus-cli bundle --manifest manifest.yaml

# Deploy to dev
smus-cli deploy --bundle bundle.zip --targets dev

# Deploy to multiple stages
smus-cli deploy --bundle bundle.zip --targets dev,test,prod
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Empty export | Check `updatedAfter` filter or verify resources exist |
| Malformed JSON error | Re-run bundle command |
| Resources not updating | Verify names match exactly (case-sensitive) |
| Permission denied | Check IAM permissions for DataZone APIs |
| Cross-references broken | Ensure all resource types are exported |

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
        "datazone:CreateGlossaryTerm",
        "datazone:UpdateGlossaryTerm",
        "datazone:CreateFormType",
        "datazone:UpdateFormType",
        "datazone:CreateAssetType",
        "datazone:UpdateAssetType",
        "datazone:CreateAsset",
        "datazone:UpdateAsset",
        "datazone:CreateDataProduct",
        "datazone:UpdateDataProduct",
        "datazone:CreateMetadataForm",
        "datazone:UpdateMetadataForm"
      ],
      "Resource": "*"
    }
  ]
}
```

## Best Practices

1. ✅ Test in dev/test before prod
2. ✅ Use incremental exports for large catalogs
3. ✅ Maintain unique resource names
4. ✅ Review import summaries
5. ✅ Version control your manifest
6. ✅ Disable import when not needed

## Limitations

- ❌ Schedule assets not supported
- ❌ No resource deletion
- ❌ Name-based matching only
- ❌ AWS-managed types excluded

## Example Output

```
Catalog import summary:
  Created: 15
  Updated: 8
  Failed: 0
```

## More Information

- [SMUS CI/CD CLI Documentation](../README.md) - Main documentation
- [Full Catalog Import/Export Guide](catalog-import-export-guide.md) - Complete guide with detailed explanations
- [Manifest Schema](manifest-schema.md) - YAML schema reference
- [Example Application](../examples/catalog-import-export/) - Working example

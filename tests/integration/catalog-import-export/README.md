# Catalog Import/Export Integration Tests

This directory contains integration tests for the DataZone catalog import/export functionality.

## Prerequisites

### Required Projects

The integration tests require pre-existing DataZone projects in a test domain. The projects must be created manually before running the tests.

#### For Export Tests (`test_catalog_export.py`)

Projects required (as defined in `manifest.yaml`):
- `catalog-export-test-dev` - Source project for export tests
- `catalog-export-test-test` - Target project for export tests
- `catalog-export-test-disabled` - Project with catalog import disabled

#### For Import Tests (`test_catalog_import.py`)

Projects required (as defined in `manifest-import.yaml`):
- `catalog-import-test-source` - Source project for import tests
- `catalog-import-test-target` - Target project for import tests
- `catalog-import-test-disabled` - Project with catalog import disabled

### Domain Requirements

All projects must be created in a DataZone domain that has the following tag:
- Key: `purpose`
- Value: `smus-cicd-testing`

The tests will automatically discover this domain by searching for the tag.

### Environment Variables

Set the following environment variable before running tests:
```bash
export DEV_DOMAIN_REGION=us-east-1  # or your domain's region
```

## Creating Test Projects

### Manual Creation via AWS Console

1. Navigate to the DataZone console
2. Select the domain tagged with `purpose=smus-cicd-testing`
3. Create the required projects with the exact names listed above
4. Ensure the projects are in ACTIVE state

### Manual Creation via AWS CLI

For V2 domains, you'll need a project profile ID. First, list available profiles:

```bash
aws datazone list-project-profiles \
  --domain-identifier <domain-id> \
  --region us-east-1
```

Then create each project:

```bash
# For export tests
aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-export-test-dev \
  --project-profile-id <profile-id> \
  --region us-east-1

aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-export-test-test \
  --project-profile-id <profile-id> \
  --region us-east-1

aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-export-test-disabled \
  --project-profile-id <profile-id> \
  --region us-east-1

# For import tests
aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-import-test-source \
  --project-profile-id <profile-id> \
  --region us-east-1

aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-import-test-target \
  --project-profile-id <profile-id> \
  --region us-east-1

aws datazone create-project \
  --domain-identifier <domain-id> \
  --name catalog-import-test-disabled \
  --project-profile-id <profile-id> \
  --region us-east-1
```

## Running the Tests

### Run Export Tests

```bash
pytest tests/integration/catalog-import-export/test_catalog_export.py -v
```

### Run Import Tests

```bash
pytest tests/integration/catalog-import-export/test_catalog_import.py -v
```

### Run All Catalog Tests

```bash
pytest tests/integration/catalog-import-export/ -v
```

## Test Behavior

### Export Tests

1. Deploy to the dev project to ensure it exists
2. Create sample catalog resources (glossaries, terms, form types)
3. Bundle the project (exports catalog resources)
4. Verify the bundle contains `catalog/catalog_export.json`
5. Verify the JSON structure and content

### Import Tests

1. Deploy to the dev project (source)
2. Create sample catalog resources in the source project
3. Bundle from the source project
4. Deploy the bundle to the test project (target)
5. Verify resources are imported into the target project
6. Verify deploy output reports import summary

## Cleanup

The tests do NOT automatically delete the projects or catalog resources. You may want to periodically clean up:

1. Delete catalog resources created during tests
2. Keep the projects for future test runs (they are reused)

To delete projects manually:

```bash
aws datazone delete-project \
  --domain-identifier <domain-id> \
  --identifier <project-id> \
  --region us-east-1
```

## Troubleshooting

### "Project not found and create=false"

This means the required projects don't exist. Create them following the instructions above.

### "Project profile id required to create project in V2 domain"

This error occurs if you try to create projects programmatically in a V2 domain without a project profile. Use the manual creation steps above.

### "No domain found with purpose=smus-cicd-testing tag"

Ensure your test domain has the required tag. Add it via the console or CLI:

```bash
aws datazone tag-resource \
  --resource-arn <domain-arn> \
  --tags purpose=smus-cicd-testing \
  --region us-east-1
```

### Permission Errors

Ensure your IAM role has the following permissions:
- `datazone:CreateProject`
- `datazone:DeleteProject`
- `datazone:GetProject`
- `datazone:ListProjects`
- `datazone:CreateGlossary`
- `datazone:CreateGlossaryTerm`
- `datazone:CreateFormType`
- `datazone:Search`
- `datazone:SearchTypes`

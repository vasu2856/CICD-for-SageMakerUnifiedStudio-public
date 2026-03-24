# Requirements Document

## Introduction

The Deploy Dry Run feature adds a `--dry-run` option to the existing `smus-cicd deploy` command. When enabled, the CLI walks through every phase of the deployment pipeline — manifest loading, bundle exploration, project initialization, storage deployment, git deployment, catalog import, QuickSight dashboard deployment, workflow creation, and bootstrap actions — without creating, modifying, or deleting any actual resources. It also proactively verifies IAM permissions, S3 bucket accessibility, DataZone domain/project reachability, and catalog asset availability, producing a structured report of what would happen and any issues detected. The goal is to let operators confirm a deployment will succeed before committing to it, avoiding partial deployment failures.

## Glossary

- **CLI**: The `smus-cicd` command-line interface built with Typer.
- **Dry_Run_Engine**: The component that orchestrates all dry-run validation checks across deployment phases.
- **Manifest**: A YAML file (`manifest.yaml`) that declares the application name, content sources, stages, and deployment configuration.
- **Bundle**: A ZIP archive containing storage files, git snapshots, workflow definitions, and catalog export data to be deployed.
- **Target_Stage**: A named stage within the manifest (e.g., `dev`, `staging`, `prod`) that defines domain, project, and deployment configuration for a specific environment.
- **Deployment_Configuration**: The section of a Target_Stage that specifies storage items, git items, and other resources to deploy.
- **Dry_Run_Report**: A structured output summarizing all planned actions, validation results, warnings, and errors discovered during the dry run.
- **Permission_Checker**: The component responsible for verifying that the current IAM identity has the required permissions for each deployment phase.
- **Catalog_Export**: A JSON file inside the bundle that describes DataZone catalog resources (glossaries, glossary terms, custom asset types, form types, data products) to be imported.
- **Dependency_Checker**: The component responsible for verifying that pre-existing AWS resources and DataZone types referenced by catalog export data exist in the target environment.
- **Glue_Data_Catalog_Resource**: Any AWS Glue Data Catalog resource referenced by catalog export assets, including Glue tables, Glue views, and Glue databases. These resources are identified by form types such as `GlueTableFormType` (which covers both tables and views, distinguished by the `tableType` field in the form content) and are expected to exist in the target AWS account with the same names as in the source environment.
- **Bootstrap_Actions**: Post-deployment actions defined in the manifest (e.g., `workflow.run`, `quicksight.refresh`) that execute after bundle deployment.
- **Pre_Deployment_Validation**: An automatic dry-run validation step that runs before the actual deployment begins, using the same Dry_Run_Engine to catch errors early and prevent partial deployments.

## Requirements

### Requirement 1: Dry Run CLI Option

**User Story:** As a DevOps engineer, I want to pass a `--dry-run` flag to the deploy command, so that I can preview the deployment without making changes.

#### Acceptance Criteria

1. WHEN the `--dry-run` flag is provided, THE CLI SHALL execute the deploy command in dry-run mode without creating, modifying, or deleting any resources.
2. WHEN the `--dry-run` flag is not provided, THE CLI SHALL execute the deploy command with its current behavior unchanged, preceded by an automatic dry-run validation step (see Requirement 14).
3. THE CLI SHALL accept the `--dry-run` flag in combination with all existing deploy options (`--manifest`, `--targets`, `--bundle-archive-path`, `--emit-events/--no-events`, `--event-bus-name`).
4. WHEN the `--dry-run` flag is provided, THE CLI SHALL suppress EventBridge event emission regardless of the `--emit-events` setting.
5. THE CLI SHALL accept a `--skip-validation` flag that, when provided, skips the automatic pre-deployment dry-run validation step and proceeds directly to deployment.

### Requirement 2: Manifest and Target Validation

**User Story:** As a DevOps engineer, I want the dry run to validate my manifest file and target stage configuration, so that I can catch configuration errors before deployment.

#### Acceptance Criteria

1. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL load and parse the Manifest file and report any YAML syntax or schema validation errors.
2. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL resolve the Target_Stage and verify that the specified domain, project, and Deployment_Configuration sections are present and well-formed.
3. IF the Manifest file does not exist or is unreadable, THEN THE Dry_Run_Engine SHALL report the file path and the specific error encountered.
4. IF the specified Target_Stage does not exist in the Manifest, THEN THE Dry_Run_Engine SHALL report the missing stage name and list available stages.
5. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL resolve and validate all environment variable references (`${VAR_NAME}` and `$VAR_NAME`) in the Manifest and report any unresolved variables.

### Requirement 3: Bundle Artifact Exploration

**User Story:** As a DevOps engineer, I want the dry run to inspect the bundle archive, so that I can verify all expected artifacts are present before deployment.

#### Acceptance Criteria

1. WHEN a bundle archive path is provided, THE Dry_Run_Engine SHALL open the bundle archive and enumerate all files contained within it.
2. WHEN a bundle archive path is not provided, THE Dry_Run_Engine SHALL attempt to locate the bundle in the `./artifacts` directory using the same resolution logic as the deploy command.
3. THE Dry_Run_Engine SHALL verify that each storage item referenced in the Deployment_Configuration has corresponding files in the bundle or on the local filesystem.
4. THE Dry_Run_Engine SHALL verify that each git item referenced in the Deployment_Configuration has corresponding content in the bundle or is accessible via the configured repository URL.
5. IF a referenced artifact is missing from the bundle, THEN THE Dry_Run_Engine SHALL report the missing artifact name and the expected location within the bundle.
6. WHEN the bundle contains a `catalog/catalog_export.json` file, THE Dry_Run_Engine SHALL validate the Catalog_Export JSON structure against the expected schema.

### Requirement 4: Permission Verification

**User Story:** As a DevOps engineer, I want the dry run to check IAM permissions for all deployment operations, so that I can identify permission gaps before the actual deployment.

#### Acceptance Criteria

1. WHEN dry-run mode is active, THE Permission_Checker SHALL verify that the current IAM identity has `s3:PutObject` and `s3:GetObject` permissions on each target S3 bucket referenced in the Deployment_Configuration.
2. WHEN dry-run mode is active, THE Permission_Checker SHALL verify that the current IAM identity has DataZone permissions (`datazone:GetDomain`, `datazone:GetProject`, `datazone:SearchListings`) required for the target domain and project.
3. WHEN the Deployment_Configuration includes catalog assets, THE Permission_Checker SHALL verify that the current IAM identity has catalog import permissions (`datazone:CreateAsset`, `datazone:CreateGlossary`, `datazone:CreateGlossaryTerm`, `datazone:CreateFormType`).
4. WHEN the manifest configures IAM role creation or update, THE Permission_Checker SHALL verify that the current IAM identity has `iam:CreateRole`, `iam:AttachRolePolicy`, and `iam:PutRolePolicy` permissions.
5. WHEN the manifest configures QuickSight dashboard deployment, THE Permission_Checker SHALL verify that the current IAM identity has QuickSight permissions (`quicksight:DescribeDashboard`, `quicksight:CreateDashboard`, `quicksight:UpdateDashboard`).
6. IF any required permission is missing, THEN THE Permission_Checker SHALL report the specific permission, the target resource ARN, and the AWS service involved.
7. WHEN the Deployment_Configuration includes catalog assets, THE Permission_Checker SHALL verify that the current IAM identity has DataZone grant permissions (`datazone:CreateSubscriptionGrant`, `datazone:GetSubscriptionGrant`, `datazone:CreateSubscriptionRequest`) required for catalog resource subscriptions.
8. WHEN the manifest configures Bootstrap_Actions of type `workflow.create`, `workflow.run`, `workflow.logs`, or `workflow.monitor`, THE Permission_Checker SHALL verify that the current IAM identity has `airflow-serverless:CreateWorkflow`, `airflow-serverless:CreateWorkflowRun`, `airflow-serverless:GetWorkflow`, `logs:GetLogEvents`, and `logs:FilterLogEvents` permissions.
9. WHEN the manifest configures Bootstrap_Actions of type `quicksight.refresh_dataset`, THE Permission_Checker SHALL verify that the current IAM identity has `quicksight:CreateIngestion`, `quicksight:DescribeIngestion`, and `quicksight:ListDataSets` permissions.
10. WHEN the manifest configures Bootstrap_Actions of type `eventbridge.put_events`, THE Permission_Checker SHALL verify that the current IAM identity has `events:PutEvents` permission.
11. WHEN the manifest configures Bootstrap_Actions of type `project.create_environment`, THE Permission_Checker SHALL verify that the current IAM identity has `datazone:CreateEnvironment` permission.
12. WHEN the manifest configures Bootstrap_Actions of type `project.create_connection`, THE Permission_Checker SHALL verify that the current IAM identity has `datazone:CreateConnection` permission.
13. WHEN the Deployment_Configuration includes catalog assets with Glue_Data_Catalog_Resource references, THE Permission_Checker SHALL verify that the current IAM identity has `glue:GetTable`, `glue:GetDatabase`, and `glue:GetPartitions` permissions required for pre-existing resource dependency validation.

### Requirement 5: Deployment Phase Simulation

**User Story:** As a DevOps engineer, I want the dry run to walk through each deployment phase and report what would happen, so that I can understand the full deployment plan.

#### Acceptance Criteria

1. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL simulate the project initialization phase and report whether the target project exists or would be created.
2. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL simulate storage deployment and report the target S3 bucket, prefix, and file count for each storage item.
3. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL simulate git deployment and report the target connection, repository, and file count for each git item.
4. WHEN dry-run mode is active AND the bundle contains catalog export data, THE Dry_Run_Engine SHALL simulate catalog import and report the count and types of catalog resources that would be created, updated, or deleted.
5. WHEN dry-run mode is active AND the manifest configures QuickSight dashboards, THE Dry_Run_Engine SHALL simulate QuickSight deployment and report which dashboards would be exported and imported.
6. WHEN dry-run mode is active AND the manifest configures Bootstrap_Actions, THE Dry_Run_Engine SHALL list each bootstrap action that would execute, including its type and parameters.
7. THE Dry_Run_Engine SHALL execute all simulation phases in the same order as the actual deploy command: manifest loading, project initialization, QuickSight deployment, bundle deployment (storage, git, catalog), workflow validation, and bootstrap actions.

### Requirement 6: Connectivity and Reachability Checks

**User Story:** As a DevOps engineer, I want the dry run to verify that target AWS resources are reachable, so that I can detect network or configuration issues before deployment.

#### Acceptance Criteria

1. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL verify that the target DataZone domain is reachable by calling `datazone:GetDomain`.
2. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL verify that the target DataZone project exists or that project creation is enabled in the manifest.
3. WHEN dry-run mode is active, THE Dry_Run_Engine SHALL verify that each target S3 bucket exists and is accessible by calling `s3:HeadBucket`.
4. WHEN dry-run mode is active AND the manifest configures Airflow workflows, THE Dry_Run_Engine SHALL verify that the Airflow environment is reachable.
5. IF any target resource is unreachable, THEN THE Dry_Run_Engine SHALL report the resource identifier, the AWS service, and the specific error returned.

### Requirement 7: Dry Run Report Output

**User Story:** As a DevOps engineer, I want the dry run to produce a clear, structured report, so that I can quickly assess deployment readiness.

#### Acceptance Criteria

1. THE Dry_Run_Report SHALL include a summary section listing the total count of planned actions, warnings, and errors.
2. THE Dry_Run_Report SHALL organize findings by deployment phase (manifest validation, project initialization, storage deployment, git deployment, catalog import, dependency validation, QuickSight deployment, workflow validation, bootstrap actions).
3. THE Dry_Run_Report SHALL classify each finding as one of: `OK` (check passed), `WARNING` (non-blocking issue), or `ERROR` (blocking issue that would cause deployment failure).
4. WHEN all checks pass with no errors, THE CLI SHALL exit with exit code 0 and display a success message indicating the deployment is expected to succeed.
5. WHEN one or more errors are detected, THE CLI SHALL exit with a non-zero exit code and display a failure message indicating the deployment would fail.
6. THE CLI SHALL output the Dry_Run_Report in human-readable text format by default.
7. WHERE the `--output json` option is provided, THE CLI SHALL output the Dry_Run_Report in machine-readable JSON format.

### Requirement 8: Catalog Export Validation

**User Story:** As a DevOps engineer, I want the dry run to validate catalog export data in the bundle, so that I can catch catalog import issues before deployment.

#### Acceptance Criteria

1. WHEN the bundle contains a Catalog_Export file, THE Dry_Run_Engine SHALL validate that each resource entry contains the required fields (`type`, `name`, `identifier`).
2. WHEN the bundle contains a Catalog_Export file, THE Dry_Run_Engine SHALL verify that all cross-references between catalog resources (e.g., glossary terms referencing glossaries, assets referencing form types) are resolvable.
3. IF the Catalog_Export file contains invalid JSON, THEN THE Dry_Run_Engine SHALL report the parse error and the location within the file.
4. WHEN the bundle contains a Catalog_Export file, THE Dry_Run_Engine SHALL report the count of each resource type (glossaries, glossary terms, custom asset types, form types, data products) that would be imported.

### Requirement 9: Workflow File Validation

**User Story:** As a DevOps engineer, I want the dry run to validate workflow files in the bundle, so that I can catch workflow definition errors before deployment.

#### Acceptance Criteria

1. WHEN the bundle or local filesystem contains workflow YAML files, THE Dry_Run_Engine SHALL validate that each file is valid YAML.
2. WHEN the bundle or local filesystem contains workflow YAML files, THE Dry_Run_Engine SHALL verify that each workflow file conforms to the expected Airflow DAG structure by checking for required top-level keys.
3. WHEN environment variable references exist in workflow files, THE Dry_Run_Engine SHALL verify that all referenced variables are defined in the Target_Stage environment_variables configuration.
4. IF a workflow file contains invalid YAML or is missing required structure, THEN THE Dry_Run_Engine SHALL report the file name and the specific validation error.

### Requirement 13: Pre-Existing Resource Dependency Validation

**User Story:** As a DevOps engineer, I want the dry run to verify that pre-existing AWS resources and DataZone types referenced by catalog export data exist in the target environment, so that I can detect missing dependencies before deployment causes silent failures or orphaned assets.

#### Acceptance Criteria

1. WHEN the bundle contains a Catalog_Export file with assets that reference Glue Data Catalog resources via GlueTableFormType content (covering both tables and views), THE Dry_Run_Engine SHALL extract the `databaseName` and `tableName` from each GlueTableFormType form content and verify that the referenced Glue resource exists in the target AWS account by calling `glue:GetTable`.
2. WHEN the bundle contains a Catalog_Export file with assets that reference Glue databases via GlueTableFormType content, THE Dry_Run_Engine SHALL verify that the referenced Glue database exists in the target AWS account by calling `glue:GetDatabase`.
3. IF a referenced Glue_Data_Catalog_Resource (table, view, or database) does not exist in the target AWS account, THEN THE Dry_Run_Engine SHALL report an ERROR finding containing the missing resource name, database name, the resource type (table, view, or database), and the catalog asset that references the missing resource.
4. WHEN the bundle contains a Catalog_Export file with assets that reference data sources via DataSourceReferenceFormType content, THE Dry_Run_Engine SHALL verify that a matching data source exists in the target DataZone project by calling `datazone:ListDataSources` and matching on data source type and database name.
5. IF no matching data source exists in the target DataZone project for an asset's DataSourceReferenceFormType, THEN THE Dry_Run_Engine SHALL report a WARNING finding containing the expected data source type, database name, and the asset that references the missing data source.
6. WHEN the bundle contains a Catalog_Export file with asset types that reference custom form types in their formsInput, THE Dry_Run_Engine SHALL verify that each referenced custom form type exists in the target DataZone domain by calling `datazone:GetFormType`.
7. IF a referenced custom form type does not exist in the target DataZone domain, THEN THE Dry_Run_Engine SHALL report an ERROR finding containing the missing form type name and the asset type that references the missing form type.
8. WHEN the bundle contains a Catalog_Export file with assets that reference asset types via typeIdentifier, THE Dry_Run_Engine SHALL verify that each referenced custom asset type exists in the target DataZone domain by calling `datazone:SearchTypes`.
9. IF a referenced custom asset type does not exist in the target DataZone domain, THEN THE Dry_Run_Engine SHALL report an ERROR finding containing the missing asset type identifier and the asset that references the missing asset type.
10. WHEN the bundle contains a Catalog_Export file with assets that reference form types in their formsInput, THE Dry_Run_Engine SHALL verify that each referenced custom form type revision is resolvable in the target DataZone domain by calling `datazone:GetFormType`.
11. IF a referenced form type revision is not resolvable in the target DataZone domain, THEN THE Dry_Run_Engine SHALL report a WARNING finding containing the form type name, the expected revision, and the asset that references the unresolvable form type revision.
12. THE Dry_Run_Engine SHALL skip validation of managed or system form types and asset types (those with the `amazon.datazone.` prefix) since these exist in every DataZone domain.
13. THE Dry_Run_Engine SHALL detect and validate all Glue Data Catalog resource types referenced by catalog assets, including but not limited to: Glue tables (asset type `GlueTableAssetType`), Glue views (asset type `GlueViewAssetType`), and any other asset whose formsInput contains a GlueTableFormType form. The `glue:GetTable` API covers both tables and views since Glue treats views as tables with a different `tableType` parameter.

### Requirement 14: Pre-Deployment Dry Run Validation

**User Story:** As a DevOps engineer, I want the deploy command to automatically run a dry-run validation before beginning the actual deployment, so that deployment failures are caught early and I avoid partial deployments that leave resources in an inconsistent state.

#### Acceptance Criteria

1. WHEN the deploy command is invoked without `--dry-run` and without `--skip-validation`, THE CLI SHALL automatically execute the Dry_Run_Engine as a pre-deployment validation step before calling the actual deploy logic.
2. IF the pre-deployment dry-run validation produces one or more ERROR findings, THEN THE CLI SHALL abort the deployment, display the Dry_Run_Report, and exit with a non-zero exit code without executing any deployment actions.
3. IF the pre-deployment dry-run validation produces only OK and WARNING findings (zero ERROR findings), THEN THE CLI SHALL log a summary of the validation results and proceed with the actual deployment.
4. WHEN the pre-deployment dry-run validation runs, THE CLI SHALL display a message indicating that pre-deployment validation is in progress (e.g., "Running pre-deployment validation...").
5. WHEN the pre-deployment dry-run validation completes successfully (no errors), THE CLI SHALL display a message indicating validation passed (e.g., "Pre-deployment validation passed. Proceeding with deployment.") along with a count of any warnings.
6. WHEN the pre-deployment dry-run validation fails (errors found), THE CLI SHALL display a message indicating validation failed (e.g., "Pre-deployment validation failed. Deployment aborted.") followed by the full Dry_Run_Report.
7. WHEN the `--skip-validation` flag is provided, THE CLI SHALL skip the pre-deployment dry-run validation step and proceed directly to deployment, matching the current deploy behavior.
8. THE pre-deployment dry-run validation SHALL use the same Dry_Run_Engine, checkers, and report model as the standalone `--dry-run` mode, ensuring consistent validation logic between both paths.
9. THE pre-deployment dry-run validation SHALL suppress EventBridge event emission during the validation phase, only allowing events during the actual deployment phase if `--emit-events` is enabled.
10. WHEN the `--output json` option is provided alongside a normal deploy (not `--dry-run`), THE pre-deployment validation report SHALL still be rendered in human-readable text format since the JSON output option only applies to standalone dry-run mode.

### Requirement 10: Unit Test Coverage

**User Story:** As a developer, I want comprehensive unit test coverage for all dry-run code, so that I can maintain code quality and catch regressions early.

#### Acceptance Criteria

1. THE Dry_Run_Engine unit test suite SHALL achieve a minimum of 95% line coverage across all dry-run modules.
2. THE unit test suite SHALL cover the Dry_Run_Engine orchestration logic, including phase ordering and error aggregation.
3. THE unit test suite SHALL cover the Permission_Checker logic for all permission verification scenarios, including missing permissions, sufficient permissions, and API call failures.
4. THE unit test suite SHALL cover the Dry_Run_Report generation logic, including human-readable text output and JSON output formatting.
5. THE unit test suite SHALL cover all manifest and bundle validation logic, including valid inputs, malformed inputs, and missing fields.
6. THE unit test suite SHALL cover all Bootstrap_Actions permission verification for each action type (`workflow.create`, `workflow.run`, `workflow.logs`, `workflow.monitor`, `quicksight.refresh_dataset`, `eventbridge.put_events`, `project.create_environment`, `project.create_connection`).
7. THE unit test suite SHALL cover the DependencyChecker logic for all pre-existing resource validation scenarios, including missing Glue Data Catalog resources (tables, views, databases), missing data sources, missing custom form types, missing custom asset types, unresolvable form type revisions, and correct skipping of managed resources.
8. THE unit test suite SHALL cover the pre-deployment validation integration in the CLI deploy function, including: validation pass leading to deployment, validation failure aborting deployment, and `--skip-validation` bypassing validation.

### Requirement 11: End-to-End Integration Test Coverage

**User Story:** As a developer, I want comprehensive integration tests that validate the dry run against real AWS resources, so that I can ensure the dry-run feature works correctly in realistic deployment scenarios.

#### Acceptance Criteria

1. THE integration test suite SHALL execute a full dry-run flow using a valid Manifest and Bundle against real AWS resources and verify that the Dry_Run_Report contains no errors.
2. THE integration test suite SHALL execute a dry-run flow using an invalid Manifest (e.g., missing required fields, malformed YAML) and verify that the Dry_Run_Report contains the expected validation errors.
3. THE integration test suite SHALL execute a dry-run flow with an IAM identity that lacks required permissions and verify that the Permission_Checker reports each missing permission accurately.
4. THE integration test suite SHALL execute a dry-run flow targeting unreachable AWS resources (e.g., nonexistent S3 bucket, nonexistent DataZone domain) and verify that the Dry_Run_Engine reports the correct connectivity errors.
5. THE integration test suite SHALL execute a dry-run flow with a Bundle containing invalid or incomplete artifacts and verify that the Dry_Run_Engine reports the specific bundle validation errors.
6. THE integration test suite SHALL verify that the dry-run flow produces consistent results across repeated executions with the same inputs.
7. THE integration test suite SHALL verify that a normal deploy (without `--dry-run` or `--skip-validation`) runs the pre-deployment validation and proceeds to deployment when validation passes.
8. THE integration test suite SHALL verify that a normal deploy aborts when the pre-deployment validation detects errors, and that no resources are created or modified.
9. THE integration test suite SHALL verify that `--skip-validation` bypasses the pre-deployment validation and proceeds directly to deployment.

### Requirement 12: Code Quality — Lint and Format Checks

**User Story:** As a developer, I want all dry-run code to pass lint and format checks, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. ALL new and modified Python files SHALL pass `black` formatting with the project's configured line length (88 characters) and target version (py38).
2. ALL new and modified Python files SHALL pass `isort` import ordering with the project's configured profile (`black`).
3. ALL new and modified Python files SHALL pass `flake8` linting with the project's configured rules (max line length 120, ignoring E203, W503, E501).
4. ALL new and modified Python files SHALL pass `mypy` type checking with no new type errors introduced.
5. AFTER all implementation tasks are complete, THE developer SHALL run `black --check`, `isort --check-only`, `flake8`, and `mypy` against all dry-run modules and verify zero violations.

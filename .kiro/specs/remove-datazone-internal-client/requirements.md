# Requirements Document

## Introduction

This document specifies requirements for removing the dependency on the `datazone-internal` boto3 client from the SMUS CI/CD CLI project. The project currently uses internal DataZone clients in multiple locations to support features like `customerProvidedRoleConfigs` for project creation and workflow connection properties (`workflowsMwaaProperties`, `workflowsServerlessProperties`). This migration will transition all DataZone operations to use the public boto3 DataZone client available by default.

## Glossary

- **SMUS_CLI**: The SageMaker Unified Studio CI/CD command-line interface tool
- **DataZone_Client**: The public boto3 DataZone client available by default in boto3
- **Internal_Client**: The `datazone-internal` boto3 client requiring custom service model registration
- **Custom_Model**: JSON service model files that define API operations and parameters for boto3 clients
- **Project_Manager**: The module responsible for creating and managing DataZone projects
- **Connection_Creator**: The module responsible for creating DataZone connections
- **DataZone_Handler**: The bootstrap handler for DataZone operations
- **Unit_Test_Suite**: The collection of unit tests in the `tests/unit/` directory
- **Integration_Test_Suite**: The collection of integration tests in the `tests/integration/` directory
- **GitHub_Workflow**: The CI/CD pipeline definitions in `.github/workflows/` directory

## Requirements

### Requirement 1: Remove Internal Client from DataZone Helper

**User Story:** As a developer, I want the DataZone helper to use only the public DataZone client, so that the codebase has fewer dependencies on internal APIs.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL remove the `_get_datazone_internal_client()` function from `src/smus_cicd/helpers/datazone.py`
2. THE SMUS_CLI SHALL ensure all DataZone operations in the helper module use `_get_datazone_client()` instead of the internal client
3. WHEN the DataZone helper is imported, THE SMUS_CLI SHALL NOT create any `datazone-internal` boto3 clients

### Requirement 2: Update Project Creation to Use Public Client

**User Story:** As a developer, I want project creation to use the public DataZone client, so that the code is compatible with standard boto3 installations.

#### Acceptance Criteria

1. THE Project_Manager SHALL use `datazone._get_datazone_client(region)` instead of `datazone._get_datazone_internal_client(region)` in the `_create_project_via_datazone_api()` method
2. WHEN creating a project with a customer-provided role, THE Project_Manager SHALL use the public API parameter format for role configuration
3. IF the public API does not support customer-provided roles, THEN THE Project_Manager SHALL log a warning and create the project without the role configuration
4. THE Project_Manager SHALL maintain backward compatibility for projects created without custom roles

### Requirement 3: Update Connection Creator to Use Public Client

**User Story:** As a developer, I want connection creation to use the public DataZone client, so that workflow connections work with standard boto3.

#### Acceptance Criteria

1. THE Connection_Creator SHALL remove the `_get_internal_datazone_client()` method from `src/smus_cicd/helpers/connection_creator.py`
2. THE Connection_Creator SHALL use the standard `_get_custom_datazone_client()` method for all connection types
3. WHEN creating WORKFLOWS_MWAA connections, THE Connection_Creator SHALL use public API-compatible property names
4. WHEN creating WORKFLOWS_SERVERLESS connections, THE Connection_Creator SHALL use public API-compatible property names
5. THE Connection_Creator SHALL maintain the `_internal_client` instance variable removal without breaking existing connection management

### Requirement 4: Update Bootstrap Handler to Use Public Client

**User Story:** As a developer, I want the bootstrap DataZone handler to use the public client, so that bootstrap operations are consistent with the rest of the codebase.

#### Acceptance Criteria

1. THE DataZone_Handler SHALL remove the conditional creation of `datazone-internal` client in `src/smus_cicd/bootstrap/handlers/datazone_handler.py`
2. WHEN handling WORKFLOWS_SERVERLESS connections, THE DataZone_Handler SHALL use the standard DataZone client
3. THE DataZone_Handler SHALL pass the appropriate client to the Connection_Creator for all connection types

### Requirement 5: Remove Custom DataZone Model Files

**User Story:** As a developer, I want to remove custom DataZone model files, so that the project has fewer maintenance dependencies.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL identify all custom DataZone model JSON files in the `src/smus_cicd/resources/` directory
2. THE SMUS_CLI SHALL remove the `datazone-internal-2018-05-10.json` file
3. THE SMUS_CLI SHALL evaluate whether `datazone-2018-05-10.json` is still needed for public API operations
4. IF the public boto3 DataZone client includes all required operations, THEN THE SMUS_CLI SHALL remove `datazone-2018-05-10.json`
5. THE SMUS_CLI SHALL update any code that references these model files

### Requirement 6: Update GitHub Workflow Configurations

**User Story:** As a developer, I want GitHub workflows to not register internal DataZone models, so that CI/CD pipelines use standard boto3 configurations.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL remove all `aws configure add-model` commands for `datazone-internal` from `.github/workflows/smus-multi-env-reusable.yml`
2. THE SMUS_CLI SHALL remove all `aws configure add-model` commands for `datazone-internal` from `.github/workflows/pr-tests.yml`
3. THE SMUS_CLI SHALL remove all `aws configure add-model` commands for `datazone-internal` from `.github/workflows/smus-direct-deploy.yml`
4. IF custom DataZone models are still required, THEN THE SMUS_CLI SHALL retain only the necessary model registration commands
5. THE SMUS_CLI SHALL ensure workflow files remain syntactically valid YAML after modifications

### Requirement 7: Update Test Setup Scripts

**User Story:** As a developer, I want test setup scripts to not reference internal clients, so that test environments use standard configurations.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL identify all references to `datazone-internal` in test setup scripts under `tests/scripts/`
2. THE SMUS_CLI SHALL update or remove references to internal client usage in deployment scripts
3. THE SMUS_CLI SHALL update documentation comments that mention `datazone-internal` client requirements
4. THE SMUS_CLI SHALL ensure test setup scripts can execute successfully with public DataZone client only

### Requirement 8: Verify Unit Test Compatibility

**User Story:** As a developer, I want all unit tests to pass after the migration, so that I can verify the changes don't break existing functionality.

#### Acceptance Criteria

1. WHEN unit tests are executed, THE Unit_Test_Suite SHALL pass all existing test cases
2. IF unit tests mock the internal client, THEN THE Unit_Test_Suite SHALL update mocks to use the public client
3. THE Unit_Test_Suite SHALL verify that DataZone helper functions return expected results
4. THE Unit_Test_Suite SHALL verify that project creation logic handles all input scenarios correctly
5. THE Unit_Test_Suite SHALL verify that connection creation logic handles all connection types correctly

### Requirement 9: Verify Integration Test Compatibility

**User Story:** As a developer, I want all integration tests to pass after the migration, so that I can verify the changes work against real AWS services.

#### Acceptance Criteria

1. WHEN integration tests are executed against AWS, THE Integration_Test_Suite SHALL pass all existing test cases
2. THE Integration_Test_Suite SHALL verify project creation with and without custom roles
3. THE Integration_Test_Suite SHALL verify WORKFLOWS_MWAA connection creation
4. THE Integration_Test_Suite SHALL verify WORKFLOWS_SERVERLESS connection creation
5. THE Integration_Test_Suite SHALL verify all other connection types remain functional
6. IF any integration test fails due to API incompatibility, THEN THE SMUS_CLI SHALL document the limitation and provide workarounds

### Requirement 10: Handle API Feature Parity

**User Story:** As a developer, I want to understand which features may not be available in the public API, so that I can plan appropriate fallback strategies.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL document whether `customerProvidedRoleConfigs` is available in the public DataZone API
2. THE SMUS_CLI SHALL document whether `workflowsMwaaProperties` is available in the public DataZone API
3. THE SMUS_CLI SHALL document whether `workflowsServerlessProperties` is available in the public DataZone API
4. IF a feature is not available in the public API, THEN THE SMUS_CLI SHALL implement graceful degradation or alternative approaches
5. THE SMUS_CLI SHALL update user-facing documentation to reflect any feature changes or limitations

### Requirement 11: Update Code Documentation

**User Story:** As a developer, I want code comments and docstrings to reflect the new implementation, so that future maintainers understand the changes.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL remove all docstring references to `datazone-internal` client support
2. THE SMUS_CLI SHALL update function docstrings to describe public API usage
3. THE SMUS_CLI SHALL update inline comments that reference internal client behavior
4. THE SMUS_CLI SHALL add comments explaining any workarounds for public API limitations
5. THE SMUS_CLI SHALL maintain PEP 8 compliance for all modified code

### Requirement 12: Update Boto3 Dependency Version

**User Story:** As a developer, I want the package to depend on the latest version of boto3, so that the public DataZone client includes all necessary API operations.

#### Acceptance Criteria

1. THE SMUS_CLI SHALL update the boto3 dependency in `requirements.txt` to the latest stable version
2. THE SMUS_CLI SHALL update the boto3 dependency in `setup.py` (if present) to match the requirements.txt version
3. THE SMUS_CLI SHALL verify that the latest boto3 version includes support for all DataZone operations used by the CLI
4. THE SMUS_CLI SHALL document the minimum required boto3 version in the project README or installation documentation
5. THE SMUS_CLI SHALL test all DataZone operations with the updated boto3 version to ensure compatibility

### Requirement 13: Validate Endpoint URL Override Support

**User Story:** As a developer, I want endpoint URL overrides to continue working, so that testing against non-production environments remains possible.

#### Acceptance Criteria

1. WHEN the `DATAZONE_ENDPOINT_URL` environment variable is set, THE DataZone_Client SHALL use the specified endpoint URL
2. THE SMUS_CLI SHALL verify that endpoint URL override works for all DataZone operations
3. THE SMUS_CLI SHALL maintain the same endpoint URL override mechanism used by the internal client
4. THE SMUS_CLI SHALL document the endpoint URL override capability for testing purposes

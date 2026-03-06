# Implementation Plan: Remove DataZone Internal Client Dependency

## Overview

This implementation plan removes the `datazone-internal` boto3 client dependency from the SMUS CI/CD CLI project. The migration transitions all DataZone operations to use the public boto3 DataZone client, eliminating custom service model registration and reducing maintenance overhead. The implementation follows a phased approach: update dependencies, migrate code components, clean up resources, add comprehensive testing, and update documentation.

## Tasks

- [x] 1. Update boto3 dependency and verify API compatibility
  - Update `requirements.txt` to specify `boto3>=1.35.0`
  - Update `setup.py` boto3 dependency if present
  - Verify all required DataZone operations exist in public client
  - _Requirements: 12.1, 12.2, 12.3_

- [x] 2. Remove internal client from DataZone helper module
  - [x] 2.1 Remove `_get_datazone_internal_client()` function from `src/smus_cicd/helpers/datazone.py`
    - Delete the entire function definition
    - Verify no other functions in the module call it
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 Write property test for endpoint URL override
    - **Property 8: Endpoint URL Override for All Operations**
    - **Validates: Requirements 13.1**
    - Test that all DataZone operations respect `DATAZONE_ENDPOINT_URL` environment variable
    - _Requirements: 13.1_

- [x] 3. Update project manager to use public client
  - [x] 3.1 Update `_create_project_via_datazone_api()` in `src/smus_cicd/helpers/project_manager.py`
    - Replace `datazone._get_datazone_internal_client(region)` with `datazone._get_datazone_client(region)`
    - Add try-except block for `customerProvidedRoleConfigs` parameter
    - Implement graceful degradation with warning message if parameter not supported
    - Handle `TypeError`, `KeyError`, and `ValidationException` exceptions
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 3.2 Write property test for project creation without custom roles
    - **Property 1: Project Creation Without Custom Roles**
    - **Validates: Requirements 2.4**
    - Test that projects without custom role ARN succeed with public API
    - _Requirements: 2.4, 8.4_

  - [ ]* 3.3 Write property test for project creation across input scenarios
    - **Property 5: Project Creation Across Input Scenarios**
    - **Validates: Requirements 8.4**
    - Test project creation with/without custom roles, memberships, and policies
    - _Requirements: 8.4, 9.2_

- [x] 4. Checkpoint - Verify project manager changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update connection creator to remove internal client
  - [x] 5.1 Remove internal client from `src/smus_cicd/helpers/connection_creator.py`
    - Remove `_internal_client` instance variable from `__init__` method
    - Delete `_get_internal_datazone_client()` method entirely
    - Update `create_connection()` to use `self.client` for WORKFLOWS_MWAA and WORKFLOWS_SERVERLESS
    - Remove conditional logic that selected internal client
    - _Requirements: 3.1, 3.2_

  - [x] 5.2 Update connection property names for public API compatibility
    - Verify `workflowsMwaaProperties` property name for WORKFLOWS_MWAA connections
    - Verify `workflowsServerlessProperties` property name for WORKFLOWS_SERVERLESS connections
    - Update `_build_connection_props()` if property names differ
    - _Requirements: 3.3, 3.4_

  - [x] 5.3 Write property test for WORKFLOWS_MWAA connection creation
    - **Property 2: WORKFLOWS_MWAA Connection Creation**
    - **Validates: Requirements 3.3**
    - Test that MWAA connections succeed with public API-compatible property names
    - _Requirements: 3.3, 9.3_

  - [x] 5.4 Write property test for WORKFLOWS_SERVERLESS connection creation
    - **Property 3: WORKFLOWS_SERVERLESS Connection Creation**
    - **Validates: Requirements 3.4**
    - Test that serverless workflow connections succeed with public API
    - _Requirements: 3.4, 4.2, 9.4_

  - [ ]* 5.5 Write property test for connection management across all types
    - **Property 4: Connection Management After Internal Client Removal**
    - **Validates: Requirements 3.5**
    - Test all connection types (S3, IAM, SPARK_GLUE, REDSHIFT, ATHENA, MLFLOW, WORKFLOWS_MWAA, WORKFLOWS_SERVERLESS)
    - _Requirements: 3.5, 8.5_

- [x] 6. Update DataZone bootstrap handler
  - [x] 6.1 Remove internal client creation from `src/smus_cicd/bootstrap/handlers/datazone_handler.py`
    - Remove conditional creation of `datazone-internal` client for WORKFLOWS_SERVERLESS
    - Remove `internal_client` variable
    - Verify `ConnectionCreator` handles all connection types with standard client
    - _Requirements: 4.1, 4.2_

  - [ ]* 6.2 Write property test for connection creation across all types
    - **Property 6: Connection Creation Across All Types**
    - **Validates: Requirements 8.5**
    - Test that all supported connection types create successfully
    - _Requirements: 8.5_

- [x] 7. Checkpoint - Verify all code migrations complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Remove custom DataZone model files
  - [x] 8.1 Remove `src/smus_cicd/resources/datazone-internal-2018-05-10.json`
    - Delete the file
    - _Requirements: 5.1_

  - [x] 8.2 Evaluate and potentially remove `src/smus_cicd/resources/datazone-2018-05-10.json`
    - Check if `ConnectionCreator._get_custom_datazone_client()` still uses it for MLflow
    - If public boto3 supports MLflow connection type, remove the file
    - If not, keep the file and document its purpose
    - _Requirements: 5.2_

- [x] 9. Update GitHub workflow configurations
  - [x] 9.1 Remove internal model registration from `.github/workflows/smus-multi-env-reusable.yml`
    - Remove `aws configure add-model` command for `datazone-internal`
    - Keep model registration for `datazone-2018-05-10.json` only if file retained
    - _Requirements: 6.1, 6.2_

  - [x] 9.2 Remove internal model registration from `.github/workflows/pr-tests.yml`
    - Remove `aws configure add-model` command for `datazone-internal`
    - Keep model registration for `datazone-2018-05-10.json` only if file retained
    - _Requirements: 6.3, 6.4_

  - [x] 9.3 Remove internal model registration from `.github/workflows/smus-direct-deploy.yml`
    - Remove `aws configure add-model` command for `datazone-internal`
    - Keep model registration for `datazone-2018-05-10.json` only if file retained
    - _Requirements: 6.6_

  - [x] 9.4 Verify workflow YAML files are valid
    - Validate YAML syntax
    - Ensure no broken references
    - _Requirements: 6.5_

- [x] 10. Update test setup scripts
  - [x] 10.1 Remove internal model registration from test setup scripts
    - Search for any test setup scripts that register `datazone-internal` model
    - Remove or update those registrations
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 10.2 Verify test setup scripts execute successfully
    - Run test setup scripts to ensure they work without internal client
    - _Requirements: 7.4_

- [x] 11. Checkpoint - Verify resource cleanup complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Add comprehensive property-based tests
  - [x]* 12.1 Write property test for connection types remaining functional
    - **Property 7: All Connection Types Remain Functional**
    - **Validates: Requirements 9.5**
    - Test that all previously working connection types still work after migration
    - _Requirements: 9.5_

  - [x]* 12.2 Write property test for endpoint URL override consistency
    - **Property 9: Endpoint URL Override Consistency**
    - **Validates: Requirements 13.2**
    - Test that endpoint override works identically to internal client behavior
    - _Requirements: 13.2, 13.3_

- [x] 13. Run existing unit tests and verify compatibility
  - [x] 13.1 Run all existing unit tests
    - Execute full unit test suite
    - Verify all tests pass with public client
    - _Requirements: 8.1_

  - [x]* 13.2 Verify DataZone helper functions return expected results
    - Test all functions in `datazone.py` module
    - Ensure return values and behavior unchanged
    - _Requirements: 8.2, 8.3_

- [x] 14. Run integration tests and verify functionality
  - [x]* 14.1 Run all existing integration tests
    - Execute full integration test suite
    - Verify all tests pass with public client
    - _Requirements: 9.1_

  - [x]* 14.2 Test graceful degradation for missing API features
    - Test scenarios where public API lacks features
    - Verify warning messages display correctly
    - Verify fallback behavior works as expected
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x]* 14.3 Verify boto3 operations work with updated version
    - Test all DataZone operations with boto3>=1.35.0
    - Ensure no breaking changes affect functionality
    - _Requirements: 12.4, 12.5_

- [x] 15. Update code documentation
  - [x] 15.1 Update docstrings and comments
    - Remove references to `datazone-internal` in comments
    - Update docstrings to reflect public client usage
    - Add comments explaining graceful degradation logic
    - _Requirements: 11.1, 11.2_

  - [x] 15.2 Update inline documentation
    - Review all code for outdated internal client references
    - Update comments to reflect current implementation
    - _Requirements: 11.3_

  - [x] 15.3 Verify code follows PEP 8 style guidelines
    - Run linter on modified files
    - Fix any style violations
    - _Requirements: 11.4, 11.5_

- [x] 16. Final checkpoint - Complete validation
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples, edge cases, and error conditions
- The implementation uses Python as specified in the design document
- Graceful degradation ensures backward compatibility when public API lacks features
- All property-based tests should use minimum 100 iterations with Hypothesis
- Test tasks include proper tagging: `# Feature: remove-datazone-internal-client, Property {number}: {property_text}`

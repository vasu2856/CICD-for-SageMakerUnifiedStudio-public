# Design Document: Remove DataZone Internal Client Dependency

## Overview

This design document outlines the approach for removing the dependency on the `datazone-internal` boto3 client from the SMUS CI/CD CLI project. The migration will transition all DataZone operations to use the public boto3 DataZone client, eliminating the need for custom service model registration and reducing maintenance overhead.

### Goals

- Remove all usage of `datazone-internal` boto3 client
- Migrate to public DataZone API for all operations
- Maintain backward compatibility for existing functionality
- Update boto3 to latest version with full DataZone API support
- Remove custom DataZone model files where possible
- Update CI/CD workflows to remove internal client setup

### Non-Goals

- Changing the external CLI interface or user-facing behavior
- Modifying the manifest file format
- Altering the deployment workflow logic beyond client usage

### Assumptions

- The public boto3 DataZone API supports all required operations (or graceful degradation is acceptable)
- The latest boto3 version includes comprehensive DataZone API coverage
- Endpoint URL override mechanism works identically for public client
- Existing tests provide adequate coverage to detect regressions

## Architecture

### Current Architecture

The current implementation uses two DataZone clients:

1. **Public Client** (`datazone`): Used for most DataZone operations
   - Created by `_get_datazone_client(region)` in `datazone.py`
   - Supports standard DataZone operations

2. **Internal Client** (`datazone-internal`): Used for specific operations
   - Created by `_get_datazone_internal_client(region)` in `datazone.py`
   - Used in `project_manager.py` for `customerProvidedRoleConfigs` parameter
   - Used in `connection_creator.py` for workflow connections
   - Used in `datazone_handler.py` for serverless workflow connections
   - Requires custom service model registration via JSON files

### Target Architecture

The target architecture uses only the public DataZone client:

```
┌─────────────────────────────────────────────────────────────┐
│                     SMUS CI/CD CLI Application                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Project    │  │  Connection  │  │   DataZone   │      │
│  │   Manager    │  │   Creator    │  │   Handler    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            │                                 │
│                    ┌───────▼────────┐                        │
│                    │ DataZone Helper│                        │
│                    │                │                        │
│                    │ _get_datazone_ │                        │
│                    │    client()    │                        │
│                    └───────┬────────┘                        │
│                            │                                 │
└────────────────────────────┼─────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Public Boto3   │
                    │ DataZone Client │
                    └─────────────────┘
```

### Migration Strategy

The migration follows these phases:

1. **Analysis Phase**: Identify all usages of internal client
2. **Code Update Phase**: Replace internal client calls with public client
3. **Testing Phase**: Verify all operations work with public client
4. **Cleanup Phase**: Remove internal client code and model files
5. **Documentation Phase**: Update all references and documentation

## Components and Interfaces

### 1. DataZone Helper Module (`datazone.py`)

**Changes Required:**

- Remove `_get_datazone_internal_client()` function
- Ensure all internal calls use `_get_datazone_client()`
- Maintain endpoint URL override support via `DATAZONE_ENDPOINT_URL` environment variable

**Interface:**

```python
def _get_datazone_client(region: str) -> boto3.client:
    """
    Create DataZone client with optional custom endpoint from environment.
    
    Args:
        region: AWS region for the client
        
    Returns:
        Configured boto3 DataZone client
        
    Environment Variables:
        DATAZONE_ENDPOINT_URL: Optional custom endpoint URL for testing
    """
    endpoint_url = os.environ.get("DATAZONE_ENDPOINT_URL")
    if endpoint_url:
        return boto3.client("datazone", region_name=region, endpoint_url=endpoint_url)
    return boto3.client("datazone", region_name=region)
```

**Impact Analysis:**

- All functions in `datazone.py` already use `_get_datazone_client()` except where explicitly calling internal client
- No changes needed to function signatures or return types
- Endpoint URL override mechanism remains unchanged

### 2. Project Manager Module (`project_manager.py`)

**Changes Required:**

- Update `_create_project_via_datazone_api()` to use public client
- Handle `customerProvidedRoleConfigs` parameter compatibility
- Implement graceful degradation if parameter not supported

**Current Implementation:**

```python
def _create_project_via_datazone_api(self, ...):
    # Uses datazone._get_datazone_internal_client(region)
    dz_client = datazone._get_datazone_internal_client(region)
    
    params = {
        "domainIdentifier": domain_id,
        "name": project_name,
        "projectProfileId": profile_id,
    }
    
    if role_arn:
        params["customerProvidedRoleConfigs"] = [
            {"roleArn": role_arn, "roleDesignation": "PROJECT_OWNER"}
        ]
```

**Target Implementation:**

```python
def _create_project_via_datazone_api(self, ...):
    # Use public client
    dz_client = datazone._get_datazone_client(region)
    
    params = {
        "domainIdentifier": domain_id,
        "name": project_name,
        "projectProfileId": profile_id,
    }
    
    # Attempt to use customerProvidedRoleConfigs if supported
    if role_arn:
        try:
            params["customerProvidedRoleConfigs"] = [
                {"roleArn": role_arn, "roleDesignation": "PROJECT_OWNER"}
            ]
            response = dz_client.create_project(**params)
        except (TypeError, KeyError, dz_client.exceptions.ValidationException) as e:
            # Parameter not supported in public API
            typer.echo(f"⚠️ customerProvidedRoleConfigs not supported, creating project without custom role")
            del params["customerProvidedRoleConfigs"]
            response = dz_client.create_project(**params)
    else:
        response = dz_client.create_project(**params)
```

**API Compatibility Considerations:**

- If `customerProvidedRoleConfigs` is not available in public API, projects will be created without custom roles
- Role attachment can still be done post-creation via IAM operations
- Warning message will inform users of the limitation

### 3. Connection Creator Module (`connection_creator.py`)

**Changes Required:**

- Remove `_get_internal_datazone_client()` method
- Remove `_internal_client` instance variable
- Update connection creation for `WORKFLOWS_MWAA` and `WORKFLOWS_SERVERLESS` types
- Use `_get_custom_datazone_client()` for all connection types

**Current Implementation:**

```python
class ConnectionCreator:
    def __init__(self, domain_id: str, region: str = "us-east-1"):
        self.domain_id = domain_id
        self.region = region
        self.client = boto3.client("datazone", region_name=region)
        self._custom_client = None
        self._internal_client = None  # To be removed
        
    def _get_internal_datazone_client(self):  # To be removed
        if self._internal_client is None:
            endpoint_url = os.environ.get("DATAZONE_ENDPOINT_URL")
            if endpoint_url:
                self._internal_client = boto3.client(
                    "datazone-internal",
                    region_name=self.region,
                    endpoint_url=endpoint_url,
                )
            else:
                self._internal_client = boto3.client(
                    "datazone-internal", region_name=self.region
                )
        return self._internal_client
```

**Target Implementation:**

```python
class ConnectionCreator:
    def __init__(self, domain_id: str, region: str = "us-east-1"):
        self.domain_id = domain_id
        self.region = region
        self.client = boto3.client("datazone", region_name=region)
        self._custom_client = None
        # _internal_client removed
        
    # _get_internal_datazone_client() method removed
```

**Connection Type Handling:**

For workflow connections, the logic will be updated:

```python
def create_connection(self, environment_id: str, name: str, 
                     connection_type: str, **kwargs) -> str:
    props = self._build_connection_props(connection_type, **kwargs)
    
    # Determine which client to use
    if connection_type == "MLFLOW":
        client = self._get_custom_datazone_client()
    elif connection_type in ["WORKFLOWS_MWAA", "WORKFLOWS_SERVERLESS"]:
        # Use standard client instead of internal client
        client = self.client
    else:
        client = self.client
```

**Property Name Compatibility:**

The `_build_connection_props()` method will use public API-compatible property names:

- `WORKFLOWS_MWAA`: Use `workflowsMwaaProperties` (verify public API support)
- `WORKFLOWS_SERVERLESS`: Use `workflowsServerlessProperties` (verify public API support)

### 4. DataZone Handler Module (`datazone_handler.py`)

**Changes Required:**

- Remove conditional creation of `datazone-internal` client
- Use standard DataZone client for all connection types
- Update `create_connection()` function

**Current Implementation:**

```python
def create_connection(action: BootstrapAction, context: Dict[str, Any]) -> Dict[str, Any]:
    # Create internal client for WORKFLOWS_SERVERLESS connections
    internal_client = None
    if connection_type == "WORKFLOWS_SERVERLESS":
        internal_client = boto3.client("datazone-internal", region_name=region)
```

**Target Implementation:**

```python
def create_connection(action: BootstrapAction, context: Dict[str, Any]) -> Dict[str, Any]:
    # No internal client needed - ConnectionCreator handles all types
    # with standard client
```

### 5. Resource Files

**Files to Remove:**

- `src/smus_cicd/resources/datazone-internal-2018-05-10.json`

**Files to Evaluate:**

- `src/smus_cicd/resources/datazone-2018-05-10.json`
  - Currently used by `ConnectionCreator._get_custom_datazone_client()` for MLflow connections
  - Evaluation needed: Does public boto3 DataZone client support MLflow connection type?
  - If yes: Remove file and use standard client
  - If no: Keep file for MLflow support only

### 6. GitHub Workflows

**Files to Update:**

1. `.github/workflows/smus-multi-env-reusable.yml`
2. `.github/workflows/pr-tests.yml`
3. `.github/workflows/smus-direct-deploy.yml`

**Changes:**

Remove all `aws configure add-model` commands for `datazone-internal`:

```yaml
# Remove these lines:
- name: Configure DataZone Internal Model
  run: |
    aws configure add-model \
      --service-model file://src/smus_cicd/resources/datazone-internal-2018-05-10.json \
      --service-name datazone-internal
```

If `datazone-2018-05-10.json` is retained for MLflow support, keep only that model registration.

### 7. Dependency Updates

**requirements.txt:**

```txt
typer[all]
PyYAML
boto3>=1.35.0  # Update to latest version with full DataZone API support
jsonschema
```

**Rationale:**

- boto3 1.35.0+ includes comprehensive DataZone API support
- Specify minimum version to ensure API compatibility
- Latest version includes all required operations

## Data Models

No changes to data models are required. The migration affects only the boto3 client implementation, not the data structures used by the application.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Project Creation Without Custom Roles

*For any* valid project configuration without a custom role ARN, creating the project via the public API should succeed and return a valid project ID.

**Validates: Requirements 2.4**

### Property 2: WORKFLOWS_MWAA Connection Creation

*For any* valid MWAA environment name, creating a WORKFLOWS_MWAA connection should succeed and use public API-compatible property names.

**Validates: Requirements 3.3**

### Property 3: WORKFLOWS_SERVERLESS Connection Creation

*For any* valid environment, creating a WORKFLOWS_SERVERLESS connection should succeed and use public API-compatible property names.

**Validates: Requirements 3.4**

### Property 4: Connection Management After Internal Client Removal

*For any* connection type (S3, IAM, SPARK_GLUE, REDSHIFT, ATHENA, MLFLOW, WORKFLOWS_MWAA, WORKFLOWS_SERVERLESS), the ConnectionCreator should successfully create and manage connections without the internal client.

**Validates: Requirements 3.5**

### Property 5: Project Creation Across Input Scenarios

*For any* valid project configuration (with or without custom roles, with or without memberships, with or without policies), the project creation logic should handle the scenario correctly using the public client.

**Validates: Requirements 8.4**

### Property 6: Connection Creation Across All Types

*For any* supported connection type, the connection creation logic should successfully create the connection using the appropriate client and property format.

**Validates: Requirements 8.5**

### Property 7: All Connection Types Remain Functional

*For any* connection type that worked before the migration, the connection should continue to work after migrating to the public client.

**Validates: Requirements 9.5**

### Property 8: Endpoint URL Override for All Operations

*For any* DataZone operation, when the `DATAZONE_ENDPOINT_URL` environment variable is set, the client should use the specified endpoint URL.

**Validates: Requirements 13.1**

### Property 9: Endpoint URL Override Consistency

*For any* DataZone operation that previously supported endpoint URL override with the internal client, the same override mechanism should work with the public client.

**Validates: Requirements 13.2**

## Error Handling

### API Compatibility Errors

**Scenario**: Public API does not support a parameter (e.g., `customerProvidedRoleConfigs`)

**Handling**:
1. Catch parameter validation exceptions
2. Log warning message to user
3. Retry operation without unsupported parameter
4. Document limitation in user-facing documentation

**Example**:

```python
try:
    response = dz_client.create_project(**params)
except (TypeError, KeyError, dz_client.exceptions.ValidationException) as e:
    if "customerProvidedRoleConfigs" in str(e):
        typer.echo("⚠️ Custom role configuration not supported in public API")
        typer.echo("   Project will be created without custom role")
        del params["customerProvidedRoleConfigs"]
        response = dz_client.create_project(**params)
    else:
        raise
```

### Connection Creation Errors

**Scenario**: Connection type not supported by public API

**Handling**:
1. Catch connection creation exceptions
2. Check if error is due to unsupported connection type
3. Log detailed error message
4. Provide workaround guidance if available
5. Fail gracefully with actionable error message

### Boto3 Version Compatibility

**Scenario**: Installed boto3 version lacks required DataZone operations

**Handling**:
1. Check boto3 version at startup
2. Verify required operations exist in client
3. Display clear error message with upgrade instructions
4. Exit with non-zero status code

**Example**:

```python
import boto3
from packaging import version

MIN_BOTO3_VERSION = "1.35.0"

def check_boto3_version():
    current_version = boto3.__version__
    if version.parse(current_version) < version.parse(MIN_BOTO3_VERSION):
        typer.echo(f"❌ boto3 version {current_version} is too old")
        typer.echo(f"   Minimum required version: {MIN_BOTO3_VERSION}")
        typer.echo(f"   Please upgrade: pip install --upgrade boto3>={MIN_BOTO3_VERSION}")
        raise SystemExit(1)
```

### Endpoint URL Override Errors

**Scenario**: Custom endpoint URL is invalid or unreachable

**Handling**:
1. Let boto3 raise connection errors naturally
2. Catch and enhance error message to mention endpoint override
3. Suggest checking `DATAZONE_ENDPOINT_URL` environment variable

## Testing Strategy

### Dual Testing Approach

The testing strategy employs both unit tests and property-based tests to ensure comprehensive coverage:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs
- Both approaches are complementary and necessary for complete validation

### Unit Testing

Unit tests will focus on:

1. **Specific Examples**:
   - Module import does not create internal clients (Requirement 1.3)
   - Project creation with customer-provided role uses correct parameter format (Requirement 2.2)
   - Graceful degradation when public API lacks features (Requirement 2.3)
   - WORKFLOWS_SERVERLESS connection creation (Requirement 4.2)
   - YAML workflow file validity after modifications (Requirement 6.5)
   - Test setup scripts execute successfully (Requirement 7.4)
   - All existing unit tests pass (Requirement 8.1)
   - DataZone helper functions return expected results (Requirement 8.3)
   - All integration tests pass (Requirement 9.1)
   - Project creation with and without custom roles (Requirement 9.2)
   - WORKFLOWS_MWAA connection creation (Requirement 9.3)
   - WORKFLOWS_SERVERLESS connection creation (Requirement 9.4)
   - Graceful degradation for missing features (Requirement 10.4)
   - PEP 8 compliance (Requirement 11.5)
   - Boto3 version includes all required operations (Requirement 12.3)
   - All operations work with updated boto3 (Requirement 12.5)
   - Endpoint URL override mechanism consistency (Requirement 13.3)

2. **Edge Cases**:
   - Empty or invalid project configurations
   - Missing environment variables
   - Network failures
   - Invalid connection properties

3. **Error Conditions**:
   - API parameter validation failures
   - Unsupported connection types
   - Boto3 version too old
   - Invalid endpoint URLs

### Property-Based Testing

Property-based tests will use **pytest with Hypothesis** (Python's property-based testing library):

**Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with reference to design property
- Tag format: `# Feature: remove-datazone-internal-client, Property {number}: {property_text}`

**Properties to Test**:

1. **Property 1**: Project Creation Without Custom Roles
   ```python
   # Feature: remove-datazone-internal-client, Property 1: Project Creation Without Custom Roles
   @given(project_config=project_configs_without_roles())
   @settings(max_examples=100)
   def test_project_creation_without_roles(project_config):
       # Test implementation
   ```

2. **Property 2**: WORKFLOWS_MWAA Connection Creation
   ```python
   # Feature: remove-datazone-internal-client, Property 2: WORKFLOWS_MWAA Connection Creation
   @given(mwaa_env_name=text(min_size=1))
   @settings(max_examples=100)
   def test_mwaa_connection_creation(mwaa_env_name):
       # Test implementation
   ```

3. **Property 3**: WORKFLOWS_SERVERLESS Connection Creation
   ```python
   # Feature: remove-datazone-internal-client, Property 3: WORKFLOWS_SERVERLESS Connection Creation
   @given(environment_id=valid_environment_ids())
   @settings(max_examples=100)
   def test_serverless_connection_creation(environment_id):
       # Test implementation
   ```

4. **Property 4**: Connection Management After Internal Client Removal
   ```python
   # Feature: remove-datazone-internal-client, Property 4: Connection Management After Internal Client Removal
   @given(connection_type=sampled_from(ALL_CONNECTION_TYPES))
   @settings(max_examples=100)
   def test_connection_management_all_types(connection_type):
       # Test implementation
   ```

5. **Property 5**: Project Creation Across Input Scenarios
   ```python
   # Feature: remove-datazone-internal-client, Property 5: Project Creation Across Input Scenarios
   @given(project_config=project_configs())
   @settings(max_examples=100)
   def test_project_creation_all_scenarios(project_config):
       # Test implementation
   ```

6. **Property 6**: Connection Creation Across All Types
   ```python
   # Feature: remove-datazone-internal-client, Property 6: Connection Creation Across All Types
   @given(connection_type=sampled_from(SUPPORTED_CONNECTION_TYPES),
          properties=connection_properties())
   @settings(max_examples=100)
   def test_connection_creation_all_types(connection_type, properties):
       # Test implementation
   ```

7. **Property 7**: All Connection Types Remain Functional
   ```python
   # Feature: remove-datazone-internal-client, Property 7: All Connection Types Remain Functional
   @given(connection_type=sampled_from(EXISTING_CONNECTION_TYPES))
   @settings(max_examples=100)
   def test_connection_types_remain_functional(connection_type):
       # Test implementation
   ```

8. **Property 8**: Endpoint URL Override for All Operations
   ```python
   # Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
   @given(operation=sampled_from(DATAZONE_OPERATIONS),
          endpoint_url=urls())
   @settings(max_examples=100)
   def test_endpoint_override_all_operations(operation, endpoint_url):
       # Test implementation
   ```

9. **Property 9**: Endpoint URL Override Consistency
   ```python
   # Feature: remove-datazone-internal-client, Property 9: Endpoint URL Override Consistency
   @given(operation=sampled_from(DATAZONE_OPERATIONS))
   @settings(max_examples=100)
   def test_endpoint_override_consistency(operation):
       # Test implementation
   ```

### Test Execution Strategy

1. **Pre-Migration**: Run full test suite to establish baseline
2. **During Migration**: Run tests after each component update
3. **Post-Migration**: Run full test suite including new property tests
4. **Integration Testing**: Execute against real AWS DataZone service
5. **Regression Testing**: Verify all existing functionality still works

### Test Environment Setup

- Use moto or localstack for unit tests where possible
- Use real AWS DataZone for integration tests
- Set `DATAZONE_ENDPOINT_URL` for testing against non-production endpoints
- Mock boto3 clients for testing error conditions

## Migration Risks and Mitigation

### Risk 1: Public API Missing Features

**Risk**: Public DataZone API may not support all features used by internal client

**Impact**: High - Could break existing functionality

**Mitigation**:
- Comprehensive API compatibility testing before migration
- Implement graceful degradation for unsupported features
- Document all limitations clearly
- Provide alternative approaches where possible
- Consider feature flags to enable/disable functionality

**Contingency**: If critical features are missing, maintain internal client for those specific operations only

### Risk 2: Breaking Changes in Boto3

**Risk**: Latest boto3 version may have breaking changes

**Impact**: Medium - Could require code updates beyond client migration

**Mitigation**:
- Test with latest boto3 in isolated environment first
- Review boto3 changelog for breaking changes
- Pin boto3 version in requirements.txt
- Run full test suite with new version before deployment

### Risk 3: Connection Type Compatibility

**Risk**: Workflow connection types may not work with public client

**Impact**: High - Would break workflow deployments

**Mitigation**:
- Test all connection types thoroughly
- Verify property names match public API expectations
- Keep custom model file if needed for specific connection types
- Document any connection type limitations

### Risk 4: Test Coverage Gaps

**Risk**: Existing tests may not catch all regressions

**Impact**: Medium - Could deploy broken functionality

**Mitigation**:
- Add property-based tests for comprehensive coverage
- Increase integration test coverage
- Manual testing of critical workflows
- Staged rollout with monitoring

### Risk 5: Endpoint Override Mechanism

**Risk**: Endpoint URL override may work differently with public client

**Impact**: Medium - Would break testing against non-production environments

**Mitigation**:
- Test endpoint override thoroughly
- Verify mechanism is identical to internal client
- Document any differences
- Provide clear error messages if override fails

## Implementation Plan

### Phase 1: Preparation (Week 1)

1. Update boto3 to latest version in development environment
2. Verify all required DataZone operations exist in public client
3. Document API compatibility findings
4. Create feature branch for migration

### Phase 2: Code Migration (Week 1-2)

1. Update `datazone.py`:
   - Remove `_get_datazone_internal_client()` function
   - Update all references

2. Update `project_manager.py`:
   - Modify `_create_project_via_datazone_api()`
   - Add graceful degradation for `customerProvidedRoleConfigs`
   - Update error handling

3. Update `connection_creator.py`:
   - Remove `_get_internal_datazone_client()` method
   - Remove `_internal_client` instance variable
   - Update connection creation logic

4. Update `datazone_handler.py`:
   - Remove internal client creation
   - Update connection handling

### Phase 3: Resource Cleanup (Week 2)

1. Remove `datazone-internal-2018-05-10.json`
2. Evaluate and potentially remove `datazone-2018-05-10.json`
3. Update GitHub workflows
4. Update test setup scripts

### Phase 4: Testing (Week 2-3)

1. Run unit tests
2. Add property-based tests
3. Run integration tests
4. Manual testing of critical workflows
5. Test endpoint URL override

### Phase 5: Documentation (Week 3)

1. Update code comments and docstrings
2. Update README with boto3 version requirement
3. Document any API limitations
4. Update user-facing documentation

### Phase 6: Deployment (Week 4)

1. Merge feature branch
2. Deploy to test environment
3. Monitor for issues
4. Deploy to production
5. Monitor and validate

## Success Criteria

The migration is considered successful when:

1. All unit tests pass
2. All property-based tests pass
3. All integration tests pass
4. No references to `datazone-internal` remain in code
5. `datazone-internal-2018-05-10.json` is removed
6. GitHub workflows updated and passing
7. Documentation updated
8. boto3 dependency updated to latest version
9. All existing functionality works as before
10. Endpoint URL override mechanism works correctly

## Rollback Plan

If critical issues are discovered post-deployment:

1. Revert to previous commit
2. Restore `datazone-internal` client usage
3. Restore custom model files
4. Restore GitHub workflow configurations
5. Document issues encountered
6. Plan remediation approach

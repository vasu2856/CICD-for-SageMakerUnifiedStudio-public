# Implementation Plan: Deploy Dry Run

## Overview

Implement the `--dry-run` option for `smus-cicd deploy` by building a `DryRunEngine` orchestrator with 12 phase-specific checkers, a structured report model, and CLI integration. The engine runs in standalone dry-run mode or as an automatic pre-deployment validation gate. Each task builds incrementally, starting with data models, then checkers, then the engine, and finally CLI wiring.

## Tasks

- [x] 1. Create data models and report formatter
  - [x] 1.1 Create `src/smus_cicd/commands/dry_run/__init__.py`, `models.py` with `Severity` enum (OK/WARNING/ERROR), `Phase` enum (12 phases in order), `Finding` dataclass, `DryRunContext` dataclass, and `DryRunReport` dataclass with `add_findings()`, `ok_count`, `warning_count`, `error_count`, `has_blocking_errors()`, and `render()` methods
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 1.2 Create `src/smus_cicd/commands/dry_run/report.py` with `ReportFormatter` class implementing `to_text(report)` (severity icons ✅/⚠️/❌, grouped by phase, summary counts) and `to_json(report)` (machine-readable JSON with `summary` and `phases` keys)
    - _Requirements: 7.6, 7.7_

  - [x] 1.3 Write property test for report structure correctness
    - **Property 15: Report structure correctness**
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 1.4 Write property test for JSON report round-trip
    - **Property 17: JSON report round-trip**
    - **Validates: Requirements 7.7**

  - [x] 1.5 Write unit tests for models and report formatter
    - Test Finding creation, report aggregation, severity counting, empty report
    - Test text formatting with mixed severities, JSON formatting, empty report rendering
    - _Requirements: 10.4_

- [x] 2. Implement manifest and bundle checkers
  - [x] 2.1 Create `src/smus_cicd/commands/dry_run/checkers/__init__.py` with `Checker` protocol defining `check(context) -> List[Finding]`
    - _Requirements: 5.7_

  - [x] 2.2 Create `checkers/manifest_checker.py` — load manifest via `ApplicationManifest.from_file()`, resolve target stage, validate env var references (`${VAR_NAME}` and `$VAR_NAME`) against `target_config.environment_variables` and `os.environ`. Return ERROR for missing/unparseable manifest or missing target stage; WARNING for unresolved env vars
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.3 Create `checkers/bundle_checker.py` — open bundle ZIP, enumerate files into `context.bundle_files`, cross-reference storage/git items from `deployment_configuration`, validate `catalog/catalog_export.json` structure if present (populate `context.catalog_data`). Return ERROR for missing artifacts, invalid ZIP, invalid catalog JSON
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 2.4 Write property test for manifest validation error reporting
    - **Property 5: Manifest validation error reporting**
    - **Validates: Requirements 2.1, 2.2**

  - [x] 2.5 Write property test for environment variable detection
    - **Property 4: Environment variable detection**
    - **Validates: Requirements 2.5**

  - [x] 2.6 Write property test for bundle file enumeration
    - **Property 6: Bundle file enumeration**
    - **Validates: Requirements 3.1**

  - [x] 2.7 Write property test for missing artifact detection
    - **Property 7: Missing artifact detection**
    - **Validates: Requirements 3.3, 3.4, 3.5**

  - [x] 2.8 Write property test for catalog export schema validation
    - **Property 8: Catalog export schema validation**
    - **Validates: Requirements 3.6**

  - [x] 2.9 Write unit tests for manifest and bundle checkers
    - Test valid manifest, invalid YAML, missing stage, unresolved vars, valid ZIP, missing artifacts, catalog validation, bad ZIP
    - _Requirements: 10.5_

- [x] 3. Implement permission and connectivity checkers
  - [x] 3.1 Create `checkers/permission_checker.py` — use `iam:SimulatePrincipalPolicy` to verify IAM permissions. Build permissions map from deployment config (S3, DataZone, catalog, IAM, QuickSight) plus `BOOTSTRAP_PERMISSION_MAP` for each bootstrap action type, plus Glue permissions when catalog assets contain Glue references. Fall back to WARNING if `SimulatePrincipalPolicy` itself is denied
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13_

  - [x] 3.2 Create `checkers/connectivity_checker.py` — call `datazone:GetDomain`, check project existence via `get_project_by_name()`, call `s3:HeadBucket` for each unique S3 bucket, check Airflow environment reachability if workflow bootstrap actions are configured
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.3 Write property test for permission set correctness
    - **Property 9: Permission set correctness**
    - **Validates: Requirements 4.1–4.13**

  - [x] 3.4 Write property test for S3 bucket reachability
    - **Property 14: S3 bucket reachability**
    - **Validates: Requirements 6.3, 6.5**

  - [x] 3.5 Write unit tests for permission and connectivity checkers
    - Test all permission types, denied permissions, API failures, reachable/unreachable domain, bucket, Airflow
    - _Requirements: 10.3, 10.6_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement deployment phase simulation checkers
  - [x] 5.1 Create `checkers/project_checker.py` — simulate project initialization using `get_project_by_name()`. Return OK if project exists, OK if not found but `create=True`, ERROR if not found and `create=False`
    - _Requirements: 5.1, 6.2_

  - [x] 5.2 Create `checkers/quicksight_checker.py` — simulate QuickSight deployment if configured, report which dashboards would be exported/imported using read-only checks from `helpers/quicksight.py`
    - _Requirements: 5.5_

  - [x] 5.3 Create `checkers/storage_checker.py` — simulate storage deployment for each storage item, report target S3 bucket, prefix, and file count per item
    - _Requirements: 5.2_

  - [x] 5.4 Create `checkers/git_checker.py` — simulate git deployment for each git item, report target connection, repository, and file count per item
    - _Requirements: 5.3_

  - [x] 5.5 Create `checkers/catalog_checker.py` — validate catalog export data from `context.catalog_data`, check required fields (`type`, `name`, `identifier`), verify cross-references, report count of each resource type
    - _Requirements: 5.4, 8.1, 8.2, 8.3, 8.4_

  - [x] 5.6 Create `checkers/workflow_checker.py` — validate workflow YAML files for valid syntax, required top-level Airflow DAG keys, and env var references against `target_config.environment_variables`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 5.7 Create `checkers/bootstrap_checker.py` — list each bootstrap action that would execute including type and parameters, using action registry from `bootstrap/action_registry.py`
    - _Requirements: 5.6_

  - [x] 5.8 Write property test for project existence simulation
    - **Property 10: Project existence simulation**
    - **Validates: Requirements 5.1, 6.2**

  - [x] 5.9 Write property test for storage simulation reporting
    - **Property 11: Storage simulation reporting**
    - **Validates: Requirements 5.2**

  - [x] 5.10 Write property test for catalog resource type counting
    - **Property 12: Catalog resource type counting**
    - **Validates: Requirements 5.4, 8.4**

  - [x] 5.11 Write property test for catalog resource field validation
    - **Property 18: Catalog resource field validation**
    - **Validates: Requirements 8.1**

  - [x] 5.12 Write property test for catalog cross-reference resolution
    - **Property 19: Catalog cross-reference resolution**
    - **Validates: Requirements 8.2**

  - [x] 5.13 Write property test for workflow file validation
    - **Property 20: Workflow file validation**
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [x] 5.14 Write property test for bootstrap action listing
    - **Property 22: Bootstrap action listing**
    - **Validates: Requirements 5.6**

  - [x] 5.15 Write unit tests for all deployment phase simulation checkers
    - Test project_checker, quicksight_checker, storage_checker, git_checker, catalog_checker, workflow_checker, bootstrap_checker with valid/invalid inputs and edge cases
    - _Requirements: 10.2, 10.5_

- [x] 6. Implement dependency checker
  - [x] 6.1 Create `checkers/dependency_checker.py` — validate pre-existing AWS resources and DataZone types referenced by catalog export data. Implement Glue Data Catalog resource validation (tables, views, databases via `glue:GetTable`, `glue:GetDatabase`, `glue:GetPartitions`), data source validation (`datazone:ListDataSources`), custom form type validation (`datazone:GetFormType`), custom asset type validation (`datazone:SearchTypes`), form type revision validation, managed resource skipping (`amazon.datazone.` prefix), and caching for all API calls
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 13.11, 13.12, 13.13_

  - [x] 6.2 Write property test for Glue Data Catalog resource dependency detection
    - **Property 23: Glue Data Catalog resource dependency detection**
    - **Validates: Requirements 13.1, 13.2, 13.3**

  - [x] 6.3 Write property test for data source dependency detection
    - **Property 24: Data source dependency detection**
    - **Validates: Requirements 13.4, 13.5**

  - [x] 6.4 Write property test for custom form type dependency detection
    - **Property 25: Custom form type dependency detection**
    - **Validates: Requirements 13.6, 13.7, 13.12**

  - [x] 6.5 Write property test for custom asset type dependency detection
    - **Property 26: Custom asset type dependency detection**
    - **Validates: Requirements 13.8, 13.9, 13.12**

  - [x] 6.6 Write property test for form type revision resolution
    - **Property 27: Form type revision resolution**
    - **Validates: Requirements 13.10, 13.11**

  - [x] 6.7 Write property test for dependency check caching
    - **Property 28: Dependency check caching**
    - **Validates: Requirements 13.1, 13.2 (caching invariant)**

  - [x] 6.8 Write unit tests for dependency checker
    - Test missing Glue tables/views/databases, missing data sources, missing custom form types, missing custom asset types, unresolvable revisions, managed resource skipping, caching behavior, partition accessibility
    - _Requirements: 10.7_

- [x] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement DryRunEngine orchestrator
  - [x] 8.1 Create `src/smus_cicd/commands/dry_run/engine.py` — instantiate all 12 checkers in phase order, call `checker.check(context)` for each, add findings to `DryRunReport`. Implement fail-fast on manifest errors (Phase 1 ERROR → return immediately). Continue through all other phases even when errors are found
    - _Requirements: 5.7, 7.1, 7.2, 7.3_

  - [x] 8.2 Write property test for phase ordering invariant
    - **Property 13: Phase ordering invariant**
    - **Validates: Requirements 5.7**

  - [x] 8.3 Write property test for no-mutation invariant
    - **Property 1: No-mutation invariant**
    - **Validates: Requirements 1.1**

  - [x] 8.4 Write property test for dry-run idempotence
    - **Property 21: Dry-run idempotence**
    - **Validates: Requirements 11.6**

  - [x] 8.5 Write unit tests for DryRunEngine
    - Test phase ordering, early termination on manifest error, full flow with mixed findings
    - _Requirements: 10.2_

- [x] 9. Integrate with CLI deploy command
  - [x] 9.1 Modify `src/smus_cicd/cli.py` to add `--dry-run` (bool), `--output` (str, "text"/"json"), and `--skip-validation` (bool) options to the `deploy()` function. Implement three execution paths: standalone dry-run, normal deploy with pre-deployment validation, and normal deploy without validation (`--skip-validation`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10_

  - [x] 9.2 Write property test for CLI option compatibility
    - **Property 2: CLI option compatibility**
    - **Validates: Requirements 1.3**

  - [x] 9.3 Write property test for event suppression under dry-run
    - **Property 3: Event suppression under dry-run**
    - **Validates: Requirements 1.4**

  - [x] 9.4 Write property test for exit code correctness
    - **Property 16: Exit code correctness**
    - **Validates: Requirements 7.4, 7.5**

  - [x] 9.5 Write property test for pre-deployment validation gate
    - **Property 29: Pre-deployment validation gate**
    - **Validates: Requirements 14.1, 14.2, 14.3**

  - [x] 9.6 Write property test for skip-validation bypass
    - **Property 30: Skip-validation bypass**
    - **Validates: Requirements 14.7**

  - [x] 9.7 Write property test for pre-deployment event suppression
    - **Property 31: Pre-deployment event suppression**
    - **Validates: Requirements 14.9**

  - [x] 9.8 Write property test for pre-deployment validation uses same engine
    - **Property 32: Pre-deployment validation uses same engine**
    - **Validates: Requirements 14.8**

  - [x] 9.9 Write unit tests for CLI deploy integration
    - Test standalone dry-run, pre-deployment validation pass → deploy, pre-deployment validation fail → abort, --skip-validation bypass, --dry-run + --skip-validation interaction
    - _Requirements: 10.8_

- [x] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Add Hypothesis dependency and create property test file
  - [x] 11.1 Add `hypothesis>=6.0.0` to `[project.optional-dependencies] dev` in `pyproject.toml`
    - _Requirements: 10.1_

  - [x] 11.2 Create `tests/unit/commands/dry_run/__init__.py` and `tests/unit/commands/dry_run/test_properties.py` with all 32 property-based tests using Hypothesis (`@settings(max_examples=100)`). Each test annotated with property number and requirements clause
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [x] 12. Lint and format compliance
  - [x] 12.1 Run `black`, `isort`, `flake8`, and `mypy` against all new dry-run modules and test files. Fix any violations
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 13. Integration tests
  - [x] 13.1 Create `tests/integration/dry_run/` directory with integration tests covering: happy path (valid manifest + bundle → zero errors), invalid manifest, missing permissions, unreachable resources, invalid bundle, idempotence, missing Glue dependencies, missing DataZone types, pre-deployment validation pass → deploy proceeds, pre-deployment validation fail → abort, and --skip-validation bypass
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (32 properties)
- Unit tests validate specific examples and edge cases
- The design uses Python — all code examples and implementations use Python
- All checkers implement the `Checker` protocol with a `check(context) -> List[Finding]` method
- Hypothesis is used for property-based testing with `@settings(max_examples=100)`

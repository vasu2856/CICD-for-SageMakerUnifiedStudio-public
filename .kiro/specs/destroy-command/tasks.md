# Implementation Plan: `destroy` Command

## Overview

Implement the `destroy` command as the inverse of `deploy`, following a strict two-phase model (validate-then-destroy). New files: `operator_registry.py` and `destroy.py`. Modified files: `quicksight.py`, `cli.py`, and the integration test.

## Tasks

- [x] 1. Create operator registry module
  - Create `src/smus_cicd/helpers/operator_registry.py` with a module-level `OPERATOR_REGISTRY` dict
  - Add the initial entry: `"airflow.providers.amazon.aws.operators.glue.GlueJobOperator"` → `{"resource_name_field": "job_name", "delete_fn": _delete_glue_job}`
  - Implement `_delete_glue_job(resource_name, region)` calling `boto3.client('glue').delete_job(JobName=resource_name)`; treat `EntityNotFoundException` as not-found (return without raising)
  - _Requirements: 12.1_

- [x] 2. Add QuickSight list helpers
  - [x] 2.1 Add `list_dashboards(aws_account_id, region) -> List[Dict]` to `src/smus_cicd/helpers/quicksight.py`
    - Paginate `client.list_dashboards()` using `NextToken`, following the same pattern as the existing `list_datasets` function
    - Return list of `DashboardSummaryList` entries
    - _Requirements: 6.2_
  - [ ]* 2.2 Write property test for `list_dashboards` pagination
    - **Property: `list_dashboards` with multiple pages returns all items across all pages**
    - **Validates: Requirements 6.2**
  - [x] 2.3 Add `list_data_sources(aws_account_id, region) -> List[Dict]` to `src/smus_cicd/helpers/quicksight.py`
    - Paginate `client.list_data_sources()` using `NextToken`, following the same pattern as `list_datasets`
    - Return list of `DataSources` entries
    - _Requirements: 6.2_
  - [ ]* 2.4 Write property test for `list_data_sources` pagination
    - **Property: `list_data_sources` with multiple pages returns all items across all pages**
    - **Validates: Requirements 6.2**

- [x] 3. Implement data models and pure helper functions in `destroy.py`
  - Create `src/smus_cicd/commands/destroy.py`
  - Define dataclasses: `ResourceToDelete`, `S3Target`, `ValidationResult`, `ResourceResult`
  - Implement `_resolve_resource_prefix(stage_name, qs_config) -> str` — reads `overrideParameters.ResourceIdOverrideConfiguration.PrefixForAllResources` and replaces `{stage.name}` with `stage_name`
  - Implement `_discover_workflow_created_resources(workflow_yaml, stage_name) -> List[ResourceToDelete]` — iterates tasks, matches `operator` field against `OPERATOR_REGISTRY`, extracts resource name from `resource_name_field`; skips tasks with `{` in the resource name (template variable warning); skips tasks whose operator is not in registry
  - Implement `_resolve_s3_targets(stage_config, connections) -> List[S3Target]` — builds list from `deployment_configuration.storage` and `deployment_configuration.git`, deduplicates overlapping prefixes (if one prefix is a subdirectory of another, keep only the parent)
  - _Requirements: 6.1, 7.6, 11.1, 11.2, 12.2, 12.5_
  - [ ]* 3.1 Write unit tests for `_resolve_resource_prefix`
    - Test `{stage.name}` substitution with various stage names
    - Test prefix template with no substitution variable (returned as-is)
    - _Requirements: 6.1_
  - [ ]* 3.2 Write property test for `_discover_workflow_created_resources`
    - **Property 14: Operator registry drives resource deletion** — tasks in registry produce `ResourceToDelete`; tasks not in registry produce `skipped`
    - **Validates: Requirements 11.1, 11.2**
  - [ ]* 3.3 Write property test for template variable detection
    - **Property 16: Template variables in resource names cause skip** — any `job_name` containing `{` must be skipped with no delete call
    - **Validates: Requirements 12.5**
  - [ ]* 3.4 Write property test for S3 prefix deduplication
    - **Property 9: S3 prefix deduplication** — when one `targetDirectory` is a subdirectory of another, only the parent prefix appears in the output list
    - **Validates: Requirements 7.6**
  - [ ]* 3.5 Write property test for `_discover_workflow_created_resources` count
    - **Property 15: Workflow YAML parsing extracts all registry-matching tasks** — N tasks with registry operators → exactly N `ResourceToDelete` entries
    - **Validates: Requirements 12.2**

- [x] 4. Implement validation phase (`_validate_stage` and `_parse_workflow_yaml_from_s3`)
  - Implement `_parse_workflow_yaml_from_s3(bucket, key, region) -> dict` — fetches object from S3 and parses YAML; returns empty dict on any error (logs warning)
  - Implement `_validate_stage(stage_name, stage_config, manifest, region) -> ValidationResult`:
    - Resolve domain + project IDs via `get_domain_from_target_config`
    - Resolve S3 connections via `get_project_connections`
    - Enumerate QuickSight resources by prefix using `list_dashboards`, `list_datasets`, `list_data_sources`; record collision error if count exceeds declared `content.quicksight` length
    - For each workflow in `content.workflows`: reconstruct name via `generate_workflow_name`, find ARN via `find_workflow_arn`, call `list_workflow_runs` to detect active runs; record collision error if more than one workflow ARN matches
    - Fetch and parse each workflow YAML from S3; call `_discover_workflow_created_resources`
    - Call `_resolve_s3_targets` to build S3 prefix list
    - Collect ALL errors and warnings without aborting early; return `ValidationResult`
  - _Requirements: 3.1, 3.2, 3.11, 3.12, 5.1, 6.1, 12.2_
  - [ ]* 4.1 Write property test for collect-all-errors validation
    - **Property 3: All validation errors are collected before aborting** — multiple stages each with one error → all errors appear in consolidated report
    - **Validates: Requirements 3.2**
  - [ ]* 4.2 Write unit tests for QuickSight collision detection
    - Prefix scan returns more resources than declared → validation error recorded, other stages still validated
    - _Requirements: 3.11_
  - [ ]* 4.3 Write unit tests for Airflow collision detection
    - Multiple workflows match reconstructed name → validation error recorded
    - _Requirements: 3.12_

- [x] 5. Implement destruction phase (`_destroy_stage`)
  - Implement `_destroy_stage(stage_name, stage_config, manifest, validation_result, region, output) -> List[ResourceResult]`:
    - **Step a**: Delete Workflow_Created_Resources from `validation_result.resources` where `resource_type` is a registry type (e.g. `glue_job`); call registry `delete_fn`; treat `EntityNotFoundException` as `not_found`
    - **Step b**: Delete Airflow workflows via `delete_workflow`; treat not-found as `not_found`. MWAA Serverless automatically terminates active runs when a workflow is deleted.
    - **Step d**: Delete QuickSight dashboards (prefix-matched), then datasets, then data sources; treat not-found as `not_found`
    - **Step e**: Delete S3 objects at each `S3Target` prefix via `list_objects` + `delete_objects`; treat empty prefix as `not_found` warning
    - **Step f**: Delete DataZone project only if `stage_config.project.create is True`; use `get_domain_from_target_config`, `get_project_id_by_name`, `delete_project`; treat not-found as `not_found`
    - For all non-recoverable errors: log, record `error`, continue processing remaining resources
  - _Requirements: 4.1, 5.3, 5.4, 6.3, 7.1, 7.2, 8.1, 8.2, 9.1, 9.3_
  - [ ]* 5.1 Write property test for destruction ordering
    - **Property 4: Destruction ordering invariant** — mock all AWS calls and verify call order: Glue delete → `delete_workflow` → QuickSight → S3 → `delete_project`
    - **Validates: Requirements 4.1**
  - [ ]* 5.3 Write property test for `project.create=false`
    - **Property 10: project.create=false prevents project deletion** — no `delete_project` call regardless of `--force`
    - **Validates: Requirements 8.2**
  - [ ]* 5.4 Write property test for QuickSight prefix filtering
    - **Property 7: QuickSight prefix filtering is exact** — only resource IDs starting with prefix are deleted; non-matching IDs are untouched
    - **Validates: Requirements 6.1_
  - [ ]* 5.5 Write property test for S3 deletion scope
    - **Property 8: S3 deletion is scoped to declared prefixes** — object keys passed to delete API are a subset of objects under declared `targetDirectory` prefixes
    - **Validates: Requirements 7.4**
  - [ ]* 5.6 Write property test for idempotency (not-found)
    - **Property 11: Not-found responses are idempotent** — any resource returning not-found → `not_found` recorded, processing continues, exit code 0
    - **Validates: Requirements 9.1**
  - [ ]* 5.7 Write property test for non-recoverable error resilience
    - **Property 12: Non-recoverable errors continue processing and set exit code** — one resource fails → remaining resources processed, exit code 1
    - **Validates: Requirements 9.3, 9.4**

- [x] 6. Implement `destroy_command` entry point and CLI wiring
  - Implement `destroy_command(manifest, targets, force, output)` in `destroy.py`:
    - Parse manifest via `ApplicationManifest.from_file`; exit 1 on failure
    - Resolve target list; validate all stage names exist in manifest; exit 1 with error listing invalid names and available names if any are invalid
    - Skip stages with absent/empty `deployment_configuration` (emit warning, continue)
    - Run `_validate_stage` for ALL targeted stages; collect all `ValidationResult` objects
    - If any `ValidationResult` has errors: print consolidated report, exit 1, no destructive calls
    - Print full destruction plan (all resources from all `ValidationResult.resources`, grouped by stage)
    - If `--force` not set: prompt for single confirmation; exit 0 on decline
    - If `--force` set: proceed without prompt
    - Call `_destroy_stage` for each targeted stage; collect `ResourceResult` lists
    - Print summary (counts of deleted/not_found/skipped/error per stage)
    - Exit 1 if any `ResourceResult` has `status == "error"`; else exit 0
    - When `--output JSON`: write single JSON object to stdout with `application_name`, `targets`, per-stage resource results; route all progress/log messages to stderr
  - Register `destroy` command in `src/smus_cicd/cli.py` (options: `--manifest/-m`, `--targets/-t`, `--force/-f`, `--output/-o`)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 9.5, 10.1, 10.2, 10.3, 10.4_
  - [ ]* 6.1 Write property test for invalid stage names
    - **Property 1: Invalid stage names abort before destruction** — any `--targets` with unknown stage name → exit 1, no deletion API calls
    - **Validates: Requirements 1.5**
  - [ ]* 6.2 Write property test for validation errors prevent destruction
    - **Property 2: Validation errors prevent all destructive actions** — any validation error → no deletion API calls, exit 1
    - **Validates: Requirements 3.1, 3.3**
  - [ ]* 6.3 Write property test for JSON output structure
    - **Property 13: JSON output contains required fields** — `--output JSON` stdout is valid JSON with `application_name`, `targets`, per-stage resource results each with `resource_type`, `resource_id`, `status`
    - **Validates: Requirements 10.2, 1.6**
  - [ ]* 6.4 Write unit tests for `--force` with collision error
    - `--force` set but validation has collision error → still aborts, no deletion calls
    - _Requirements: 3.3_

- [x] 7. Checkpoint — Ensure all unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Extend integration test with destroy steps
  - In `tests/integration/examples-analytics-workflows/dashboard-glue-quick/test_dashboard_glue_quick_workflow.py`, extend `test_dashboard_glue_quick_workflow_deployment` after the existing Step 9:
  - **Step 10**: Run `destroy --targets test --manifest <manifest_file> --force`; assert exit code 0
  - **Step 11**: Verify resources are gone:
    - QuickSight: `list_dashboards`, `list_data_sets`, `list_data_sources` with prefix `deployed-test-covid-` return empty lists
    - Glue: `boto3.client('glue').get_job(JobName=...)` raises `EntityNotFoundException` for `setup-covid-db-job`, `summary-glue-job`, `set-permission-check-job`
    - Airflow: reconstructed workflow name not found via `list_workflows`
    - S3: `list_objects` for `dashboard-glue-quick/bundle/` and `repos/` prefixes returns empty
    - DataZone: project still exists (because `project.create` is `false` in this manifest)
  - **Step 12**: Run destroy again with `--force`; assert exit code 0 and all resource results have `status == "not_found"` (idempotency check)
  - _Requirements: 9.1, 9.2, 9.5_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Bootstrap Connection deletion
  - In `_validate_stage`: scan `stage_config.bootstrap.actions` for `type: datazone.create_connection` entries; skip `default.*` names; skip if `project.create: true`; call `get_project_connections` to check existence; add found connections to `ValidationResult.resources` as `datazone_connection` type with connection ID in metadata
  - In `_destroy_stage`: add step (d) between Airflow workflow deletion and QuickSight deletion — for each `datazone_connection` resource, call `datazone_client.delete_connection(domainIdentifier=domain_id, identifier=connection_id)`; treat `ResourceNotFoundException` as `not_found`; never delete `default.*` connections
  - Add unit tests covering: connection discovery from bootstrap actions, `default.*` skip, `project.create=true` skip, successful deletion, not-found handling
  - _Requirements: 13.1–13.8_

- [x] 11. Final checkpoint after connection deletion
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- The `--force` flag bypasses the confirmation prompt but never bypasses collision errors
- Workflow run re-check at destruction time (not just at validation time) is required by Property 6

- [x] 12. Implement Catalog resource deletion
  - In `_validate_stage`: when `deployment_configuration.catalog` is present and not disabled, call `_search_target_resources` and `_search_target_type_resources` (from `catalog_import.py`) to enumerate all project-owned catalog resources; add them to `ValidationResult.resources` as typed entries (`catalog_glossary`, `catalog_glossary_term`, `catalog_form_type`, `catalog_asset_type`, `catalog_asset`, `catalog_data_product`); filter out managed form/asset types (`amazon.datazone.*`); add a warning to the destruction plan: "All project-owned catalog resources will be deleted, including any created manually. To skip catalog resource deletion, set `disable: true` under `deployment_configuration.catalog` in your manifest."
  - In `_destroy_stage`: add step (g) after S3 deletion — delete catalog resources in reverse dependency order: data products → assets → asset types → form types → glossary terms → glossaries; use the appropriate DataZone delete API for each type; treat not-found as `not_found`; remove the existing catalog warning from `_validate_stage` (it's now replaced by the destruction plan warning)
  - Update destruction ordering in `_destroy_stage` step labels (f→S3, g→catalog, h→project)
  - Add unit tests covering: catalog resource discovery when catalog config present, skip when absent/disabled, deletion ordering, not-found handling, managed resource filtering
  - _Requirements: 14.1–14.7, 15.1–15.2_

- [x] 13. Final checkpoint after catalog deletion
  - Ensure all tests pass, ask the user if questions arise.

# Testing Guide: `destroy` Command

Incremental testing plan ordered by complexity. Each test has a status tracker updated during implementation.

**Status legend:** ⬜ Not started · 🔄 In progress · ✅ Pass · ❌ Fail · ⏭️ Skipped

**Coverage target:** ≥ 90% line and branch coverage on `src/smus_cicd/commands/destroy.py` and `src/smus_cicd/helpers/operator_registry.py`.

---

## Part 1: Unit Tests

Tests run locally via `python -m pytest` from the workspace root. All AWS API calls are mocked using `unittest.mock.patch`.

Test file: `tests/unit/commands/test_destroy_command.py`

---

### Level 1 — Operator Registry (No Dependencies)

Validates the operator registry module in isolation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U1 | `OPERATOR_REGISTRY` contains an entry for `GlueJobOperator` | Key present in dict | ⬜ |
| U2 | `GlueJobOperator` entry has `resource_name_field` set to `"job_name"` | Field value correct | ⬜ |
| U3 | `GlueJobOperator` entry has a callable `delete_fn` | `callable(delete_fn)` is True | ⬜ |
| U4 | `_delete_glue_job` calls `boto3.client('glue').delete_job(JobName=resource_name)` | API called with correct params | ⬜ |
| U5 | `_delete_glue_job` treats `EntityNotFoundException` as not-found (returns without raising) | No exception raised | ⬜ |
| U6 | `_delete_glue_job` propagates non-EntityNotFoundException errors | Exception raised | ⬜ |

---

### Level 2 — QuickSight List Helpers (Pagination)

Validates the new `list_dashboards` and `list_data_sources` helpers in `quicksight.py`.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U7 | `list_dashboards` with a single page returns all items | All items from `DashboardSummaryList` returned | ⬜ |
| U8 | `list_dashboards` with multiple pages follows `NextToken` until exhausted | All items from all pages returned | ⬜ |
| U9 | `list_dashboards` with empty response returns empty list | Returns `[]` | ⬜ |
| U10 | `list_dashboards` propagates `ClientError` | Exception raised | ⬜ |
| U11 | `list_data_sources` with a single page returns all items | All items from `DataSources` returned | ⬜ |
| U12 | `list_data_sources` with multiple pages follows `NextToken` until exhausted | All items from all pages returned | ⬜ |
| U13 | `list_data_sources` with empty response returns empty list | Returns `[]` | ⬜ |
| U14 | `list_data_sources` propagates `ClientError` | Exception raised | ⬜ |

---

### Level 3 — Pure Helper Functions (No AWS Calls)

Validates pure logic functions that require no AWS calls.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U15 | `_resolve_resource_prefix` replaces `{stage.name}` with the stage key | `deployed-dev-covid-` for stage `dev` | ⬜ |
| U16 | `_resolve_resource_prefix` with no `{stage.name}` variable returns prefix unchanged | Original prefix returned | ⬜ |
| U17 | `_resolve_resource_prefix` with empty prefix returns empty string | Returns `""` | ⬜ |
| U18 | `_discover_workflow_created_resources` with a `GlueJobOperator` task returns one `ResourceToDelete` of type `glue_job` | One entry with correct `resource_id` | ⬜ |
| U19 | `_discover_workflow_created_resources` with an unregistered operator returns one `ResourceToDelete` of type `skipped` | One entry with `resource_type == "skipped"` | ⬜ |
| U20 | `_discover_workflow_created_resources` with a `GlueJobOperator` task where `job_name` contains `{` returns `skipped` | Skipped with warning, no delete call | ⬜ |
| U21 | `_discover_workflow_created_resources` with mixed operators returns correct counts of each type | Registry-matching count + skipped count = total tasks | ⬜ |
| U22 | `_discover_workflow_created_resources` with empty tasks dict returns empty list | Returns `[]` | ⬜ |
| U23 | `_resolve_s3_targets` with two non-overlapping storage entries returns two `S3Target` entries | Two entries in output | ⬜ |
| U24 | `_resolve_s3_targets` with overlapping prefixes (one is subdirectory of another) deduplicates to parent only | One entry in output | ⬜ |
| U25 | `_resolve_s3_targets` with storage and git entries combines both | Both types included | ⬜ |
| U26 | `_resolve_s3_targets` with no `deployment_configuration` returns empty list | Returns `[]` | ⬜ |

---

### Level 4 — Validation Phase (Mocked AWS)

Validates `_validate_stage` with mocked AWS responses.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U27 | Clean stage with no resources returns `ValidationResult` with empty errors and warnings | `errors == []`, `warnings == []` | ⬜ |
| U28 | QuickSight prefix scan returns more dashboards than declared → collision error recorded | Error in `ValidationResult.errors` | ⬜ |
| U29 | QuickSight prefix scan returns more datasets than declared → collision error recorded | Error in `ValidationResult.errors` | ⬜ |
| U30 | QuickSight prefix scan returns more data sources than declared → collision error recorded | Error in `ValidationResult.errors` | ⬜ |
| U31 | Multiple Airflow workflows match reconstructed name → collision error recorded | Error in `ValidationResult.errors` | ⬜ |
| U32 | Workflow with active runs → `active_workflow_runs` populated in `ValidationResult` | Run IDs present | ⬜ |
| U33 | Workflow YAML not found in S3 → warning recorded, no crash | Warning in `ValidationResult.warnings` | ⬜ |
| U34 | Multiple stages each with one error → all errors collected (no early abort) | All errors present across stages | ⬜ |
| U35 | Stage with absent `deployment_configuration` → warning emitted, stage skipped | Warning recorded | ⬜ |
| U36 | `get_domain_from_target_config` raises exception → error recorded, other stages still validated | Error recorded, processing continues | ⬜ |

---

### Level 5 — Destruction Phase (Mocked AWS)

Validates `_destroy_stage` with mocked AWS responses.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U37 | Full stage with all resource types: verify mock call order satisfies `stop_run` → `delete_glue_job` → `delete_workflow` → QuickSight → S3 → `delete_project` | Call order invariant holds | ⬜ |
| U38 | `stop_workflow_run` fails → `delete_workflow` NOT called for that workflow | No `delete_workflow` call | ⬜ |
| U39 | Workflow run active at validation but completed before destruction → `stop_workflow_run` not called | No stop call | ⬜ |
| U40 | New workflow run started after validation → `stop_workflow_run` called | Stop call made | ⬜ |
| U41 | `project.create=false` → no `delete_project` call | No `delete_project` call | ⬜ |
| U42 | `project.create=true` → `delete_project` called after all other resources | `delete_project` called last | ⬜ |
| U43 | QuickSight resource not found → `not_found` recorded, processing continues | `not_found` status, no crash | ⬜ |
| U44 | Glue job not found (`EntityNotFoundException`) → `not_found` recorded, processing continues | `not_found` status, no crash | ⬜ |
| U45 | S3 prefix empty → `not_found` warning, processing continues | Warning logged, no crash | ⬜ |
| U46 | Non-recoverable API error on one resource → error recorded, remaining resources processed | Error recorded, processing continues | ⬜ |
| U47 | All resources already absent → all `not_found`, exit code 0 | All statuses `not_found` | ⬜ |
| U48 | QuickSight prefix filter: resource list with mixed IDs → only IDs starting with prefix are deleted | Non-matching IDs untouched | ⬜ |
| U49 | S3 deletion: only objects under declared `targetDirectory` prefixes are deleted | No objects outside prefixes deleted | ⬜ |

---

### Level 6 — Command Entry Point and CLI Wiring

Validates `destroy_command` top-level logic and CLI registration.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U50 | Invalid stage name in `--targets` → error printed listing valid stages, exit 1, no API calls | Exit 1, no deletion calls | ⬜ |
| U51 | Manifest file not found → error printed, exit 1, no API calls | Exit 1, no deletion calls | ⬜ |
| U52 | Validation errors present → consolidated error report printed, exit 1, no destructive calls | Exit 1, no deletion calls | ⬜ |
| U53 | Multiple stages each with one validation error → all errors in consolidated report | All errors present | ⬜ |
| U54 | Clean validation → destruction plan printed with all discovered resources | Plan contains all resources | ⬜ |
| U55 | `--force` not set, user confirms → destruction proceeds | Deletion calls made | ⬜ |
| U56 | `--force` not set, user declines → exit 0, no destructive calls | No deletion calls | ⬜ |
| U57 | `--force` set → confirmation prompt skipped, destruction proceeds | No prompt, deletion calls made | ⬜ |
| U58 | `--force` set with collision error → still aborts, no deletion calls | Exit 1, no deletion calls | ⬜ |
| U59 | `--force` set with active workflow runs → `stop_workflow_run` called without prompt | Stop called, no prompt | ⬜ |
| U60 | One resource fails with non-recoverable error → remaining resources processed, exit 1 | All resources attempted, exit 1 | ⬜ |
| U61 | All resources deleted successfully → exit 0 | Exit 0 | ⬜ |
| U62 | `--output JSON` → stdout is valid JSON with `application_name`, `targets`, per-stage resource results | Valid JSON with required fields | ⬜ |
| U63 | `--output JSON` → no non-JSON content on stdout | Stdout is pure JSON | ⬜ |
| U64 | Summary printed at end showing counts of deleted/not_found/skipped/error per stage | Summary present | ⬜ |
| U65 | `destroy` command registered in `cli.py` with correct options | Command available via CLI | ⬜ |

---

### Level 7 — Edge Cases

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U66 | Stage with no QuickSight config → QuickSight deletion skipped | No QuickSight API calls | ⬜ |
| U67 | Stage with no workflows → workflow deletion skipped | No Airflow API calls | ⬜ |
| U68 | Stage with no storage/git → S3 deletion skipped | No S3 API calls | ⬜ |
| U69 | Workflow YAML with no tasks → empty `ResourceToDelete` list | Returns `[]` | ⬜ |
| U70 | `_parse_workflow_yaml_from_s3` with S3 error → returns empty dict, logs warning | Empty dict returned, no crash | ⬜ |
| U71 | `_parse_workflow_yaml_from_s3` with invalid YAML → returns empty dict, logs warning | Empty dict returned, no crash | ⬜ |
| U72 | Multiple targets specified → each stage validated and destroyed independently | Both stages processed | ⬜ |
| U73 | Default `--targets` (all stages) → all stages in manifest processed | All stages processed | ⬜ |

---

## Part 2: Coverage Requirements

The unit tests above are designed to achieve ≥ 90% line and branch coverage on the new modules.

### Coverage targets

| Module | Target Coverage | Key Branches to Cover |
|--------|----------------|----------------------|
| `src/smus_cicd/commands/destroy.py` | ≥ 90% | Validation errors vs clean, `--force` vs prompt, `project.create` true/false, each resource type present/absent, not-found vs error vs success for each type |
| `src/smus_cicd/helpers/operator_registry.py` | ≥ 90% | `EntityNotFoundException` path, non-EntityNotFoundException path |
| `src/smus_cicd/helpers/quicksight.py` (new functions only) | ≥ 90% | Single page, multi-page, empty response, error |

### Running with coverage

```bash
# Run destroy unit tests with coverage
python -m pytest tests/unit/commands/test_destroy_command.py \
  --cov=smus_cicd.commands.destroy \
  --cov=smus_cicd.helpers.operator_registry \
  --cov-report=term-missing \
  --cov-fail-under=90 \
  -v

# Include quicksight new helpers
python -m pytest tests/unit/commands/test_destroy_command.py \
  --cov=smus_cicd.commands.destroy \
  --cov=smus_cicd.helpers.operator_registry \
  --cov=smus_cicd.helpers.quicksight \
  --cov-report=term-missing \
  -v
```

---

## Part 3: Integration Test

The integration test extends the existing `tests/integration/examples-analytics-workflows/dashboard-glue-quick/test_dashboard_glue_quick_workflow.py`.

No new test file is created. Steps 10–12 are appended to `test_dashboard_glue_quick_workflow_deployment` after the existing Step 9 (pipeline tests pass).

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I1 | Step 10: `destroy --targets test --force` exits 0 | Exit code 0, success indicators in output | ⬜ |
| I2 | Step 11a: No QuickSight dashboards with `deployed-test-covid-` prefix exist after destroy | `list_dashboards` returns empty for prefix | ⬜ |
| I3 | Step 11b: No QuickSight datasets with `deployed-test-covid-` prefix exist after destroy | `list_data_sets` returns empty for prefix | ⬜ |
| I4 | Step 11c: No QuickSight data sources with `deployed-test-covid-` prefix exist after destroy | `list_data_sources` returns empty for prefix | ⬜ |
| I5 | Step 11d: Glue job `setup-covid-db-job` does not exist after destroy | `get_job` raises `EntityNotFoundException` | ⬜ |
| I6 | Step 11e: Glue job `summary-glue-job` does not exist after destroy | `get_job` raises `EntityNotFoundException` | ⬜ |
| I7 | Step 11f: Glue job `set-permission-check-job` does not exist after destroy | `get_job` raises `EntityNotFoundException` | ⬜ |
| I8 | Step 11g: Airflow workflow with reconstructed name does not exist after destroy | `list_workflows` returns no match | ⬜ |
| I9 | Step 11h: S3 prefix `dashboard-glue-quick/bundle/` is empty after destroy | `list_objects` returns empty | ⬜ |
| I10 | Step 11i: S3 prefix `repos/` is empty after destroy | `list_objects` returns empty | ⬜ |
| I11 | Step 11j: DataZone project still exists after destroy (`project.create: false`) | Project found via `get_project_id_by_name` | ⬜ |
| I12 | Step 12: Second destroy run exits 0 with all resources reported as `not_found` | Exit 0, all statuses `not_found` | ⬜ |

---

## Summary

| Section | Test Count | Type |
|---------|-----------|------|
| Level 1: Operator Registry | 6 | Unit |
| Level 2: QuickSight List Helpers | 8 | Unit |
| Level 3: Pure Helper Functions | 12 | Unit |
| Level 4: Validation Phase | 10 | Unit |
| Level 5: Destruction Phase | 13 | Unit |
| Level 6: Command Entry Point & CLI | 16 | Unit |
| Level 7: Edge Cases | 8 | Unit |
| **Total unit** | **73** | |
| Integration (Steps 10–12) | 12 | Integration |
| **Grand total** | **85** | |

### Automated Test File

| File | Tests |
|------|-------|
| `tests/unit/commands/test_destroy_command.py` | 73 |

### Requirements Traceability

| Requirement | Covered By |
|-------------|-----------|
| 1.1–1.4 CLI options | U65 |
| 1.5 Invalid stage names | U50 |
| 1.6 JSON output routing | U62, U63 |
| 2.1 Manifest validation | U51 |
| 2.2 `ApplicationManifest.from_file` reuse | U51 |
| 2.3 Missing `deployment_configuration` | U35 |
| 3.1 Full validation before destruction | U52, U58 |
| 3.2 Collect all errors | U34, U53 |
| 3.3 Errors abort before destruction | U52, U58 |
| 3.4 Destruction plan printed | U54 |
| 3.5 Confirmation prompt | U55, U56 |
| 3.6 User decline exits cleanly | U56 |
| 3.7 `--force` skips prompt | U57 |
| 3.8 Active runs in plan | U59 |
| 3.9 Abort on active run decline | U56 |
| 3.10 `--force` auto force-stop | U59 |
| 3.11 QuickSight collision detection | U28, U29, U30 |
| 3.12 Airflow collision detection | U31 |
| 4.1 Destruction ordering | U37 |
| 5.1 Workflow name reconstruction | U32 |
| 5.2 Workflow not found → warning | U33 |
| 5.3 Delete workflow after resources | U37 |
| 5.4 Stop runs before delete | U38, U39, U40 |
| 5.5 Wait for workflow deletion | U37 |
| 6.1 QuickSight prefix enumeration | U48 |
| 6.2 `list_dashboards`, `list_datasets`, `list_data_sources` | U7–U14 |
| 6.3 QuickSight not found → warning | U43 |
| 6.4 Delete order: dashboards → datasets → data sources | U37 |
| 6.5 No QuickSight config → skip | U66 |
| 7.1–7.2 S3 deletion via connections | U49 |
| 7.3 Empty S3 prefix → warning | U45 |
| 7.4 S3 scope boundary | U49 |
| 7.5 No storage/git → skip | U68 |
| 7.6 S3 prefix deduplication | U24 |
| 8.1 `project.create=true` → delete project | U42 |
| 8.2 `project.create=false` → no delete | U41 |
| 8.3 Project not found → warning | U44 |
| 9.1 Not-found → warning, continue | U43, U44, U45, U47 |
| 9.2 Not-found → exit 0 | U47 |
| 9.3 Non-recoverable error → continue | U46 |
| 9.4 Any error → exit 1 | U60 |
| 9.5 All absent → success | U47 |
| 10.1 TEXT output per-resource lines | U64 |
| 10.2 JSON output structure | U62 |
| 10.3 Summary at end | U64 |
| 10.4 JSON stdout purity | U63 |
| 11.1 Registry-matching operators deleted | U18, U21 |
| 11.2 Unregistered operators skipped | U19, U21 |
| 11.3 Notebook-created resources out of scope | U19 |
| 12.1 `OPERATOR_REGISTRY` with `GlueJobOperator` | U1–U3 |
| 12.2 Workflow YAML parsing | U18–U22 |
| 12.3 YAML not found → warning | U33, U70 |
| 12.4 Resource not found → warning | U44 |
| 12.5 Template variables → skip | U20 |
| 12.6 Workflow-created resources before workflow | U37 |
| 12.7 Resources in destruction plan | U54 |

### Correctness Properties Coverage

| Property | Unit Tests | Integration Tests |
|----------|-----------|-------------------|
| P1: Invalid stage names abort | U50 | — |
| P2: Validation errors prevent destruction | U52, U58 | — |
| P3: All errors collected | U34, U53 | — |
| P4: Destruction ordering invariant | U37 | I1 |
| P5: Workflow name reconstruction | U32 | — |
| P6: Active runs re-checked | U39, U40 | — |
| P6a: New runs caught at re-check | U40 | — |
| P7: QuickSight prefix filtering | U48 | I2–I4 |
| P8: S3 deletion scoped to prefixes | U49 | I9, I10 |
| P9: S3 prefix deduplication | U24 | — |
| P10: `project.create=false` prevents deletion | U41 | I11 |
| P11: Not-found is idempotent | U43–U47 | I12 |
| P12: Non-recoverable errors continue | U46, U60 | — |
| P13: JSON output structure | U62, U63 | — |
| P14: Operator registry drives deletion | U18–U21 | I5–I7 |
| P15: YAML parsing extracts all tasks | U21 | — |
| P16: Template variables cause skip | U20 | — |
| P17: Destruction plan complete | U54 | — |

---

## Running Tests

All commands from the workspace root.

### Run all destroy unit tests
```bash
python -m pytest tests/unit/commands/test_destroy_command.py -v
```

### Run with coverage report
```bash
python -m pytest tests/unit/commands/test_destroy_command.py \
  --cov=smus_cicd.commands.destroy \
  --cov=smus_cicd.helpers.operator_registry \
  --cov-report=term-missing \
  --cov-fail-under=90 \
  -v
```

### Run full unit test suite (including destroy)
```bash
python tests/run_tests.py --type unit
```

### Run integration test (requires AWS credentials)
```bash
# Ensure credentials are configured first
python -m pytest tests/integration/examples-analytics-workflows/dashboard-glue-quick/test_dashboard_glue_quick_workflow.py \
  -v -m integration -k "test_dashboard_glue_quick_workflow_deployment"
```

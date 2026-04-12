# Testing Guide: Deploy Dry Run

Incremental testing plan ordered by complexity. Each test has a status tracker updated during implementation.

**Status legend:** ⬜ Not started · 🔄 In progress · ✅ Pass · ❌ Fail · ⏭️ Skipped

---

## Part 1: Unit Tests

Tests run locally via `./venv/bin/python -m pytest` from the `CICD-for-SageMakerUnifiedStudio-public/` directory.

---

### Level 1 — Data Models (No Dependencies)

Validates Severity enum, Phase enum, Finding dataclass, DryRunContext, and DryRunReport aggregation logic.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U1 | Severity enum has exactly three values: OK, WARNING, ERROR | Enum members match | ⬜ |
| U2 | Phase enum has 12 values in deployment order | Enum members and order match | ⬜ |
| U3 | Finding dataclass stores severity, message, phase, resource, service, details | All fields accessible | ⬜ |
| U4 | DryRunReport.add_findings sets phase on each finding | Finding.phase populated | ⬜ |
| U5 | DryRunReport.ok_count returns count of OK findings | Count matches | ⬜ |
| U6 | DryRunReport.warning_count returns count of WARNING findings | Count matches | ⬜ |
| U7 | DryRunReport.error_count returns count of ERROR findings | Count matches | ⬜ |
| U8 | DryRunReport with mixed severities returns correct counts | All three counts correct | ⬜ |
| U9 | DryRunReport.has_blocking_errors returns True when ERROR findings exist in phase | Returns True | ⬜ |
| U10 | DryRunReport.has_blocking_errors returns False when no ERROR findings in phase | Returns False | ⬜ |
| U11 | Empty DryRunReport has zero counts for all severities | All counts are 0 | ⬜ |
| U12 | DryRunReport.findings_by_phase groups findings correctly | Findings grouped by phase | ⬜ |

---

### Level 2 — Report Formatter (Text & JSON)

Validates ReportFormatter text and JSON output generation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U13 | Text formatter includes ✅ icon for OK findings | Icon present | ⬜ |
| U14 | Text formatter includes ⚠️ icon for WARNING findings | Icon present | ⬜ |
| U15 | Text formatter includes ❌ icon for ERROR findings | Icon present | ⬜ |
| U16 | Text formatter groups findings by phase | Phase headers present | ⬜ |
| U17 | Text formatter includes summary counts | OK/WARNING/ERROR counts in output | ⬜ |
| U18 | JSON formatter produces valid JSON with `summary` and `phases` keys | Keys present, valid JSON | ⬜ |
| U19 | JSON `summary` contains `ok`, `warnings`, `errors` counts | Counts match report | ⬜ |
| U20 | JSON `phases` groups findings by phase name | Phase grouping correct | ⬜ |
| U21 | Empty report renders valid text output | No crash, valid output | ⬜ |
| U22 | Empty report renders valid JSON output | No crash, valid JSON | ⬜ |
| U23 | DryRunReport.render("text") delegates to text formatter | Text output returned | ⬜ |
| U24 | DryRunReport.render("json") delegates to JSON formatter | JSON output returned | ⬜ |

---

### Level 3 — Manifest Checker

Validates manifest loading, target stage resolution, and environment variable detection.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U25 | Valid manifest loads without ERROR findings | No ERROR findings | ⬜ |
| U26 | Invalid YAML produces ERROR finding with parse error details | ERROR finding with message | ⬜ |
| U27 | Missing manifest file produces ERROR finding with file path | ERROR finding with path | ⬜ |
| U28 | Valid target stage resolves without ERROR findings | No ERROR findings | ⬜ |
| U29 | Missing target stage produces ERROR with stage name and available stages | ERROR with stage list | ⬜ |
| U30 | Unresolved `${VAR_NAME}` reference produces WARNING finding | WARNING finding | ⬜ |
| U31 | Unresolved `$VAR_NAME` reference produces WARNING finding | WARNING finding | ⬜ |
| U32 | Resolved env var (in target_config.environment_variables) produces no WARNING | No WARNING | ⬜ |
| U33 | Resolved env var (in os.environ) produces no WARNING | No WARNING | ⬜ |
| U34 | Manifest with missing domain/project/deployment_configuration produces ERROR | ERROR finding | ⬜ |

---

### Level 4 — Bundle Checker

Validates bundle ZIP exploration, artifact cross-referencing, and catalog export validation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U35 | Valid ZIP enumerates all files into context.bundle_files | File set matches ZIP contents | ⬜ |
| U36 | OK finding reports exact file count from ZIP | Count in message | ⬜ |
| U37 | Invalid ZIP file produces ERROR finding | ERROR finding | ⬜ |
| U38 | Missing bundle path with no ./artifacts fallback produces ERROR | ERROR finding | ⬜ |
| U39 | Storage item with matching bundle files produces no ERROR | No ERROR | ⬜ |
| U40 | Storage item missing from bundle produces ERROR with item name | ERROR with name | ⬜ |
| U41 | Git item with matching bundle content produces no ERROR | No ERROR | ⬜ |
| U42 | Git item missing from bundle produces ERROR with item name | ERROR with name | ⬜ |
| U43 | Valid catalog_export.json populates context.catalog_data | Data populated | ⬜ |
| U44 | Invalid catalog_export.json produces ERROR with parse error | ERROR finding | ⬜ |
| U45 | Missing catalog_export.json when not referenced produces no ERROR | No ERROR | ⬜ |
| U46 | Bundle resolution from ./artifacts directory works | Bundle found and opened | ⬜ |

---

### Level 5 — Permission Checker

Validates IAM permission verification via SimulatePrincipalPolicy.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U47 | S3 permissions (PutObject, GetObject) checked for each target bucket | Actions in simulation call | ⬜ |
| U48 | DataZone permissions (GetDomain, GetProject, SearchListings) checked | Actions in simulation call | ⬜ |
| U49 | Catalog import permissions checked when catalog assets present | CreateAsset, CreateGlossary, etc. in call | ⬜ |
| U50 | IAM role permissions checked when role creation configured | CreateRole, AttachRolePolicy in call | ⬜ |
| U51 | QuickSight permissions checked when dashboards configured | DescribeDashboard, CreateDashboard in call | ⬜ |
| U52 | Denied permission produces ERROR with action name and resource ARN | ERROR with details | ⬜ |
| U53 | Allowed permission produces OK finding | OK finding | ⬜ |
| U54 | SimulatePrincipalPolicy AccessDenied falls back to WARNING | WARNING, not ERROR | ⬜ |
| U55 | Bootstrap action `workflow.create` adds correct IAM actions | airflow-serverless:CreateWorkflow in map | ⬜ |
| U56 | Bootstrap action `workflow.run` adds correct IAM actions | airflow-serverless:CreateWorkflowRun in map | ⬜ |
| U57 | Bootstrap action `workflow.logs` adds correct IAM actions | logs:GetLogEvents, logs:FilterLogEvents in map | ⬜ |
| U58 | Bootstrap action `workflow.monitor` adds correct IAM actions | GetWorkflow + log actions in map | ⬜ |
| U59 | Bootstrap action `quicksight.refresh_dataset` adds correct IAM actions | CreateIngestion, DescribeIngestion, ListDataSets | ⬜ |
| U60 | Bootstrap action `eventbridge.put_events` adds correct IAM actions | events:PutEvents in map | ⬜ |
| U61 | Bootstrap action `project.create_environment` adds correct IAM actions | datazone:CreateEnvironment in map | ⬜ |
| U62 | Bootstrap action `project.create_connection` adds correct IAM actions | datazone:CreateConnection in map | ⬜ |
| U63 | DataZone grant permissions checked when catalog assets present | CreateSubscriptionGrant, etc. in call | ⬜ |
| U64 | Glue permissions added when catalog assets contain Glue references | glue:GetTable, GetDatabase, GetPartitions | ⬜ |

---

### Level 6 — Connectivity Checker

Validates AWS resource reachability checks.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U65 | Reachable DataZone domain produces OK finding | OK finding | ⬜ |
| U66 | Unreachable DataZone domain produces ERROR with domain ID and error | ERROR finding | ⬜ |
| U67 | Existing DataZone project produces OK finding | OK finding | ⬜ |
| U68 | Missing project with create enabled produces OK finding | OK finding | ⬜ |
| U69 | Missing project without create enabled produces ERROR | ERROR finding | ⬜ |
| U70 | Accessible S3 bucket (HeadBucket succeeds) produces OK finding | OK finding | ⬜ |
| U71 | Inaccessible S3 bucket produces ERROR with bucket name and error | ERROR finding | ⬜ |
| U72 | Duplicate S3 bucket names checked only once | Single HeadBucket call per bucket | ⬜ |
| U73 | Reachable Airflow environment produces OK finding | OK finding | ⬜ |
| U74 | Unreachable Airflow environment produces ERROR | ERROR finding | ⬜ |
| U75 | No Airflow check when no workflow bootstrap actions configured | No Airflow API call | ⬜ |

---

### Level 7 — Project Checker

Validates project initialization simulation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U76 | Existing project produces OK finding | OK finding | ⬜ |
| U77 | Missing project with create=True produces OK finding | OK finding | ⬜ |
| U78 | Missing project with create=False produces ERROR finding | ERROR finding | ⬜ |
| U79 | API error during project check produces ERROR with error details | ERROR finding | ⬜ |

---

### Level 8 — QuickSight Checker

Validates QuickSight deployment simulation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U80 | QuickSight configured: reports dashboards that would be exported/imported | Dashboard names in findings | ⬜ |
| U81 | QuickSight not configured: no findings produced | Empty findings | ⬜ |
| U82 | QuickSight API error produces ERROR finding | ERROR finding | ⬜ |

---

### Level 9 — Storage & Git Checkers

Validates storage and git deployment simulation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U83 | Storage item produces OK finding with bucket, prefix, and file count | All three in message | ⬜ |
| U84 | Multiple storage items produce one finding per item | Finding count matches item count | ⬜ |
| U85 | Empty storage configuration produces no findings | Empty findings | ⬜ |
| U86 | Git item produces OK finding with connection, repository, and file count | All three in message | ⬜ |
| U87 | Multiple git items produce one finding per item | Finding count matches item count | ⬜ |
| U88 | Empty git configuration produces no findings | Empty findings | ⬜ |

---

### Level 10 — Catalog Checker

Validates catalog export data validation and cross-reference resolution.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U89 | Valid catalog data with all required fields produces no ERROR | No ERROR findings | ⬜ |
| U90 | Resource missing `type` field produces ERROR | ERROR finding | ⬜ |
| U91 | Resource missing `name` field produces ERROR | ERROR finding | ⬜ |
| U92 | Resource missing `identifier` field produces ERROR | ERROR finding | ⬜ |
| U93 | Resolvable cross-reference (glossary term → glossary) produces no ERROR | No ERROR | ⬜ |
| U94 | Unresolvable cross-reference produces ERROR | ERROR finding | ⬜ |
| U95 | Resource type counts reported correctly (glossaries, terms, asset types, form types, data products) | Counts in findings | ⬜ |
| U96 | Invalid catalog JSON produces ERROR with parse error | ERROR finding | ⬜ |
| U97 | Missing top-level keys (`metadata`, `resources`) produce ERROR | ERROR finding | ⬜ |
| U98 | No catalog data in context produces no findings | Empty findings | ⬜ |

---

### Level 11 — Dependency Checker (Glue Data Catalog)

Validates pre-existing Glue resource dependency detection.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U99 | Existing Glue table produces no ERROR | No ERROR | ⬜ |
| U100 | Missing Glue table produces ERROR with database name, table name, and referencing asset | ERROR with details | ⬜ |
| U101 | Existing Glue view produces no ERROR | No ERROR | ⬜ |
| U102 | Missing Glue view produces ERROR with database name, view name, and referencing asset | ERROR with details | ⬜ |
| U103 | Existing Glue database produces no ERROR | No ERROR | ⬜ |
| U104 | Missing Glue database produces ERROR with database name | ERROR with details | ⬜ |
| U105 | Glue table partition check succeeds produces no WARNING | No WARNING | ⬜ |
| U106 | Glue table partition check fails produces WARNING | WARNING finding | ⬜ |
| U107 | Glue view skips partition check | No GetPartitions call for views | ⬜ |
| U108 | Database existence cached — second check for same DB skips API call | Single GetDatabase call | ⬜ |
| U109 | Table existence cached — second check for same (db, table) skips API call | Single GetTable call | ⬜ |

---

### Level 12 — Dependency Checker (DataZone Types & Data Sources)

Validates DataZone type and data source dependency detection.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U110 | Existing data source produces no WARNING | No WARNING | ⬜ |
| U111 | Missing data source produces WARNING with type, database name, and referencing asset | WARNING with details | ⬜ |
| U112 | Existing custom form type produces no ERROR | No ERROR | ⬜ |
| U113 | Missing custom form type produces ERROR with form type name and referencing asset type | ERROR with details | ⬜ |
| U114 | Managed form type (`amazon.datazone.*`) skipped — no API call | No GetFormType call | ⬜ |
| U115 | Existing custom asset type produces no ERROR | No ERROR | ⬜ |
| U116 | Missing custom asset type produces ERROR with type identifier and referencing asset | ERROR with details | ⬜ |
| U117 | Managed asset type (`amazon.datazone.*`) skipped — no API call | No SearchTypes call | ⬜ |
| U118 | Resolvable form type revision produces no WARNING | No WARNING | ⬜ |
| U119 | Unresolvable form type revision produces WARNING with form type name and expected revision | WARNING with details | ⬜ |
| U120 | Data source lookup cached by (type, databaseName) | Single ListDataSources call per unique pair | ⬜ |
| U121 | Form type lookup cached by name | Single GetFormType call per unique name | ⬜ |
| U122 | Asset type lookup cached by identifier | Single SearchTypes call per unique identifier | ⬜ |

---

### Level 13 — Workflow Checker

Validates workflow YAML file validation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U123 | Valid workflow YAML produces no ERROR | No ERROR | ⬜ |
| U124 | Invalid YAML syntax produces ERROR with file name | ERROR finding | ⬜ |
| U125 | Missing required top-level DAG keys produces ERROR | ERROR finding | ⬜ |
| U126 | Unresolved env var in workflow produces WARNING | WARNING finding | ⬜ |
| U127 | Resolved env var in workflow produces no WARNING | No WARNING | ⬜ |
| U128 | No workflow files produces no findings | Empty findings | ⬜ |

---

### Level 14 — Bootstrap Checker

Validates bootstrap action listing.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U129 | Each bootstrap action produces OK finding with type and parameters | Type and params in message | ⬜ |
| U130 | Multiple bootstrap actions produce one finding per action | Finding count matches action count | ⬜ |
| U131 | Empty bootstrap actions list produces no findings | Empty findings | ⬜ |
| U132 | All 8 bootstrap action types produce correct findings | All types handled | ⬜ |

---

### Level 15 — DryRunEngine Orchestrator

Validates engine phase ordering, fail-fast behavior, and report assembly.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U133 | Engine runs all 12 phases in correct order | Phase order in report matches design | ⬜ |
| U134 | Manifest ERROR causes fail-fast — subsequent phases not executed | Only manifest phase in report | ⬜ |
| U135 | Non-manifest ERROR does not cause fail-fast — all phases run | All phases in report | ⬜ |
| U136 | Findings from all phases aggregated into single DryRunReport | All findings present | ⬜ |
| U137 | Engine passes shared DryRunContext to all checkers | Context populated by earlier phases available to later ones | ⬜ |
| U138 | Full flow with mixed OK/WARNING/ERROR produces correct report | Counts match | ⬜ |

---

### Level 16 — CLI Integration

Validates CLI deploy command integration with dry-run engine.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U139 | `--dry-run` flag runs DryRunEngine and renders report | Report output, no deploy_command call | ⬜ |
| U140 | `--dry-run` with zero errors exits with code 0 | Exit code 0 | ⬜ |
| U141 | `--dry-run` with errors exits with non-zero code | Exit code 1 | ⬜ |
| U142 | `--dry-run` suppresses EventBridge events regardless of `--emit-events` | No EventEmitter instantiated | ⬜ |
| U143 | `--output json` produces JSON report | JSON output | ⬜ |
| U144 | `--output text` produces text report (default) | Text output | ⬜ |
| U145 | Normal deploy (no flags) runs pre-deployment validation first | DryRunEngine called before deploy_command | ⬜ |
| U146 | Pre-deployment validation pass → deploy_command called | deploy_command invoked | ⬜ |
| U147 | Pre-deployment validation fail → deploy_command NOT called, exit 1 | deploy_command not invoked, exit 1 | ⬜ |
| U148 | Pre-deployment validation logs "Running pre-deployment validation..." | Log message present | ⬜ |
| U149 | Pre-deployment validation pass logs "Pre-deployment validation passed" with warning count | Log message present | ⬜ |
| U150 | Pre-deployment validation fail logs "Pre-deployment validation failed. Deployment aborted." | Log message present | ⬜ |
| U151 | `--skip-validation` skips DryRunEngine, calls deploy_command directly | No DryRunEngine call | ⬜ |
| U152 | `--dry-run` accepts all existing deploy options without parse error | No parse error | ⬜ |
| U153 | Pre-deployment validation suppresses EventBridge during validation phase | No events during validation | ⬜ |
| U154 | `--output json` with normal deploy (not `--dry-run`) renders validation in text | Text format for validation | ⬜ |

---

## Part 2: Property-Based Tests (Hypothesis)

Property tests use `@settings(max_examples=100)` and Hypothesis strategies to generate realistic inputs. All run via `./venv/bin/python -m pytest`.

---

### Level 17 — Report & Model Properties

Validates report structure and serialization correctness across random inputs.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P1 | **Property 15**: For any list of findings with arbitrary severities and phases, ok_count + warning_count + error_count equals total findings, and findings_by_phase groups correctly | Counts and grouping correct | ⬜ |
| P2 | **Property 17**: For any DryRunReport, JSON round-trip (to_json → json.loads) preserves summary counts | Round-trip equality | ⬜ |

---

### Level 18 — Manifest & Bundle Properties

Validates manifest validation and bundle exploration correctness across random inputs.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P3 | **Property 5**: For any input string, invalid YAML/schema → at least one ERROR; valid YAML/schema → no ERROR | Error detection correct | ⬜ |
| P4 | **Property 4**: For any manifest content with `${VAR}` / `$VAR` references and any env var dict, every unresolved var produces WARNING | All unresolved vars detected | ⬜ |
| P5 | **Property 6**: For any valid ZIP, BundleChecker reports OK with exact file count, context.bundle_files equals ZipFile.namelist() | Count and set match | ⬜ |
| P6 | **Property 7**: For any deployment config and bundle, every missing item produces ERROR, present items produce no ERROR | Missing detection correct | ⬜ |
| P7 | **Property 8**: For any JSON object, missing required top-level keys → ERROR; all keys present → no schema ERROR | Schema validation correct | ⬜ |

---

### Level 19 — Permission & Connectivity Properties

Validates permission set construction and reachability check correctness.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P8 | **Property 9**: For any deployment config, the IAM actions set equals the union of base actions + BOOTSTRAP_PERMISSION_MAP actions + Glue actions (when applicable). Denied actions produce findings with action name and ARN | Permission set correct | ⬜ |
| P9 | **Property 14**: For any set of S3 bucket names, HeadBucket called for each unique bucket. Success → OK, exception → ERROR with bucket name | Reachability correct | ⬜ |

---

### Level 20 — Deployment Phase Simulation Properties

Validates simulation checker correctness across random inputs.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P10 | **Property 10**: For any project config (create True/False) and DataZone response (exists/not found), correct OK or ERROR produced | Project simulation correct | ⬜ |
| P11 | **Property 11**: For any storage item and bundle, finding contains bucket name, prefix, and correct file count | Storage simulation correct | ⬜ |
| P12 | **Property 12**: For any catalog export with mixed resource types, CatalogChecker reports correct count per type | Resource counting correct | ⬜ |
| P13 | **Property 18**: For any catalog resource entry, missing required fields → ERROR; all fields present → no field ERROR | Field validation correct | ⬜ |
| P14 | **Property 19**: For any catalog with cross-references, unresolvable references → ERROR per reference | Cross-ref detection correct | ⬜ |
| P15 | **Property 20**: For any file content, invalid YAML → ERROR; missing DAG keys → ERROR; unresolved vars → WARNING | Workflow validation correct | ⬜ |
| P16 | **Property 22**: For any list of bootstrap actions, one OK finding per action with type and parameter keys | Bootstrap listing correct | ⬜ |

---

### Level 21 — Dependency Checker Properties

Validates dependency detection correctness across random catalog structures.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P17 | **Property 23**: For any assets with GlueTableFormType and any Glue API responses, ERROR for each missing (db, table/view) pair. Partition check for tables only | Glue dependency detection correct | ⬜ |
| P18 | **Property 24**: For any assets with DataSourceReferenceFormType and any ListDataSources responses, WARNING for each unmatched data source | Data source detection correct | ⬜ |
| P19 | **Property 25**: For any asset types with custom form type references, ERROR for missing custom types. Managed types (`amazon.datazone.*`) never checked | Form type detection correct | ⬜ |
| P20 | **Property 26**: For any assets with custom typeIdentifier, ERROR for missing custom types. Managed types never checked | Asset type detection correct | ⬜ |
| P21 | **Property 27**: For any assets with form type revisions, WARNING for unresolvable revisions | Revision detection correct | ⬜ |
| P22 | **Property 28**: For N assets referencing same Glue DB, GetDatabase called at most once. Same for (db, table) → GetTable at most once. Same caching for form types, asset types, data sources | Caching invariant holds | ⬜ |

---

### Level 22 — Engine & CLI Properties

Validates engine orchestration and CLI behavior correctness.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P23 | **Property 13**: For any dry-run execution, phases appear in design-specified order | Phase ordering invariant | ⬜ |
| P24 | **Property 1**: For any valid inputs, dry-run invokes zero mutating AWS API calls | No-mutation invariant | ⬜ |
| P25 | **Property 21**: For any inputs, two dry-run executions produce identical finding counts and messages | Idempotence invariant | ⬜ |
| P26 | **Property 2**: For any combination of existing deploy options, `--dry-run` accepted without parse error | CLI compatibility | ⬜ |
| P27 | **Property 3**: For any `--emit-events` value, `--dry-run` suppresses all EventBridge events | Event suppression | ⬜ |
| P28 | **Property 16**: For any DryRunReport, exit code is 0 iff error_count == 0 | Exit code correctness | ⬜ |
| P29 | **Property 29**: For any deploy without `--dry-run`/`--skip-validation`, DryRunEngine runs first. error_count > 0 → deploy_command not called. error_count == 0 → deploy_command called once | Pre-deployment gate | ⬜ |
| P30 | **Property 30**: For any deploy with `--skip-validation`, DryRunEngine never instantiated, deploy_command called once | Skip-validation bypass | ⬜ |
| P31 | **Property 31**: For any deploy without `--dry-run`/`--skip-validation`, no EventBridge events during validation phase | Pre-deployment event suppression | ⬜ |
| P32 | **Property 32**: For identical inputs, standalone dry-run and pre-deployment validation produce identical reports | Engine consistency | ⬜ |

---

## Part 3: Integration Tests

These tests require real AWS credentials and DataZone domains. Run from the `CICD-for-SageMakerUnifiedStudio-public/` directory after sourcing `.env`.

---

### Level 23 — Standalone Dry Run (Happy Path)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I1 | `smus-cicd deploy --dry-run` with valid manifest + bundle produces report with zero errors | Exit code 0, no ERROR findings | ⬜ |
| I2 | Dry-run report contains findings for all 12 phases | All phases present | ⬜ |
| I3 | `--output json` produces valid JSON report with correct structure | Valid JSON, summary + phases keys | ⬜ |
| I4 | `--output text` produces human-readable report with severity icons | Icons present | ⬜ |
| I5 | Repeated dry-run with same inputs produces identical results | Idempotent output | ⬜ |

---

### Level 24 — Standalone Dry Run (Error Detection)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I6 | Dry-run with invalid manifest (malformed YAML) reports manifest validation errors | ERROR in manifest phase | ⬜ |
| I7 | Dry-run with missing target stage reports error with available stages | ERROR with stage list | ⬜ |
| I8 | Dry-run with restricted IAM identity reports missing permissions | ERROR in permission phase | ⬜ |
| I9 | Dry-run targeting nonexistent S3 bucket reports connectivity error | ERROR in connectivity phase | ⬜ |
| I10 | Dry-run targeting nonexistent DataZone domain reports connectivity error | ERROR in connectivity phase | ⬜ |
| I11 | Dry-run with incomplete bundle reports missing artifact errors | ERROR in bundle phase | ⬜ |

---

### Level 25 — Dependency Validation (Integration)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I12 | Dry-run with catalog referencing nonexistent Glue tables reports dependency errors | ERROR in dependency phase | ⬜ |
| I13 | Dry-run with catalog referencing nonexistent Glue databases reports dependency errors | ERROR in dependency phase | ⬜ |
| I14 | Dry-run with catalog referencing nonexistent custom form types reports errors | ERROR in dependency phase | ⬜ |
| I15 | Dry-run with catalog referencing nonexistent custom asset types reports errors | ERROR in dependency phase | ⬜ |
| I16 | Dry-run with catalog referencing missing data sources reports warnings | WARNING in dependency phase | ⬜ |

---

### Level 26 — Pre-Deployment Validation (Integration)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I17 | Normal deploy (no flags) runs pre-deployment validation and proceeds when validation passes | Deployment completes | ⬜ |
| I18 | Normal deploy aborts when pre-deployment validation detects errors — no resources created | Exit code 1, no resources | ⬜ |
| I19 | `--skip-validation` bypasses validation and proceeds directly to deployment | No validation output, deployment runs | ⬜ |

---

## Summary

| Section | Test Count | Type |
|---------|-----------|------|
| Level 1: Data Models | 12 | Unit |
| Level 2: Report Formatter | 12 | Unit |
| Level 3: Manifest Checker | 10 | Unit |
| Level 4: Bundle Checker | 12 | Unit |
| Level 5: Permission Checker | 18 | Unit |
| Level 6: Connectivity Checker | 11 | Unit |
| Level 7: Project Checker | 4 | Unit |
| Level 8: QuickSight Checker | 3 | Unit |
| Level 9: Storage & Git Checkers | 6 | Unit |
| Level 10: Catalog Checker | 10 | Unit |
| Level 11: Dependency Checker (Glue) | 11 | Unit |
| Level 12: Dependency Checker (DataZone) | 13 | Unit |
| Level 13: Workflow Checker | 6 | Unit |
| Level 14: Bootstrap Checker | 4 | Unit |
| Level 15: DryRunEngine Orchestrator | 6 | Unit |
| Level 16: CLI Integration | 16 | Unit |
| Level 17: Report & Model Properties | 2 | Property (Hypothesis) |
| Level 18: Manifest & Bundle Properties | 5 | Property (Hypothesis) |
| Level 19: Permission & Connectivity Properties | 2 | Property (Hypothesis) |
| Level 20: Deployment Phase Simulation Properties | 7 | Property (Hypothesis) |
| Level 21: Dependency Checker Properties | 6 | Property (Hypothesis) |
| Level 22: Engine & CLI Properties | 10 | Property (Hypothesis) |
| Level 23: Standalone Dry Run (Happy Path) | 5 | Integration |
| Level 24: Standalone Dry Run (Error Detection) | 6 | Integration |
| Level 25: Dependency Validation | 5 | Integration |
| Level 26: Pre-Deployment Validation | 3 | Integration |
| **Total** | **201** | |

### Automated Test Breakdown

| File | Tests | Status |
|------|-------|--------|
| tests/unit/commands/dry_run/test_models.py | 12 | ⬜ Not started |
| tests/unit/commands/dry_run/test_report.py | 12 | ⬜ Not started |
| tests/unit/commands/dry_run/test_manifest_checker.py | 10 | ⬜ Not started |
| tests/unit/commands/dry_run/test_bundle_checker.py | 12 | ⬜ Not started |
| tests/unit/commands/dry_run/test_permission_checker.py | 18 | ⬜ Not started |
| tests/unit/commands/dry_run/test_connectivity_checker.py | 11 | ⬜ Not started |
| tests/unit/commands/dry_run/test_project_checker.py | 4 | ⬜ Not started |
| tests/unit/commands/dry_run/test_quicksight_checker.py | 3 | ⬜ Not started |
| tests/unit/commands/dry_run/test_storage_checker.py | 3 | ⬜ Not started |
| tests/unit/commands/dry_run/test_git_checker.py | 3 | ⬜ Not started |
| tests/unit/commands/dry_run/test_catalog_checker.py | 10 | ⬜ Not started |
| tests/unit/commands/dry_run/test_dependency_checker.py | 24 | ⬜ Not started |
| tests/unit/commands/dry_run/test_workflow_checker.py | 6 | ⬜ Not started |
| tests/unit/commands/dry_run/test_bootstrap_checker.py | 4 | ⬜ Not started |
| tests/unit/commands/dry_run/test_engine.py | 6 | ⬜ Not started |
| tests/unit/commands/dry_run/test_cli_integration.py | 16 | ⬜ Not started |
| tests/unit/commands/dry_run/test_properties.py | 32 | ⬜ Not started |
| **Total unit/property** | **186** | **0 passed, 0 failed, 0 skipped** |

### Integration Test Files

| File | Tests | Location |
|------|-------|----------|
| tests/integration/dry_run/test_dry_run_happy_path.py | 5 | tests/integration/dry_run/ |
| tests/integration/dry_run/test_dry_run_errors.py | 6 | tests/integration/dry_run/ |
| tests/integration/dry_run/test_dry_run_dependencies.py | 5 | tests/integration/dry_run/ |
| tests/integration/dry_run/test_pre_deployment_validation.py | 3 | tests/integration/dry_run/ |
| **Total integration** | **19** | Requires AWS credentials |

### Coverage Targets

| Module | Target Coverage |
|--------|----------------|
| `commands/dry_run/models.py` | **95%+** |
| `commands/dry_run/report.py` | **95%+** |
| `commands/dry_run/engine.py` | **95%+** |
| `commands/dry_run/checkers/*.py` | **95%+** |
| `cli.py` (deploy function changes) | **95%+** |

---

### Requirements Traceability

| Requirement | Covered By |
|-------------|-----------|
| 1.1 Dry-run no mutations | P24, U139 |
| 1.2 Default behavior unchanged | U145, U146 |
| 1.3 CLI option compatibility | P26, U152 |
| 1.4 Event suppression | P27, U142 |
| 1.5 Skip-validation flag | P30, U151 |
| 2.1–2.2 Manifest validation | P3, U25–U26, U28–U29 |
| 2.3 Missing manifest | U27 |
| 2.4 Missing target stage | U29 |
| 2.5 Env var detection | P4, U30–U33 |
| 3.1 Bundle enumeration | P5, U35–U36 |
| 3.2 Bundle resolution | U38, U46 |
| 3.3–3.5 Artifact detection | P6, U39–U42 |
| 3.6 Catalog export validation | P7, U43–U44 |
| 4.1–4.13 Permission verification | P8, U47–U64 |
| 5.1 Project simulation | P10, U76–U78 |
| 5.2 Storage simulation | P11, U83–U85 |
| 5.3 Git simulation | U86–U88 |
| 5.4 Catalog simulation | P12, U89–U98 |
| 5.5 QuickSight simulation | U80–U82 |
| 5.6 Bootstrap listing | P16, U129–U132 |
| 5.7 Phase ordering | P23, U133 |
| 6.1–6.5 Connectivity checks | P9, U65–U75 |
| 7.1–7.3 Report structure | P1, U5–U12 |
| 7.4–7.5 Exit codes | P28, U140–U141 |
| 7.6 Text output | U13–U17, U23 |
| 7.7 JSON output | P2, U18–U20, U24 |
| 8.1–8.4 Catalog validation | P13, P14, U89–U98 |
| 9.1–9.4 Workflow validation | P15, U123–U128 |
| 10.1–10.8 Unit test coverage | All unit tests |
| 11.1–11.9 Integration tests | I1–I19 |
| 12.1–12.5 Lint/format | Separate lint task |
| 13.1–13.3 Glue dependencies | P17, U99–U109 |
| 13.4–13.5 Data source dependencies | P18, U110–U111 |
| 13.6–13.7 Form type dependencies | P19, U112–U114 |
| 13.8–13.9 Asset type dependencies | P20, U115–U117 |
| 13.10–13.11 Form type revisions | P21, U118–U119 |
| 13.12 Managed resource skipping | U114, U117 |
| 13.13 Glue resource type detection | U99–U102 |
| 14.1–14.3 Pre-deployment gate | P29, U145–U147 |
| 14.4–14.6 Validation messages | U148–U150 |
| 14.7 Skip-validation | P30, U151 |
| 14.8 Same engine | P32 |
| 14.9 Event suppression during validation | P31, U153 |
| 14.10 JSON output during validation | U154 |

### Correctness Properties Coverage

| Property | Unit Tests | Property Tests | Integration Tests |
|----------|-----------|----------------|-------------------|
| P1: No-mutation invariant | U139 | P24 | I1 |
| P2: CLI option compatibility | U152 | P26 | — |
| P3: Event suppression | U142 | P27 | — |
| P4: Env var detection | U30–U33 | P4 | — |
| P5: Manifest validation | U25–U29 | P3 | I6, I7 |
| P6: Bundle enumeration | U35–U36 | P5 | — |
| P7: Missing artifact detection | U39–U42 | P6 | I11 |
| P8: Catalog schema validation | U43–U44, U97 | P7 | — |
| P9: Permission set correctness | U47–U64 | P8 | I8 |
| P10: Project simulation | U76–U78 | P10 | — |
| P11: Storage simulation | U83–U85 | P11 | — |
| P12: Catalog resource counting | U95 | P12 | — |
| P13: Phase ordering | U133 | P23 | I2 |
| P14: S3 reachability | U70–U72 | P9 | I9 |
| P15: Report structure | U5–U12 | P1 | — |
| P16: Exit code correctness | U140–U141 | P28 | — |
| P17: JSON round-trip | U18–U20 | P2 | I3 |
| P18: Catalog field validation | U90–U92 | P13 | — |
| P19: Catalog cross-references | U93–U94 | P14 | — |
| P20: Workflow validation | U123–U128 | P15 | — |
| P21: Dry-run idempotence | — | P25 | I5 |
| P22: Bootstrap listing | U129–U132 | P16 | — |
| P23: Glue dependency detection | U99–U109 | P17 | I12, I13 |
| P24: Data source detection | U110–U111 | P18 | I16 |
| P25: Form type detection | U112–U114 | P19 | I14 |
| P26: Asset type detection | U115–U117 | P20 | I15 |
| P27: Form type revision | U118–U119 | P21 | — |
| P28: Dependency caching | U108–U109, U120–U122 | P22 | — |
| P29: Pre-deployment gate | U145–U147 | P29 | I17, I18 |
| P30: Skip-validation bypass | U151 | P30 | I19 |
| P31: Pre-deployment event suppression | U153 | P31 | — |
| P32: Validation engine consistency | — | P32 | — |

---

## Running Tests

All commands from `CICD-for-SageMakerUnifiedStudio-public/` directory.

### Run all dry-run unit tests
```bash
./venv/bin/python -m pytest tests/unit/commands/dry_run/ -v
```

### Run with coverage
```bash
./venv/bin/python -m pytest tests/unit/commands/dry_run/ \
  --cov=smus_cicd.commands.dry_run \
  --cov-report=term-missing -v
```

### Run only property-based tests
```bash
./venv/bin/python -m pytest tests/unit/commands/dry_run/test_properties.py -v
```

### Run only unit tests (no property tests)
```bash
./venv/bin/python -m pytest tests/unit/commands/dry_run/ \
  --ignore=tests/unit/commands/dry_run/test_properties.py -v
```

### Run specific checker tests
```bash
./venv/bin/python -m pytest tests/unit/commands/dry_run/test_dependency_checker.py -v
./venv/bin/python -m pytest tests/unit/commands/dry_run/test_permission_checker.py -v
```

### Run dry-run integration tests
```bash
# Requires valid AWS credentials — source .env first
source .env
./venv/bin/python -m pytest tests/integration/dry_run/ -v
```

### Run full unit test suite (including dry-run)
```bash
./venv/bin/python -m pytest tests/unit/ -v
```

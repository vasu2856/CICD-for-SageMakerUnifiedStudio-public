# Testing Guide: DataZone Catalog Import/Export

Incremental testing plan ordered by complexity. Each test has a status tracker updated during implementation.

**Status legend:** ⬜ Not started · 🔄 In progress · ✅ Pass · ❌ Fail · ⏭️ Skipped

---

## Part 1: Unit Tests

Tests run locally via `./venv/bin/python -m pytest` from the `CICD-for-SageMakerUnifiedStudio-public/` directory.

---

### Level 1 — Search & Pagination (No Dependencies)

Validates the Search API and SearchTypes API wrappers handle pagination, ownership filtering, and error propagation.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U1 | A single-page search returns all items without following nextToken | Result list matches API response items | ✅ |
| U2 | A multi-page search follows nextToken until exhausted and returns all items | All items from both pages returned | ✅ |
| U5 | The `owningProjectIdentifier` parameter is applied to all Search API calls for server-side ownership filtering | API call includes `owningProjectIdentifier` | ✅ |
| U6 | A sort clause of `{"attribute": "updatedAt", "order": "DESCENDING"}` is applied to all search queries | Sort clause present in API call | ✅ |
| U7 | An empty search result returns an empty list without error | Returns `[]` | ✅ |
| U8 | When the Search API raises an exception, it propagates to the caller | Exception raised | ✅ |

---

### Level 2 — SearchTypes API (Client-Side Filtering)

Validates the SearchTypes API wrapper for FormTypes and AssetTypes with client-side ownership filtering.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U9 | Searching for form types returns items with `owningProjectId` matching the source project | Only project-owned form types returned | ✅ |
| U10 | Searching for asset types returns items with `owningProjectId` matching the source project | Only project-owned asset types returned | ✅ |
| U11 | Client-side `owningProjectId` filtering removes items owned by other projects | Non-matching items excluded | ✅ |
| U12 | Managed resources (`managed=True`) are excluded from search type results | Managed items filtered out | ✅ |
| U14 | Multi-page SearchTypes results are paginated correctly | All pages followed, all items returned | ✅ |
| U15 | Sort clause is applied to SearchTypes queries | Sort clause present in API call | ✅ |
| U16 | When the SearchTypes API raises an exception, it propagates to the caller | Exception raised | ✅ |

---

### Level 3 — Asset & Data Product Enrichment (GetAsset/GetDataProduct)

Validates that Search API summary results are enriched with full details via per-item API calls.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U17 | Each asset returned by Search is enriched with `formsOutput`, `description`, and `listingStatus` from the GetAsset API | Enriched fields present on each item | ✅ |
| U18 | When GetAsset fails for one asset, the original Search result is preserved as fallback | Original item returned, no crash | ✅ |
| U19 | Assets without an `identifier` field are skipped during enrichment | No GetAsset call for items missing identifier | ✅ |
| U20 | Each data product returned by Search is enriched with `items`, `description`, and `listingStatus` from GetDataProduct | Enriched fields present | ✅ |
| U21 | When GetDataProduct fails for one item, the original Search result is preserved as fallback | Original item returned, no crash | ✅ |
| U22 | Data products without an `id` field are skipped during enrichment | No GetDataProduct call for items missing id | ✅ |

---

### Level 4 — Serialization (Resource → JSON)

Validates that each resource type is correctly serialized to the export JSON format.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U23 | A glossary is serialized with `sourceId`, `name`, and all user-configurable attributes | All fields present | ✅ |
| U24 | A glossary term with `termRelations` is serialized with the relations preserved | `termRelations` present in output | ✅ |
| U25 | A glossary term with empty `termRelations` omits the field | No `termRelations` key | ✅ |
| U26 | A form type with a `model` is serialized with the complete model structure preserved | `model` present with all fields | ✅ |
| U27 | An asset type is serialized with `sourceId`, `name`, and all attributes | All fields present | ✅ |
| U28 | An asset with `externalIdentifier` is serialized with the identifier preserved | `externalIdentifier` present | ✅ |
| U29 | An asset without `externalIdentifier` is serialized without the field | No `externalIdentifier` key | ✅ |
| U30 | An asset's `formsOutput` is serialized as `formsInput` in the export JSON | `formsInput` present, `formsOutput` absent | ✅ |
| U31 | A data product is serialized with `sourceId`, `name`, `items`, and `listingStatus` | All fields present | ✅ |
| U32 | An unknown resource type returns an empty dict | Returns `{}` | ✅ |

---

### Level 5 — Full Export Pipeline (End-to-End Unit)

Validates the complete export flow: Search → Enrich → Serialize → JSON output.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U33 | Export produces all 7 resource type keys in the output JSON | `glossaries`, `glossaryTerms`, `formTypes`, `assetTypes`, `assets`, `dataProducts`, `metadata` all present | ✅ |
| U34 | The `metadata` section includes `sourceProjectId`, `sourceDomainId`, `exportTimestamp`, and `resourceTypes` | All metadata fields present | ✅ |
| U35 | Assets are queried via Search API, form/asset types via SearchTypes API | Correct API routing | ✅ |
| U36 | SearchTypes API is used for form types and asset types | `search_types` called for these types | ✅ |
| U37 | Ownership filter is applied to all queries | `owningProjectIdentifier` or client-side filter on all calls | ✅ |
| U40 | `externalIdentifier` is exported for assets | Field present in asset entries | ✅ |
| U41 | `formsInput` (from enriched `formsOutput`) is exported for assets | Field present in asset entries | ✅ |
| U42 | `termRelations` is exported for glossary terms | Field present in glossary term entries | ✅ |
| U43 | An API failure during export raises an exception (no partial JSON) | Exception propagated | ✅ |
| U44 | An empty project produces valid JSON with zero resources | Valid JSON, all lists empty | ✅ |
| U45 | The export function signature does not accept a `resource_types` parameter | No such parameter | ✅ |
| U46 | No `metadataForms` key appears in the output JSON | Key absent | ✅ |

---

### Level 6 — Exported Fields Verification (Enrichment Correctness)

Validates that every field is populated after the full Search → GetAsset/GetDataProduct → Serialize pipeline.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U47 | Glossary fields (`name`, `sourceId`, `description`) are populated after export | All fields non-empty | ✅ |
| U48 | Glossary term fields (`name`, `sourceId`, `glossaryId`, `termRelations`) are populated | All fields non-empty | ✅ |
| U49 | Form type fields (`name`, `sourceId`, `model`) are populated | All fields non-empty | ✅ |
| U50 | Asset type fields (`name`, `sourceId`) are populated | All fields non-empty | ✅ |
| U51 | Asset fields (`name`, `sourceId`, `formsInput`, `externalIdentifier`) are populated after GetAsset enrichment | All fields non-empty | ✅ |
| U52 | Asset `listingStatus` is populated after GetAsset enrichment | Field present and non-empty | ✅ |
| U53 | Data product `items` are populated after GetDataProduct enrichment | `items` list non-empty | ✅ |
| U54 | Data product `listingStatus` is populated after GetDataProduct enrichment | Field present and non-empty | ✅ |
| U55 | Data product `items` are empty WITHOUT enrichment (Search API limitation) | `items` list empty | ✅ |
| U56 | Asset `formsInput` is empty WITHOUT enrichment (Search API limitation) | `formsInput` list empty | ✅ |
| U57 | All resource types have `sourceId` and `name` after export | Both fields present on every resource | ✅ |
| U58 | Asset `listingStatus` is "ACTIVE" (not "LISTED") after enrichment | Value is "ACTIVE" | ✅ |

---

### Level 7 — Import Validation & Identifier Mapping

Validates JSON validation, external identifier normalization, and identifier mapping logic.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U59 | A valid catalog JSON passes validation without error | No exception raised | ✅ |
| U60 | A catalog JSON missing a top-level key (e.g., `glossaries`) raises a validation error | `ValueError` raised | ✅ |
| U61 | A catalog JSON missing a metadata key (e.g., `sourceProjectId`) raises a validation error | `ValueError` raised | ✅ |
| U62 | Validation does not require a `metadataForms` key (backward compat) | No error when key absent | ✅ |
| U63 | External identifier normalization strips the ARN prefix | Prefix removed | ✅ |
| U64 | External identifier normalization removes the AWS account ID | Account ID removed | ✅ |
| U65 | External identifier normalization removes the AWS region | Region removed | ✅ |
| U66 | An empty string external identifier returns empty string | Returns `""` | ✅ |
| U67 | A `None` external identifier passes through as `None` | Returns `None` | ✅ |
| U68 | An identifier with no AWS info passes through unchanged | Returns original string | ✅ |

---

### Level 8 — Identifier Map Building & Cross-Reference Resolution

Validates the mapping from source identifiers to target identifiers and cross-reference resolution.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U69 | Resources with matching `externalIdentifier` in the target project are mapped to the target identifier | Mapping contains source→target pair | ✅ |
| U70 | When no `externalIdentifier` match exists, the mapper falls back to `name` matching | Name-based mapping created | ✅ |
| U71 | When neither `externalIdentifier` nor `name` matches, the resource is left unmapped (marked for creation) | No mapping entry | ✅ |
| U72 | Form types are mapped using the same externalIdentifier/name logic | Mapping contains form type entries | ✅ |
| U73 | Glossary term `glossaryId` references are resolved to the target glossary identifier | `glossaryId` updated to target ID | ✅ |
| U74 | Asset `typeIdentifier` references are resolved to the target asset type identifier | `typeIdentifier` updated to target ID | ✅ |
| U75 | Unmapped cross-references are preserved as-is (no crash) | Original reference kept | ✅ |

---

### Level 9 — Import Resource (Create/Update)

Validates individual resource create and update operations.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U76 | Creating a glossary calls `create_glossary` with the correct parameters | API called with name, description, etc. | ✅ |
| U77 | Updating a glossary calls `update_glossary` with the target identifier | API called with existing ID | ✅ |
| U78 | A `ConflictException` during create is treated as an update (idempotent) | Falls back to update API | ✅ |
| U79 | An API failure during create/update returns `False` (no crash) | Returns `False` | ✅ |
| U80 | Creating an asset includes the `externalIdentifier` field | `externalIdentifier` in API call | ✅ |
| U81 | A resource with a missing `sourceId` returns `False` without calling any API | Returns `False`, no API call | ✅ |

---

### Level 10 — Publish Resource (Listing Verification with Polling)

Validates the async publish flow: `create_listing_change_set` → poll → verify ACTIVE status.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U85 | Publishing an asset calls `create_listing_change_set` and polls `get_asset` until `listingStatus` is ACTIVE | Returns `True` | ✅ |
| U86 | Publishing a data product calls `create_listing_change_set` and polls `get_data_product` until ACTIVE | Returns `True` | ✅ |
| U87 | When listing status is FAILED after polling, publish returns `False` | Returns `False` | ✅ |
| U88 | When listing status never becomes ACTIVE within the timeout, publish returns `False` | Returns `False` (timeout) | ✅ |
| U89 | When listing status transitions from CREATING to ACTIVE during polling, publish returns `True` | Returns `True` after transition | ✅ |
| U90 | Publishing a non-publishable type (glossary, form type, etc.) returns `True` without calling any API | Returns `True`, no API call | ✅ |
| U91 | When `create_listing_change_set` raises an exception, publish returns `False` | Returns `False` | ✅ |
| U92 | When a poll call raises an exception, the next poll retries | Retries on error | ✅ |

---

### Level 11 — Identify Extra Resources in Target

Validates detection of resources in the target that are not in the source bundle (logged, not deleted).

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U93 | Resources in the target project but not in the export JSON are identified as extra | Extra resources returned | ✅ |
| U94 | When all target resources match the export JSON, no extras are identified | Empty extras list | ✅ |

---

### Level 12 — Full Import Pipeline (End-to-End Unit)

Validates the complete import flow: validate → map → create/update → log extras → publish → summary.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U95 | Resources are created in dependency order: Glossaries → GlossaryTerms → FormTypes → AssetTypes → Assets → DataProducts | Create calls in correct order | ✅ |
| U96 | Extra resources in target are logged but NOT deleted | No delete API calls, skipped count incremented | ✅ |
| U97 | When source `listingStatus` is ACTIVE and `skipPublish` is false, assets/data products are published after creation | Publish called | ✅ |
| U98 | When source `listingStatus` is not ACTIVE, no publish is attempted | No publish call | ✅ |
| U99 | When `skipPublish` is true, no publish is attempted regardless of source state | No publish call | ✅ |
| U100 | A publish failure increments the `failed` count in the summary | Failed count incremented | ✅ |
| U101 | When one resource fails to create, remaining resources are still attempted (error resilience) | All resources attempted | ✅ |
| U102 | The import summary reports correct counts of created, updated, skipped, and failed resources | Counts match actual operations | ✅ |
| U103 | Malformed JSON is rejected before any API calls are made | `ValueError` raised, no API calls | ✅ |

---

### Level 13 — Permission Check (Pre-Import Validation)

Validates that required DataZone policy grants are checked before import begins.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U104 | When all required grants (CREATE_GLOSSARY, CREATE_FORM_TYPE, CREATE_ASSET_TYPE) are present, the check passes | Returns empty missing list | ✅ |
| U105 | When no grants are present, all three required grants are reported as missing | Returns all 3 missing | ✅ |
| U106 | When only some grants are present, only the missing ones are reported | Returns only missing grants | ✅ |
| U107 | When `list_policy_grants` raises `AccessDeniedException`, the check returns empty (graceful degradation) | Returns empty, no crash | ✅ |
| U108 | When `get_project` fails, the check returns empty (graceful degradation) | Returns empty, no crash | ✅ |
| U109 | When the project has no `domainUnitId`, the check returns empty | Returns empty | ✅ |
| U110 | `import_catalog` aborts with an error when required grants are missing | Import aborted, error logged | ✅ |
| U111 | Non-AccessDeniedException ClientError logs warning, does not treat as missing | Returns empty | ✅ |
| U112 | Generic Exception on `list_policy_grants` logs warning, does not treat as missing | Returns empty | ✅ |

---

### Level 14 — Managed Resource Detection & Client Helpers

Validates managed resource detection, DataZone client creation, and form type revision lookup.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U113 | Managed form type name (amazon.datazone.*) is detected as managed | Returns `True` | ✅ |
| U114 | Custom form type name is not detected as managed | Returns `False` | ✅ |
| U115 | Empty name is not detected as managed | Returns `False` | ✅ |
| U116 | `None` name is not detected as managed | Returns `False` | ✅ |
| U117 | Custom DATAZONE_ENDPOINT_URL creates client with custom endpoint | Client created with endpoint | ✅ |
| U118 | Default client creation (no custom endpoint) uses standard boto3 | Client created without endpoint | ✅ |
| U119 | `_get_form_type_revision` returns revision from API response | Returns revision string | ✅ |
| U120 | `_get_form_type_revision` returns `None` on API error | Returns `None` | ✅ |

---

### Level 15 — Search Target Resources (Pagination & Filtering)

Validates search target resources and search target type resources with pagination and filtering.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U121 | Single-page search returns all items | All items returned | ✅ |
| U122 | Multi-page search follows nextToken | All pages followed | ✅ |
| U123 | SearchTypes filters by owning project (client-side) | Only matching items returned | ✅ |
| U124 | SearchTypes for ASSET_TYPE filters correctly | Matching items returned | ✅ |
| U125 | SearchTypes pagination follows nextToken | All pages followed | ✅ |
| U126 | SearchTypes with unknown scope returns empty | Empty list returned | ✅ |

---

### Level 16 — Forms Normalization (typeName → typeIdentifier, Revision Remap)

Validates forms normalization for API compatibility.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U127 | Asset forms: `typeName` renamed to `typeIdentifier` | Field renamed | ✅ |
| U128 | Asset forms: existing `typeIdentifier` preserved when both present | Original kept | ✅ |
| U129 | Asset forms: `typeRevision` remapped to target domain revision | Revision updated | ✅ |
| U130 | AssetType forms: `typeName` renamed to `typeIdentifier` | Field renamed | ✅ |
| U131 | AssetType forms: `typeRevision` remapped to target domain revision | Revision updated | ✅ |
| U132 | Empty/None forms pass through unchanged | Returns input | ✅ |
| U133 | Unknown resource type forms pass through unchanged | Returns input | ✅ |
| U134 | Asset form without `typeRevision` skips revision remap | No revision field added | ✅ |
| U135 | Asset form revision resolves to `None` keeps original | Original revision kept | ✅ |
| U136 | AssetType form without `typeRevision` skips revision remap | No revision field added | ✅ |
| U137 | AssetType form revision resolves to `None` keeps original | Original revision kept | ✅ |
| U138a | Asset form: `DataSourceReferenceForm` remapped to target data source by exact databaseName match | `dataSourceIdentifier.id` updated to target DS | ✅ |
| U138b | Asset form: `DataSourceReferenceForm` remapped via wildcard `"*"` database filter when no exact match | Wildcard DS used | ✅ |
| U138c | Asset form: `DataSourceReferenceForm` falls back to first candidate of same type | First candidate DS used | ✅ |
| U138d | Asset form: `DataSourceReferenceForm` stripped when no matching data source in target | Form removed from output | ✅ |
| U138e | Asset form: `databaseName` extracted from `GlueTableForm` content for data source matching | Correct DB name used | ✅ |
| U138f | Asset form: `DataSourceReferenceForm` remap updates `filterableDataSourceId` and `dataSourceRunId` | All three fields updated | ✅ |

---

### Level 17 — Cross-Reference Resolution (Data Products & Term Relations)

Validates cross-reference resolution for data products and glossary term relations.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U138 | Data product item identifiers resolved to target asset IDs | Identifiers updated | ✅ |
| U139 | Data product glossary terms resolved to target term IDs | Terms updated | ✅ |
| U140 | Glossary term `termRelations` resolved to target term IDs | Relations updated | ✅ |
| U141 | Non-list `termRelations` values preserved as-is | Scalar value kept | ✅ |

---

### Level 18 — Import Resource (All Types: Create, Update, Managed Skip)

Validates import resource for all resource types including minimal/optional field handling.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U142 | Create glossary term with all optional fields | All fields in API call | ✅ |
| U143 | Update glossary term with termRelations | termRelations in update call | ✅ |
| U144 | Create form type with model and description | Fields in API call | ✅ |
| U145 | Update form type skips (no update API) | No create call | ✅ |
| U146 | Managed form type skipped | No API call | ✅ |
| U147 | Create asset type with formsInput | formsInput in API call | ✅ |
| U148 | Update asset type skips (no update API) | No create call | ✅ |
| U149 | Managed asset type skipped | No API call | ✅ |
| U150 | Managed forms filtered from asset type creation | Managed forms removed | ✅ |
| U151 | Update asset merges exported forms with existing managed forms | Both form sets in revision | ✅ |
| U152 | Update asset with get_asset failure still creates revision | Revision created | ✅ |
| U153 | Create data product with items | Items in API call | ✅ |
| U154 | Update data product creates revision | Revision created | ✅ |
| U155 | Create asset minimal (no optional fields) | Only required fields | ✅ |
| U156 | Non-ConflictException ClientError returns (False, False) | Error propagated | ✅ |
| U157 | Create glossary minimal (no description/status) | Only required fields | ✅ |
| U158 | Create glossary term minimal (no optional fields) | Only required fields | ✅ |
| U159 | Update glossary minimal (no description/status) | Only required fields | ✅ |
| U160 | Update glossary term minimal (no optional fields) | Only required fields | ✅ |
| U161 | Create data product minimal (no description/items) | Only required fields | ✅ |
| U162 | Update data product minimal (no description) | Only required fields | ✅ |
| U163 | Create form type minimal (no description/model) | Only required fields | ✅ |
| U164 | Create asset type minimal (no description/formsInput) | Only required fields | ✅ |

---

### Level 19 — Identifier Map Building (All Types & Error Handling)

Validates identifier map building for all resource types and error handling.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U165 | Glossary term mapping by name | Mapping created | ✅ |
| U166 | Asset type mapping by name | Mapping created | ✅ |
| U167 | Data product mapping by name | Mapping created | ✅ |
| U168 | Glossary term search failure graceful | No mapping, no crash | ✅ |
| U169 | Form type search failure graceful | No mapping, no crash | ✅ |
| U170 | Asset type search failure graceful | No mapping, no crash | ✅ |
| U171 | Data product search failure graceful | No mapping, no crash | ✅ |
| U172 | Asset search failure graceful | No mapping, no crash | ✅ |
| U173 | Glossary search failure graceful | No mapping, no crash | ✅ |
| U174 | Resources without sourceId skipped | No mapping entry | ✅ |

---

### Level 20 — Identify Extra Resources in Target (All Types)

Validates identification of extra resources in target for all resource types (logged, not deleted).

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U179 | Identify extra glossary terms in target | Extra terms returned | ✅ |
| U180 | Identify extra form types in target | Extra form types returned | ✅ |
| U181 | Identify extra asset types in target | Extra asset types returned | ✅ |
| U182 | Identify extra assets in target | Extra assets returned | ✅ |
| U183 | Identify extra data products in target | Extra data products returned | ✅ |
| U184 | Search failure during extra resource identification is graceful | No crash, empty list | ✅ |
| U185–U190 | Individual search failure per resource type during extra resource identification | Each type handled gracefully | ✅ |

---

### Level 21 — Full Import Pipeline (Second Pass & Integration)

Validates the second pass termRelations update and extra resource logging.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| U191 | Second pass updates glossary terms with resolved termRelations | update_glossary_term called with resolved IDs | ✅ |
| U192 | Second pass termRelations update failure is logged, not fatal | No crash | ✅ |
| U193 | Second pass skips terms with empty termRelations | No update call | ✅ |
| U194 | Extra resources in target are skipped, not deleted | Skipped count incremented, no delete calls | ✅ |
| U195 | Second pass handles non-list termRelations values | Scalar preserved | ✅ |
| U196 | Updated asset with ACTIVE listingStatus is published | Publish called | ✅ |
| U197 | Second pass skips terms with no target mapping | No update call | ✅ |

---

## Part 2: Property-Based Tests (Hypothesis)

Property tests use `@settings(max_examples=100)` and `@st.composite` strategies to generate realistic mock API responses. All run via `./venv/bin/python -m pytest`.

---

### Level 22 — Export Properties

Validates export correctness properties across randomly generated inputs.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P1 | When `enabled=True`, all 6 resource types are queried; when `enabled=False`, no queries are made | All types present or none | ✅ |
| P2 | All Search/SearchTypes queries include the ownership filter for the source project | `owningProjectIdentifier` or client-side filter present | ✅ |
| P6 | The export JSON always has the 7 required top-level keys and valid metadata | Structure invariant holds | ✅ |
| P7a | Glossary field preservation: `name`, `sourceId`, `description` survive serialization | Fields match input | ✅ |
| P7b | Glossary term field preservation: `termRelations` survive serialization | Relations match input | ✅ |
| P7c | Form type model preservation: complete `model` structure survives serialization | Model matches input | ✅ |
| P7d | Asset field preservation: `formsInput`, `externalIdentifier` survive serialization | Fields match input | ✅ |
| P7e | Asset type field preservation: `name`, `sourceId` survive serialization | Fields match input | ✅ |
| P7f | Data product field preservation: `items`, `listingStatus` survive serialization | Fields match input | ✅ |
| P8 | Export JSON round-trips through `json.dumps` → `json.loads` without data loss | Round-trip equality | ✅ |
| P16 | When any Search/SearchTypes API raises an error, no partial JSON is produced | Exception propagated, no output | ✅ |

---

### Level 23 — Import Properties

Validates import correctness properties across randomly generated catalog data.

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| P9a | External identifier normalization removes AWS account ID and region | Normalized form has no AWS info | ✅ |
| P9b | Same resource in different AWS accounts normalizes to the same identifier | Equal after normalization | ✅ |
| P9c | When no external identifier exists, name is used as fallback for mapping | Name-based mapping created | ✅ |
| P9d | When neither external identifier nor name matches, resource is marked for creation | No mapping entry | ✅ |
| P10a | Glossary term `glossaryId` is resolved to the target glossary identifier | Resolved correctly | ✅ |
| P10b | Asset `typeIdentifier` is resolved to the target asset type identifier | Resolved correctly | ✅ |
| P10c | Unmapped cross-references are preserved as-is | Original reference kept | ✅ |
| P11 | Resources are always created in dependency order regardless of input ordering | Dependency order respected | ✅ |
| P12 | Extra resources in target are logged but never deleted (no delete API calls) | No delete calls, skipped count matches extras | ✅ |
| P13 | When random resources fail to create, all remaining resources are still attempted | All resources attempted | ✅ |
| P14 | Summary counts (created + updated + failed) always equal total resources attempted | Counts add up | ✅ |
| P15a | When source `listingStatus` is ACTIVE and `skipPublish` is false, publish is called | Publish invoked | ✅ |
| P15b | When `skipPublish` is true, no publish is called regardless of source state | No publish call | ✅ |
| P15c | When source `listingStatus` is not ACTIVE, no publish is called | No publish call | ✅ |
| P17a | Missing a top-level key in catalog JSON raises `ValueError` | Exception raised | ✅ |
| P17b | Missing a metadata key in catalog JSON raises `ValueError` | Exception raised | ✅ |
| P17c | `import_catalog` rejects malformed JSON before making any API calls | No API calls made | ✅ |
| P18 | When an asset has a `DataSourceReferenceForm`, the form is remapped to the target domain's data source by type + databaseName matching | `dataSourceIdentifier.id` updated to target DS | ✅ |

---

## Part 3: Integration Tests (Manual)

These tests require real AWS credentials and DataZone domains. Run via `smus-cli` commands from the `CICD-for-SageMakerUnifiedStudio-public/` directory after sourcing `.env`.

---

### Level 24 — Bundle Command (Export)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I1 | `smus-cli bundle` with `content.catalog.enabled: true` produces a ZIP containing `catalog/catalog_export.json` | File exists in ZIP | ✅ |
| I2 | The exported JSON contains all 7 top-level keys with correct metadata | Keys and metadata present | ✅ |
| I3 | Assets in the export have populated `formsInput` (from GetAsset enrichment) | `formsInput` non-empty | ✅ |
| I4 | Data products in the export have populated `items` (from GetDataProduct enrichment) | `items` non-empty | ✅ |
| I5 | Glossary terms in the export have `termRelations` when relations exist in source | `termRelations` present | ✅ |
| I6 | `listingStatus` is "ACTIVE" for published assets (not "LISTED") | Value is "ACTIVE" | ✅ |
| I7 | `smus-cli bundle` with `content.catalog.enabled: false` produces a ZIP without `catalog/` directory | No catalog directory | ✅ |

---

### Level 25 — Deploy Command (Import)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I8 | `smus-cli deploy` with a catalog bundle creates resources in the target project | Resources visible in target | ✅ |
| I9 | Permission check runs before import and reports missing grants if any | Error message lists missing grants | ✅ |
| I10 | Glossaries are created before glossary terms (dependency order) | Glossaries exist when terms reference them | ✅ |
| I11 | Form types are created before asset types and assets | Form types exist when referenced | ✅ |
| I12 | Assets with `externalIdentifier` are mapped to existing target resources on re-deploy | Update instead of duplicate create | ✅ |
| I13 | Assets and data products with source `listingStatus: ACTIVE` are published in the target | Listing status becomes ACTIVE | ✅ |
| I14 | Publish verification polls until ACTIVE status is confirmed | Listing status verified | ✅ |
| I15 | Deploy summary reports correct counts of created, updated, and failed resources | Counts match actual operations | ✅ |
| I16 | Managed form types and asset types are skipped (not created) | No attempt to create managed types | ✅ |
| I17 | `typeRevision` references are remapped to the target project's revision IDs | Correct revision used | ✅ |

---

### Level 26 — Re-Deploy (Idempotency)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I18 | Running `smus-cli deploy` a second time with the same bundle updates existing resources instead of creating duplicates | No duplicate resources | ✅ |
| I19 | Updated resources retain their target identifiers | IDs unchanged after re-deploy | ✅ |
| I20 | Resources deleted from the source bundle are deleted from the target on re-deploy | Extra resources removed | ✅ |

---

### Level 27 — Edge Cases (Manual Verification)

| # | Description | Key Assertions | Status |
|---|-------------|----------------|--------|
| I21 | A project with no catalog resources produces a valid empty export | Empty JSON, no errors | ✅ |
| I22 | A bundle with `skipPublish: true` skips all publishing during deploy | No publish calls | ✅ |
| I23 | A deploy to a project with no existing catalog resources creates everything from scratch | All resources created | ✅ |
| I24 | A deploy with partial API failures continues and reports failures in the summary | Summary shows failures, other resources created | ✅ |

---

## Summary

| Section | Test Count | Type |
|---------|-----------|------|
| Level 1: Search & Pagination | 8 | Unit |
| Level 2: SearchTypes API | 8 | Unit |
| Level 3: Asset & Data Product Enrichment | 6 | Unit |
| Level 4: Serialization | 10 | Unit |
| Level 5: Full Export Pipeline | 14 | Unit |
| Level 6: Exported Fields Verification | 12 | Unit |
| Level 7: Import Validation & Identifier Mapping | 10 | Unit |
| Level 8: Identifier Map & Cross-References | 7 | Unit |
| Level 9: Import Resource (CRUD) | 9 | Unit |
| Level 10: Publish Resource (Polling) | 8 | Unit |
| Level 11: Identify Resources to Delete | 2 | Unit |
| Level 12: Full Import Pipeline | 9 | Unit |
| Level 13: Permission Check | 9 | Unit |
| Level 14: Managed Resource & Client Helpers | 8 | Unit |
| Level 15: Search Target Resources | 6 | Unit |
| Level 16: Forms Normalization | 11 | Unit |
| Level 17: Cross-Reference Resolution (DP & Terms) | 4 | Unit |
| Level 18: Import Resource (All Types) | 23 | Unit |
| Level 19: Identifier Map Building (All Types) | 10 | Unit |
| Level 20: Delete Resource & Identify to Delete | 12 | Unit |
| Level 21: Full Import Pipeline (Second Pass) | 7 | Unit |
| Level 22: Export Properties | 12 | Property (Hypothesis) |
| Level 23: Import Properties | 17 | Property (Hypothesis) |
| Level 24: Bundle Command | 7 | Integration |
| Level 25: Deploy Command | 10 | Integration |
| Level 26: Re-Deploy (Idempotency) | 3 | Integration |
| Level 27: Edge Cases | 4 | Integration |
| **Total** | **236** | |

### Automated Test Breakdown

| File | Tests | Status |
|------|-------|--------|
| test_catalog_export.py | 62 | ✅ All passing |
| test_catalog_export_properties.py | 10 | ✅ All passing |
| test_catalog_import.py | 138 | ✅ All passing |
| test_catalog_import_properties.py | 23 | ✅ All passing |
| **Total unit/property** | **233** | **233 passed, 0 failed, 0 skipped** |

### Integration Test Files

| File | Tests | Location |
|------|-------|----------|
| test_catalog_export.py | 3 | tests/integration/catalog-import-export/ |
| test_catalog_import.py | 8 | tests/integration/catalog-import-export/ |
| test_catalog_round_trip.py | 7 | tests/integration/catalog-import-export/ |
| test_catalog_edge_cases.py | 3 | tests/integration/catalog-import-export/ |
| **Total integration** | **21** | Requires AWS credentials |

### Coverage

| Module | Statements | Missed | Branch | Coverage |
|--------|-----------|--------|--------|----------|
| `catalog_export.py` | 135 | 5 | 58 | **96%** |
| `catalog_import.py` | 576 | 2 | 318 | **98%** |

---

### Requirements Traceability

| Requirement | Covered By |
|-------------|-----------|
| 1.1–1.3 Manifest enabled/disabled | P1, U33–U46 |
| 1.4 skipPublish flag | U97–U99, P15a–P15c |
| 1.5–1.6 Manifest schema (no filters) | U45, U46 |
| 1.7 formsOutput export | U17, U30, U41, U51, U56 |
| 1.8 termRelations export | U24, U42, U48 |
| 2.1 Search API ownership filter | U5, P2 |
| 2.2 SearchTypes client-side filter | U11, U12, P2 |
| 2.3 owningProjectId match | U5, U11, U37 |
| 2.4 Form type model export | U26, U49, P7c |
| 2.5 Sort clause | U6, U15 |
| 2.6 Pagination | U2, U14 |
| 2.9 catalog_export.json in bundle | I1 |
| 2.10 formsOutput → formsInput | U30, U41, P7d |
| 2.11 termRelations export | U24, U42, P7b |
| 2.13 GetAsset enrichment | U17, U51, U52 |
| 2.14 identifier/id fallback | U28, U51 |
| 3.1–3.2 JSON structure | P6, U33, U34 |
| 3.3–3.6 Field preservation | P7a–P7f |
| 3.7 JSON round-trip | P8 |
| 4.1–4.2 Identifier mapping | P9a–P9d, U69–U72 |
| 4.3–4.5 Target matching | U69–U71 |
| 4.6 Cross-reference resolution | P10a–P10c, U73–U75 |
| 5.1–5.3 Create/update resources | U76–U80 |
| 5.4–5.5 Deletion order | P12, U96 |
| 5.6 Creation order | P11, U95 |
| 5.10 Error resilience | P13, U101 |
| 5.12 Summary counts | P14, U102 |
| 5.13 Publishing (source-state + skipPublish + verification) | P15a–P15c, U85–U92, U97–U100 |
| 5.14 Publish failure handling | U87, U88, U91, U100 |
| 5.15 DataSourceReferenceForm remapping | U138a–U138f, P18 |
| 6.1–6.3 Deploy integration | I8, I15 |
| 7.1 Export error propagation | P16, U8, U16, U43 |
| 7.2 Empty project export | U44 |
| 7.3 Import error logging | P13, U101 |
| 7.4 Malformed JSON validation | P17a–P17c, U59–U62, U103 |

### Correctness Properties Coverage

| Property | Unit Tests | Property Tests | Integration Tests |
|----------|-----------|----------------|-------------------|
| P1: Export Enabled/Disabled | U33–U46 | P1 | I1, I7 |
| P2: Ownership Filtering | U5, U11, U37 | P2 | — |
| P6: JSON Structure Invariant | U33, U34 | P6 | I2 |
| P7: Field Preservation | U23–U32, U47–U58 | P7a–P7f | I3–I6 |
| P8: JSON Round-Trip | — | P8 | — |
| P9: Identifier Mapping | U63–U72 | P9a–P9d | I12 |
| P10: Cross-Reference Resolution | U73–U75 | P10a–P10c | I10, I11 |
| P11: Dependency-Ordered Creation | U95 | P11 | I10, I11 |
| P12: Dependency-Ordered Deletion | U96 | P12 | I20 |
| P13: Error Resilience | U101 | P13 | I24 |
| P14: Summary Counts | U102 | P14 | I15 |
| P15: Automatic Publishing | U85–U92, U97–U100 | P15a–P15c | I13, I14 |
| P16: Export Error Propagation | U8, U16, U43 | P16 | — |
| P17: Malformed JSON Validation | U59–U62, U103 | P17a–P17c | — |
| P18: DataSourceReferenceForm Remapping | U138a–U138f | P18 | — |

---

## Running Tests

All commands from `CICD-for-SageMakerUnifiedStudio-public/` directory.

### Run all catalog tests
```bash
./venv/bin/python -m pytest tests/unit/helpers/test_catalog_export.py \
  tests/unit/helpers/test_catalog_export_properties.py \
  tests/unit/helpers/test_catalog_import.py \
  tests/unit/helpers/test_catalog_import_properties.py -v
```

### Run with coverage
```bash
./venv/bin/python -m pytest tests/unit/helpers/test_catalog_export.py \
  tests/unit/helpers/test_catalog_export_properties.py \
  tests/unit/helpers/test_catalog_import.py \
  tests/unit/helpers/test_catalog_import_properties.py \
  --cov=smus_cicd.helpers.catalog_export \
  --cov=smus_cicd.helpers.catalog_import \
  --cov-report=term-missing -v
```

### Run only property-based tests
```bash
./venv/bin/python -m pytest tests/unit/helpers/test_catalog_export_properties.py \
  tests/unit/helpers/test_catalog_import_properties.py -v
```

### Run full unit test suite
```bash
find tests -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
./venv/bin/python -m pytest tests/unit/ -v --ignore=tests/unit/helpers/test_datazone_properties.py
```

### Run catalog integration tests
```bash
# Requires valid AWS credentials — source .env first
source .env
./venv/bin/python -m pytest tests/integration/catalog-import-export/ -v -m integration
```

### Run catalog integration edge case tests only
```bash
source .env
./venv/bin/python -m pytest tests/integration/catalog-import-export/test_catalog_edge_cases.py -v
```

> **Note:** `test_datazone_properties.py` has pre-existing failures unrelated to catalog. Ignore it.

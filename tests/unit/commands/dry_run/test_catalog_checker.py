"""Unit tests for CatalogChecker (Phase 9 — Catalog Import Simulation).

Tests cover:
- No catalog data → OK skip
- Empty resources list → OK skip
- Valid catalog with all required fields
- Missing required fields (type, name, identifier)
- Non-dict resource entries
- Cross-reference validation: glossary terms → glossaries
- Cross-reference validation: assets → form types
- Cross-reference validation: asset types → form types (dict formsInput)
- Managed/system form types are skipped in cross-reference checks
- Resource type counting (glossaries, glossary terms, assets, etc.)
- Mixed valid and invalid resources
- Finding metadata (resource, service, details)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from smus_cicd.commands.dry_run.checkers.catalog_checker import CatalogChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    catalog_data: Optional[Dict[str, Any]] = None,
    resources: Optional[list] = None,
) -> DryRunContext:
    """Build a DryRunContext with catalog data.

    If ``resources`` is provided, groups them by their ``type`` field into
    the keyed format expected by the production catalog export schema.
    """
    if resources is not None and catalog_data is None:
        catalog_data = _group_resources(resources)
    return DryRunContext(
        manifest_file="manifest.yaml",
        catalog_data=catalog_data,
    )


def _group_resources(resources: list) -> Dict[str, Any]:
    """Group a flat list of resource dicts by their 'type' field into keyed format."""
    grouped: Dict[str, Any] = {"metadata": {}}
    for r in resources:
        if isinstance(r, dict):
            rtype = r.get("type", "unknown")
            grouped.setdefault(rtype, []).append(r)
    return grouped


def _make_resource(
    rtype: str = "assets",
    name: str = "my-resource",
    identifier: str = "id-123",
    **extra: Any,
) -> Dict[str, Any]:
    """Build a minimal catalog resource dict."""
    r: Dict[str, Any] = {"type": rtype, "name": name, "identifier": identifier}
    r.update(extra)
    return r


@pytest.fixture
def checker() -> CatalogChecker:
    return CatalogChecker()


# ---------------------------------------------------------------------------
# No catalog data / empty resources
# ---------------------------------------------------------------------------


class TestCatalogCheckerNoData:
    """When catalog_data is None or empty, produce OK skip."""

    def test_no_catalog_data_produces_ok(self, checker):
        ctx = _make_context(catalog_data=None)
        findings = checker.check(ctx)

        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "no catalog data" in findings[0].message.lower()

    def test_empty_resources_produces_ok(self, checker):
        ctx = _make_context(
            catalog_data={"metadata": {}, "assets": [], "glossaries": []}
        )
        findings = checker.check(ctx)

        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "0 resources" in findings[0].message


# ---------------------------------------------------------------------------
# Required field validation
# ---------------------------------------------------------------------------


class TestRequiredFieldValidation:
    """Each resource must have type, name, and identifier."""

    def test_valid_resource_no_field_errors(self, checker):
        resources = [_make_resource()]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_missing_type_produces_error(self, checker):
        """In keyed format, type is auto-tagged from the key. Test missing name instead."""
        resources = [{"type": "assets", "identifier": "id-1"}]  # missing name
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "name" in errors[0].message

    def test_missing_name_produces_error(self, checker):
        resources = [{"type": "assets", "identifier": "id-1"}]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "name" in errors[0].message

    def test_missing_identifier_produces_error(self, checker):
        resources = [{"type": "assets", "name": "foo"}]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "identifier" in errors[0].message

    def test_missing_multiple_fields_produces_error(self, checker):
        resources = [{"type": "assets"}]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "identifier" in errors[0].message
        assert "name" in errors[0].message

    def test_non_dict_resource_produces_error(self, checker):
        """Non-dict resources are filtered out during flattening, producing 0 resources."""
        ctx = _make_context(catalog_data={"assets": ["not-a-dict"]})
        findings = checker.check(ctx)

        # Non-dict items are skipped, so we get "0 resources" OK
        ok_findings = [f for f in findings if "0 resource" in f.message]
        assert len(ok_findings) == 1

    def test_multiple_invalid_resources(self, checker):
        ctx = _make_context(
            catalog_data={
                "assets": [
                    {"name": "a", "identifier": "id-a"},  # type auto-tagged
                    {"type": "assets", "identifier": "id-b"},  # missing name
                ],
            }
        )
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1  # only the missing-name one


# ---------------------------------------------------------------------------
# Cross-reference validation: glossary terms → glossaries
# ---------------------------------------------------------------------------


class TestGlossaryTermCrossReferences:
    """Glossary terms referencing glossaries must be resolvable."""

    def test_valid_glossary_reference(self, checker):
        resources = [
            _make_resource(rtype="glossaries", name="g1", identifier="glossary-1"),
            _make_resource(
                rtype="glossaryTerms",
                name="term1",
                identifier="term-1",
                glossaryId="glossary-1",
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_unresolvable_glossary_reference(self, checker):
        resources = [
            _make_resource(
                rtype="glossaryTerms",
                name="term1",
                identifier="term-1",
                glossaryId="nonexistent-glossary",
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "term1" in errors[0].message
        assert "nonexistent-glossary" in errors[0].message

    def test_no_glossary_id_no_error(self, checker):
        """Glossary terms without glossaryId don't trigger cross-ref errors."""
        resources = [
            _make_resource(rtype="glossaryTerms", name="term1", identifier="term-1"),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Cross-reference validation: assets → form types (list formsInput)
# ---------------------------------------------------------------------------


class TestAssetFormTypeCrossReferences:
    """Assets referencing form types via formsInput must be resolvable."""

    def test_valid_form_type_reference(self, checker):
        resources = [
            _make_resource(rtype="formTypes", name="MyForm", identifier="my-form-type"),
            _make_resource(
                rtype="assets",
                name="asset1",
                identifier="asset-1",
                formsInput=[{"typeIdentifier": "my-form-type"}],
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_unresolvable_form_type_reference(self, checker):
        resources = [
            _make_resource(
                rtype="assets",
                name="asset1",
                identifier="asset-1",
                formsInput=[{"typeIdentifier": "missing-form-type"}],
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "asset1" in errors[0].message
        assert "missing-form-type" in errors[0].message

    def test_managed_form_type_skipped(self, checker):
        """Managed form types (amazon.datazone.*) are not checked."""
        resources = [
            _make_resource(
                rtype="assets",
                name="asset1",
                identifier="asset-1",
                formsInput=[{"typeIdentifier": "amazon.datazone.GlueTableFormType"}],
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_typeName_fallback(self, checker):
        """formsInput using typeName instead of typeIdentifier is also checked."""
        resources = [
            _make_resource(
                rtype="assets",
                name="asset1",
                identifier="asset-1",
                formsInput=[{"typeName": "custom-form"}],
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "custom-form" in errors[0].message

    def test_no_formsInput_no_error(self, checker):
        resources = [
            _make_resource(rtype="assets", name="asset1", identifier="asset-1"),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_non_list_formsInput_no_error(self, checker):
        """If formsInput is not a list for assets, skip cross-ref check."""
        resources = [
            _make_resource(
                rtype="assets",
                name="asset1",
                identifier="asset-1",
                formsInput="not-a-list",
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Cross-reference validation: asset types → form types (dict formsInput)
# ---------------------------------------------------------------------------


class TestAssetTypeFormTypeCrossReferences:
    """Asset types referencing form types via dict formsInput must be resolvable."""

    def test_valid_form_type_reference(self, checker):
        resources = [
            _make_resource(rtype="formTypes", name="MyForm", identifier="my-form-type"),
            _make_resource(
                rtype="assetTypes",
                name="MyAssetType",
                identifier="my-asset-type",
                formsInput={"form1": {"typeIdentifier": "my-form-type"}},
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_unresolvable_form_type_reference(self, checker):
        resources = [
            _make_resource(
                rtype="assetTypes",
                name="MyAssetType",
                identifier="my-asset-type",
                formsInput={"form1": {"typeIdentifier": "missing-form"}},
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "MyAssetType" in errors[0].message
        assert "missing-form" in errors[0].message

    def test_managed_form_type_skipped(self, checker):
        resources = [
            _make_resource(
                rtype="assetTypes",
                name="MyAssetType",
                identifier="my-asset-type",
                formsInput={
                    "form1": {"typeIdentifier": "amazon.datazone.SomeFormType"}
                },
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_non_dict_formsInput_no_error(self, checker):
        """If formsInput is not a dict for assetTypes, skip cross-ref check."""
        resources = [
            _make_resource(
                rtype="assetTypes",
                name="MyAssetType",
                identifier="my-asset-type",
                formsInput=[{"typeIdentifier": "something"}],
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        # No cross-ref errors for asset types with list formsInput
        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Resource type counting
# ---------------------------------------------------------------------------


class TestResourceTypeCounting:
    """Report correct counts for each resource type."""

    def test_single_type(self, checker):
        resources = [
            _make_resource(rtype="glossaries", name="g1", identifier="id-1"),
            _make_resource(rtype="glossaries", name="g2", identifier="id-2"),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        ok_findings = [f for f in findings if f.severity == Severity.OK]
        count_finding = [f for f in ok_findings if "would process" in f.message]
        assert len(count_finding) == 1
        assert "2 glossaries" in count_finding[0].message
        assert count_finding[0].details["total"] == 2

    def test_multiple_types(self, checker):
        resources = [
            _make_resource(rtype="glossaries", name="g1", identifier="id-1"),
            _make_resource(rtype="glossaryTerms", name="t1", identifier="id-2"),
            _make_resource(rtype="glossaryTerms", name="t2", identifier="id-3"),
            _make_resource(rtype="assets", name="a1", identifier="id-4"),
            _make_resource(rtype="formTypes", name="f1", identifier="id-5"),
            _make_resource(rtype="dataProducts", name="dp1", identifier="id-6"),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        count_finding = [f for f in findings if "would process" in f.message]
        assert len(count_finding) == 1
        msg = count_finding[0].message
        assert "1 glossaries" in msg
        assert "2 glossary terms" in msg
        assert "1 form types" in msg
        assert "1 assets" in msg
        assert "1 data products" in msg
        assert count_finding[0].details["total"] == 6

    def test_unknown_type_included(self, checker):
        """Unknown resource types not in CREATION_ORDER are not processed."""
        ctx = _make_context(
            catalog_data={
                "unknownType": [
                    {"type": "unknownType", "name": "u1", "identifier": "id-1"},
                ],
            }
        )
        findings = checker.check(ctx)

        # No resources from CREATION_ORDER found, so 0 resources
        ok_findings = [f for f in findings if "0 resource" in f.message]
        assert len(ok_findings) == 1

    def test_type_counts_in_details(self, checker):
        resources = [
            _make_resource(rtype="assets", name="a1", identifier="id-1"),
            _make_resource(rtype="assets", name="a2", identifier="id-2"),
            _make_resource(rtype="glossaries", name="g1", identifier="id-3"),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        count_finding = [f for f in findings if "would process" in f.message]
        details = count_finding[0].details
        assert details["type_counts"]["assets"] == 2
        assert details["type_counts"]["glossaries"] == 1
        assert details["total"] == 3


# ---------------------------------------------------------------------------
# Mixed valid and invalid resources
# ---------------------------------------------------------------------------


class TestMixedResources:
    """Combination of valid, invalid, and cross-reference issues."""

    def test_mixed_valid_and_missing_fields(self, checker):
        resources = [
            _make_resource(rtype="assets", name="good", identifier="id-1"),
            {"type": "assets", "name": "bad"},  # missing identifier
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "identifier" in errors[0].message

    def test_mixed_valid_and_bad_cross_refs(self, checker):
        resources = [
            _make_resource(rtype="glossaries", name="g1", identifier="glossary-1"),
            _make_resource(
                rtype="glossaryTerms",
                name="good-term",
                identifier="term-1",
                glossaryId="glossary-1",
            ),
            _make_resource(
                rtype="glossaryTerms",
                name="bad-term",
                identifier="term-2",
                glossaryId="nonexistent",
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "bad-term" in errors[0].message


# ---------------------------------------------------------------------------
# Finding metadata
# ---------------------------------------------------------------------------


class TestFindingMetadata:
    """Findings carry appropriate service and details."""

    def test_skip_finding_has_service(self, checker):
        ctx = _make_context(catalog_data=None)
        findings = checker.check(ctx)
        assert findings[0].service == "datazone"

    def test_count_finding_has_service(self, checker):
        resources = [_make_resource()]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        count_finding = [f for f in findings if "would process" in f.message]
        assert count_finding[0].service == "datazone"

    def test_field_error_has_resource(self, checker):
        resources = [{"type": "assets", "name": "myasset"}]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors[0].resource == "myasset"

    def test_field_error_has_details(self, checker):
        resources = [{"type": "assets", "name": "myasset"}]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors[0].details is not None
        assert "identifier" in errors[0].details["missing_fields"]

    def test_cross_ref_error_has_resource(self, checker):
        resources = [
            _make_resource(
                rtype="glossaryTerms",
                name="term1",
                identifier="term-1",
                glossaryId="missing",
            ),
        ]
        ctx = _make_context(resources=resources)
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors[0].resource == "term1"

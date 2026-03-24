"""Catalog import simulation checker (Phase 9).

Validates catalog export data from ``context.catalog_data`` (populated by
BundleChecker). Checks required fields (``type``, ``name``, ``identifier``)
on each resource entry, verifies cross-references between catalog resources
are resolvable, and reports count of each resource type.

Reuses validation patterns from ``helpers/catalog_import.py``.

Requirements: 5.4, 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, List, Set

from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity
from smus_cicd.helpers.catalog_import import (
    CREATION_ORDER,
    CROSS_REFERENCE_FIELDS,
    RESOURCE_TYPE_DISPLAY_NAMES,
    _is_managed_resource,
    get_form_type_ref,
)

logger = logging.getLogger(__name__)

# Required fields on every catalog resource entry
_REQUIRED_RESOURCE_FIELDS = {"type", "name", "identifier"}


class CatalogChecker:
    """Validates catalog export data and reports planned catalog import actions."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        if context.catalog_data is None:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No catalog data to validate; skipping.",
                    service="datazone",
                )
            )
            return findings

        catalog_data = context.catalog_data

        # Collect all resources from the real catalog format (keyed by type)
        # Also support legacy flat "resources" list for backward compat
        resources: list = catalog_data.get("resources", [])
        if not resources:
            # Real format: flatten all resource-type lists, tagging each
            # with its type key so downstream logic can identify them
            for key in CREATION_ORDER:
                for item in catalog_data.get(key, []):
                    if isinstance(item, dict):
                        tagged = dict(item)
                        tagged.setdefault("type", key)
                        # Map sourceId → identifier for uniform access
                        if "identifier" not in tagged and "sourceId" in tagged:
                            tagged["identifier"] = tagged["sourceId"]
                        resources.append(tagged)

        if not resources:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="Catalog export contains 0 resources; nothing to import.",
                    service="datazone",
                )
            )
            return findings

        # 1. Validate required fields on each resource
        self._validate_required_fields(resources, findings)

        # 2. Build identifier index and verify cross-references
        self._validate_cross_references(resources, findings)

        # 3. Report resource type counts
        self._report_resource_type_counts(resources, findings)

        # 4. Emit per-resource OK findings for resources without errors
        self._emit_per_resource_outcomes(resources, findings)

        return findings

    def _validate_required_fields(
        self,
        resources: List[Any],
        findings: List[Finding],
    ) -> None:
        """Check that each resource entry has the required fields."""
        for idx, resource in enumerate(resources):
            if not isinstance(resource, dict):
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(f"Catalog resource at index {idx} is not a dict"),
                        service="datazone",
                    )
                )
                continue

            missing = _REQUIRED_RESOURCE_FIELDS - set(resource.keys())
            if missing:
                name = resource.get("name", resource.get("identifier", f"index {idx}"))
                rtype = resource.get("type", "unknown")
                display = RESOURCE_TYPE_DISPLAY_NAMES.get(rtype, rtype)
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Catalog resource '{name}' missing required "
                            f"field(s): {', '.join(sorted(missing))}"
                        ),
                        resource=str(name),
                        service=display,
                        details={"missing_fields": sorted(missing)},
                    )
                )

    def _validate_cross_references(
        self,
        resources: List[Any],
        findings: List[Finding],
    ) -> None:
        """Verify that cross-references between catalog resources are resolvable."""
        # Build an index of all known identifiers and names
        # Cross-references can use either sourceId/identifier or name
        known_identifiers: Set[str] = set()
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            identifier = resource.get("identifier")
            if identifier:
                known_identifiers.add(str(identifier))
            name = resource.get("name")
            if name:
                known_identifiers.add(name)

        # Check cross-references using shared field definitions
        for resource in resources:
            if not isinstance(resource, dict):
                continue

            resource_type = resource.get("type", "")
            resource_name = resource.get("name", "unknown")

            # Check top-level cross-reference fields (e.g. glossaryTerms → glossaryId)
            for field_name, target_type in CROSS_REFERENCE_FIELDS.get(
                resource_type, []
            ):
                ref_id = resource.get(field_name)
                if ref_id and ref_id not in known_identifiers:
                    # Skip managed/system types (amazon.datazone.*)
                    if _is_managed_resource(ref_id):
                        continue
                    target_display = RESOURCE_TYPE_DISPLAY_NAMES.get(
                        target_type, target_type
                    )
                    source_display = RESOURCE_TYPE_DISPLAY_NAMES.get(
                        resource_type, resource_type
                    )
                    # Singularize: "glossaries" → "glossary", "form types" → "form type"
                    singular = target_display
                    if singular.endswith("ies"):
                        singular = singular[:-3] + "y"
                    elif singular.endswith("s"):
                        singular = singular[:-1]
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=(
                                f"{(RESOURCE_TYPE_DISPLAY_NAMES.get(resource_type) or resource_type).capitalize()} "
                                f"'{resource_name}' references "
                                f"{singular} '{ref_id}' which is not in "
                                f"the catalog export"
                            ),
                            resource=resource_name,
                            service=source_display,
                        )
                    )

            # Check form type references in formsInput (assets use list, assetTypes use dict)
            if resource_type == "assets":
                forms_input = resource.get("formsInput")
                if isinstance(forms_input, list):
                    for form in forms_input:
                        if not isinstance(form, dict):
                            continue
                        type_id = get_form_type_ref(form)
                        if type_id and type_id not in known_identifiers:
                            if _is_managed_resource(type_id):
                                continue
                            findings.append(
                                Finding(
                                    severity=Severity.ERROR,
                                    message=(
                                        f"Asset '{resource_name}' references "
                                        f"form type '{type_id}' which is not "
                                        f"in the catalog export"
                                    ),
                                    resource=resource_name,
                                    service=RESOURCE_TYPE_DISPLAY_NAMES.get(
                                        "assets", "assets"
                                    ),
                                )
                            )

            if resource_type == "assetTypes":
                forms_input = resource.get("formsInput")
                if isinstance(forms_input, dict):
                    for form_name, form_config in forms_input.items():
                        if not isinstance(form_config, dict):
                            continue
                        type_id = get_form_type_ref(form_config)
                        if type_id and type_id not in known_identifiers:
                            if _is_managed_resource(type_id):
                                continue
                            findings.append(
                                Finding(
                                    severity=Severity.ERROR,
                                    message=(
                                        f"Asset type '{resource_name}' references "
                                        f"form type '{type_id}' which is not "
                                        f"in the catalog export"
                                    ),
                                    resource=resource_name,
                                    service=RESOURCE_TYPE_DISPLAY_NAMES.get(
                                        "assetTypes", "asset types"
                                    ),
                                )
                            )

    def _emit_per_resource_outcomes(
        self,
        resources: List[Any],
        findings: List[Finding],
    ) -> None:
        """Emit an OK finding per valid resource so it appears in the outlook.

        A resource is considered "errored" if any ERROR finding already
        references it by name.  All other dict resources with a ``name``
        get an individual OK finding.
        """
        errored_names: Set[str] = {
            f.resource for f in findings if f.severity == Severity.ERROR and f.resource
        }

        for resource in resources:
            if not isinstance(resource, dict):
                continue
            name = resource.get("name")
            if not name or name in errored_names:
                continue
            rtype = resource.get("type", "unknown")
            display = RESOURCE_TYPE_DISPLAY_NAMES.get(rtype, rtype)
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message=f"{(display or rtype).capitalize()} '{name}' ready for import",
                    resource=name,
                    service=display,
                )
            )

    def _report_resource_type_counts(
        self,
        resources: List[Any],
        findings: List[Finding],
    ) -> None:
        """Report the count of each resource type in the catalog export."""
        type_counts: Counter = Counter()
        for resource in resources:
            if isinstance(resource, dict):
                rtype = resource.get("type", "unknown")
                type_counts[rtype] += 1

        # Build a human-readable summary
        parts = []
        for type_key in CREATION_ORDER:
            count = type_counts.get(type_key, 0)
            if count > 0:
                display_name = RESOURCE_TYPE_DISPLAY_NAMES.get(type_key, type_key)
                parts.append(f"{count} {display_name}")

        # Include any unknown types
        for type_key, count in type_counts.items():
            if type_key not in RESOURCE_TYPE_DISPLAY_NAMES:
                parts.append(f"{count} {type_key}")

        total = sum(type_counts.values())
        summary = ", ".join(parts) if parts else "no resources"

        findings.append(
            Finding(
                severity=Severity.OK,
                message=(
                    f"Catalog import would process {total} resource(s): " f"{summary}"
                ),
                service="datazone",
                details={"type_counts": dict(type_counts), "total": total},
            )
        )

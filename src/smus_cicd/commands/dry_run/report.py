"""Text and JSON report formatters for dry-run results."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from smus_cicd.commands.dry_run.models import DryRunReport, Phase, Severity

_SEVERITY_ICONS = {
    Severity.OK: "✅",
    Severity.WARNING: "⚠️",
    Severity.ERROR: "❌",
}

# Phases that represent actual deployable resources (not infra checks)
_DEPLOYMENT_PHASES: Set[Phase] = {
    Phase.QUICKSIGHT,
    Phase.STORAGE_DEPLOYMENT,
    Phase.GIT_DEPLOYMENT,
    Phase.CATALOG_IMPORT,
    Phase.DEPENDENCY_VALIDATION,
    Phase.WORKFLOW_VALIDATION,
    Phase.BOOTSTRAP_ACTIONS,
}


@dataclass
class ResourceOutcome:
    """Tracks the deployment outcome for a single named resource."""

    name: str
    service: str = ""
    phase: str = ""
    status: str = "ok"  # "ok", "warning", "error"
    reasons: List[str] = field(default_factory=list)


def _collect_resource_outcomes(
    report: DryRunReport,
) -> Dict[str, ResourceOutcome]:
    """Build a map of resource name → ResourceOutcome from deployment phases.

    Also includes error/warning findings from non-deployment phases (e.g.
    Permission Verification) when they carry a ``resource`` attribute, so
    that blockers like missing policy grants appear in the outlook.
    """
    outcomes: Dict[str, ResourceOutcome] = {}

    for phase, findings in report.findings_by_phase.items():
        is_deployment = phase in _DEPLOYMENT_PHASES
        for f in findings:
            if not f.resource:
                continue
            # From non-deployment phases, only surface errors/warnings
            if not is_deployment and f.severity == Severity.OK:
                continue
            name = f.resource
            if name not in outcomes:
                outcomes[name] = ResourceOutcome(
                    name=name,
                    service=f.service or "",
                    phase=phase.value,
                )
            ro = outcomes[name]
            if f.severity == Severity.ERROR:
                ro.status = "error"
                ro.reasons.append(f.message)
            elif f.severity == Severity.WARNING and ro.status != "error":
                ro.status = "warning"
                ro.reasons.append(f.message)

    return outcomes


def _partition_outcomes(
    outcomes: Dict[str, ResourceOutcome],
) -> tuple:
    """Split outcomes into will_deploy, at_risk, will_fail lists."""
    will_deploy: List[ResourceOutcome] = []
    at_risk: List[ResourceOutcome] = []
    will_fail: List[ResourceOutcome] = []

    for ro in sorted(outcomes.values(), key=lambda r: r.name):
        if ro.status == "error":
            will_fail.append(ro)
        elif ro.status == "warning":
            at_risk.append(ro)
        else:
            will_deploy.append(ro)

    return will_deploy, at_risk, will_fail


class ReportFormatter:
    """Renders a DryRunReport in human-readable text or machine-readable JSON."""

    @staticmethod
    def to_text(report: DryRunReport) -> str:
        """Render the report as human-readable text.

        Findings are grouped by phase with severity icons, followed by a
        resource deployment outlook showing which resources will deploy,
        which are at risk, and which will fail with reasons.
        """
        lines: List[str] = []
        lines.append("Dry Run Report")
        lines.append("=" * 40)

        for phase in Phase:
            findings = report.findings_by_phase.get(phase, [])
            if not findings:
                continue
            lines.append("")
            lines.append(f"--- {phase.value} ---")
            for f in findings:
                icon = _SEVERITY_ICONS.get(f.severity, "")
                lines.append(f"  {icon} {f.message}")

        # --- Resource deployment outlook ---
        outcomes = _collect_resource_outcomes(report)
        if outcomes:
            will_deploy, at_risk, will_fail = _partition_outcomes(outcomes)
            lines.append("")
            lines.append("=" * 40)
            lines.append("Resource Deployment Outlook")
            lines.append("-" * 40)

            def _render_group(
                label: str, icon: str, items: List[ResourceOutcome]
            ) -> None:
                if not items:
                    return
                lines.append(f"  {label} ({len(items)}):")
                by_phase: Dict[str, List[ResourceOutcome]] = defaultdict(list)
                for ro in items:
                    by_phase[ro.phase].append(ro)
                for phase_name, ros in by_phase.items():
                    lines.append(f"    [{phase_name}]")
                    for ro in ros:
                        svc = f"  ({ro.service})" if ro.service else ""
                        lines.append(f"      {icon} {ro.name}{svc}")
                        for reason in ro.reasons:
                            lines.append(f"         └─ {reason}")

            _render_group("Will deploy", "✅", will_deploy)
            _render_group("At risk", "⚠️", at_risk)
            _render_group("Will fail", "❌", will_fail)

        lines.append("")
        lines.append("=" * 40)
        lines.append(
            f"Summary: {report.ok_count} OK, "
            f"{report.warning_count} warning(s), "
            f"{report.error_count} error(s)"
        )
        lines.append(
            "Note: Dry run is best-effort. A passing result does not guarantee "
            "deployment success."
        )
        return "\n".join(lines)

    @staticmethod
    def to_json(report: DryRunReport) -> str:
        """Render the report as machine-readable JSON.

        Returns a JSON string with summary, resource_outlook (with source/
        target/reasons per resource), and phases.
        """
        phases: Dict[str, List[Dict[str, Any]]] = {}
        for phase in Phase:
            findings = report.findings_by_phase.get(phase, [])
            if not findings:
                continue
            phases[phase.value] = [
                {"severity": f.severity.value, "message": f.message} for f in findings
            ]

        outcomes = _collect_resource_outcomes(report)
        will_deploy, at_risk, will_fail = _partition_outcomes(outcomes)

        def _group_by_phase(
            items: List[ResourceOutcome],
        ) -> Dict[str, List[Dict[str, Any]]]:
            grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for ro in items:
                d: Dict[str, Any] = {"name": ro.name, "service": ro.service}
                if ro.reasons:
                    d["reasons"] = ro.reasons
                grouped[ro.phase].append(d)
            return dict(grouped)

        data = {
            "summary": {
                "ok": report.ok_count,
                "warnings": report.warning_count,
                "errors": report.error_count,
            },
            "resource_outlook": {
                "will_deploy": _group_by_phase(will_deploy),
                "at_risk": _group_by_phase(at_risk),
                "will_fail": _group_by_phase(will_fail),
            },
            "phases": phases,
        }
        return json.dumps(data, indent=2)

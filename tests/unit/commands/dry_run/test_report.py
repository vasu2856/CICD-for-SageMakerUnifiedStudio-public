"""Unit tests for the dry-run report formatter.

Tests text formatting with mixed severities, JSON formatting,
empty report rendering, phase grouping, and summary counts.

Requirements: 10.4
"""

import json

from smus_cicd.commands.dry_run.models import (
    DryRunReport,
    Finding,
    Phase,
    Severity,
)
from smus_cicd.commands.dry_run.report import ReportFormatter


class TestReportFormatterText:
    """Tests for ReportFormatter.to_text()."""

    def test_mixed_severities_show_correct_icons(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [
                Finding(severity=Severity.OK, message="Manifest loaded"),
                Finding(severity=Severity.WARNING, message="Unresolved var"),
                Finding(severity=Severity.ERROR, message="Missing stage"),
            ],
        )
        text = ReportFormatter.to_text(report)

        assert "✅ Manifest loaded" in text
        assert "⚠️ Unresolved var" in text
        assert "❌ Missing stage" in text

    def test_groups_findings_by_phase(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [Finding(severity=Severity.OK, message="Manifest OK")],
        )
        report.add_findings(
            Phase.BUNDLE_EXPLORATION,
            [Finding(severity=Severity.OK, message="Bundle OK")],
        )
        text = ReportFormatter.to_text(report)

        # Phase headers should appear
        assert "--- Manifest Validation ---" in text
        assert "--- Bundle Exploration ---" in text
        # Manifest section should come before Bundle section
        manifest_pos = text.index("Manifest Validation")
        bundle_pos = text.index("Bundle Exploration")
        assert manifest_pos < bundle_pos

    def test_shows_summary_counts(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [
                Finding(severity=Severity.OK, message="ok1"),
                Finding(severity=Severity.OK, message="ok2"),
            ],
        )
        report.add_findings(
            Phase.PERMISSION_VERIFICATION,
            [Finding(severity=Severity.WARNING, message="warn1")],
        )
        text = ReportFormatter.to_text(report)

        assert "2 OK" in text
        assert "1 warning(s)" in text
        assert "0 error(s)" in text

    def test_empty_report(self):
        report = DryRunReport()
        text = ReportFormatter.to_text(report)

        assert "Dry Run Report" in text
        assert "0 OK" in text
        assert "0 warning(s)" in text
        assert "0 error(s)" in text

    def test_skips_phases_with_no_findings(self):
        report = DryRunReport()
        report.add_findings(
            Phase.CONNECTIVITY,
            [Finding(severity=Severity.OK, message="Domain reachable")],
        )
        text = ReportFormatter.to_text(report)

        # Only the phase with findings should appear
        assert "--- Connectivity & Reachability ---" in text
        assert "--- Manifest Validation ---" not in text


class TestReportFormatterJson:
    """Tests for ReportFormatter.to_json()."""

    def test_produces_valid_json(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [
                Finding(severity=Severity.OK, message="Manifest loaded"),
                Finding(severity=Severity.WARNING, message="Unresolved var"),
                Finding(severity=Severity.ERROR, message="Missing stage"),
            ],
        )
        result = ReportFormatter.to_json(report)
        data = json.loads(result)

        assert isinstance(data, dict)
        assert "summary" in data
        assert "phases" in data

    def test_correct_summary_counts(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [Finding(severity=Severity.OK, message="ok")],
        )
        report.add_findings(
            Phase.BUNDLE_EXPLORATION,
            [
                Finding(severity=Severity.WARNING, message="warn"),
                Finding(severity=Severity.ERROR, message="err"),
            ],
        )
        result = ReportFormatter.to_json(report)
        data = json.loads(result)

        assert data["summary"]["ok"] == 1
        assert data["summary"]["warnings"] == 1
        assert data["summary"]["errors"] == 1

    def test_correct_phase_grouping(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [Finding(severity=Severity.OK, message="Manifest loaded")],
        )
        report.add_findings(
            Phase.PERMISSION_VERIFICATION,
            [Finding(severity=Severity.WARNING, message="Cannot verify")],
        )
        result = ReportFormatter.to_json(report)
        data = json.loads(result)

        assert "Manifest Validation" in data["phases"]
        assert "Permission Verification" in data["phases"]
        assert len(data["phases"]["Manifest Validation"]) == 1
        assert data["phases"]["Manifest Validation"][0]["severity"] == "OK"
        assert data["phases"]["Manifest Validation"][0]["message"] == "Manifest loaded"
        assert data["phases"]["Permission Verification"][0]["severity"] == "WARNING"

    def test_empty_report(self):
        report = DryRunReport()
        result = ReportFormatter.to_json(report)
        data = json.loads(result)

        assert data["summary"]["ok"] == 0
        assert data["summary"]["warnings"] == 0
        assert data["summary"]["errors"] == 0
        assert data["phases"] == {}

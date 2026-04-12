"""Unit tests for dry-run data models.

Tests Finding creation, DryRunReport aggregation, severity counting,
empty report, phase assignment, has_blocking_errors, and render delegation.

Requirements: 10.4
"""

from smus_cicd.commands.dry_run.models import (
    DryRunReport,
    Finding,
    Phase,
    Severity,
)


class TestFinding:
    """Tests for the Finding dataclass."""

    def test_creation_with_all_fields(self):
        finding = Finding(
            severity=Severity.ERROR,
            message="Missing artifact",
            phase=Phase.BUNDLE_EXPLORATION,
            resource="arn:aws:s3:::my-bucket/key",
            service="S3",
            details={"expected": "file.txt", "location": "storage/"},
        )

        assert finding.severity == Severity.ERROR
        assert finding.message == "Missing artifact"
        assert finding.phase == Phase.BUNDLE_EXPLORATION
        assert finding.resource == "arn:aws:s3:::my-bucket/key"
        assert finding.service == "S3"
        assert finding.details == {"expected": "file.txt", "location": "storage/"}

    def test_creation_with_minimal_fields(self):
        finding = Finding(severity=Severity.OK, message="Check passed")

        assert finding.severity == Severity.OK
        assert finding.message == "Check passed"
        assert finding.phase is None
        assert finding.resource is None
        assert finding.service is None
        assert finding.details is None


class TestDryRunReport:
    """Tests for the DryRunReport dataclass."""

    def test_empty_report_counts(self):
        report = DryRunReport()

        assert report.ok_count == 0
        assert report.warning_count == 0
        assert report.error_count == 0
        assert report.findings_by_phase == {}

    def test_add_findings_sets_phase(self):
        findings = [
            Finding(severity=Severity.OK, message="Good"),
            Finding(severity=Severity.WARNING, message="Watch out"),
        ]
        report = DryRunReport()
        report.add_findings(Phase.MANIFEST_VALIDATION, findings)

        for f in findings:
            assert f.phase == Phase.MANIFEST_VALIDATION

    def test_severity_counting(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [
                Finding(severity=Severity.OK, message="ok1"),
                Finding(severity=Severity.OK, message="ok2"),
                Finding(severity=Severity.WARNING, message="warn1"),
            ],
        )
        report.add_findings(
            Phase.BUNDLE_EXPLORATION,
            [
                Finding(severity=Severity.ERROR, message="err1"),
                Finding(severity=Severity.OK, message="ok3"),
            ],
        )

        assert report.ok_count == 3
        assert report.warning_count == 1
        assert report.error_count == 1

    def test_has_blocking_errors_true(self):
        report = DryRunReport()
        report.add_findings(
            Phase.PERMISSION_VERIFICATION,
            [
                Finding(severity=Severity.OK, message="ok"),
                Finding(severity=Severity.ERROR, message="denied"),
            ],
        )

        assert report.has_blocking_errors(Phase.PERMISSION_VERIFICATION) is True

    def test_has_blocking_errors_false_no_errors(self):
        report = DryRunReport()
        report.add_findings(
            Phase.CONNECTIVITY,
            [
                Finding(severity=Severity.OK, message="reachable"),
                Finding(severity=Severity.WARNING, message="slow"),
            ],
        )

        assert report.has_blocking_errors(Phase.CONNECTIVITY) is False

    def test_has_blocking_errors_false_empty_phase(self):
        report = DryRunReport()

        assert report.has_blocking_errors(Phase.BOOTSTRAP_ACTIONS) is False

    def test_render_delegates_to_text(self):
        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [Finding(severity=Severity.OK, message="Manifest loaded")],
        )
        text = report.render("text")

        assert "Manifest loaded" in text
        assert "Dry Run Report" in text

    def test_render_delegates_to_json(self):
        import json

        report = DryRunReport()
        report.add_findings(
            Phase.MANIFEST_VALIDATION,
            [Finding(severity=Severity.OK, message="Manifest loaded")],
        )
        result = report.render("json")
        data = json.loads(result)

        assert "summary" in data
        assert "phases" in data

    def test_render_defaults_to_text(self):
        report = DryRunReport()
        text = report.render()

        assert "Dry Run Report" in text

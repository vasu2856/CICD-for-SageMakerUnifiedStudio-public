"""Tests for PreflightChecker — validates shared preconditions."""

from dataclasses import dataclass
from typing import Any

import pytest

from smus_cicd.commands.dry_run.checkers.preflight_checker import PreflightChecker
from smus_cicd.commands.dry_run.models import DryRunContext, Severity


@dataclass
class _FakeTarget:
    project: Any = None


@pytest.fixture
def checker():
    return PreflightChecker()


class TestPreflightCheckerPass:
    def test_both_present_produces_ok(self, checker):
        ctx = DryRunContext(
            manifest_file="m.yaml",
            target_config=_FakeTarget(),
            config={"region": "us-east-1"},
        )
        findings = checker.check(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "passed" in findings[0].message.lower()


class TestPreflightCheckerFail:
    def test_no_target_config_produces_error(self, checker):
        ctx = DryRunContext(
            manifest_file="m.yaml", target_config=None, config={"region": "us-east-1"}
        )
        findings = checker.check(ctx)
        assert any(
            f.severity == Severity.ERROR and "target" in f.message.lower()
            for f in findings
        )

    def test_no_config_produces_error(self, checker):
        ctx = DryRunContext(
            manifest_file="m.yaml", target_config=_FakeTarget(), config=None
        )
        findings = checker.check(ctx)
        assert any(
            f.severity == Severity.ERROR and "config" in f.message.lower()
            for f in findings
        )

    def test_both_missing_produces_two_errors(self, checker):
        ctx = DryRunContext(manifest_file="m.yaml", target_config=None, config=None)
        findings = checker.check(ctx)
        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 2

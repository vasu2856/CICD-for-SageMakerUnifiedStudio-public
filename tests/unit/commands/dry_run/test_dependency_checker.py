"""Unit tests for DependencyChecker (Phase 9b — Dependency Validation).

Tests cover:
- No catalog data → WARNING skip
- No manifest/target → WARNING skip
- Empty resources → OK
- Missing Glue databases (EntityNotFoundException)
- Missing Glue tables and views
- Partition accessibility (WARNING on failure)
- Missing data sources
- Missing custom form types
- Missing custom asset types
- Unresolvable form type revisions / revision mismatch
- Managed resource skipping (amazon.datazone. prefix)
- Caching behaviour for all API calls
- Glue client creation failure

Requirements: 10.7
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from smus_cicd.commands.dry_run.checkers.dependency_checker import (
    DependencyChecker,
)
from smus_cicd.commands.dry_run.models import DryRunContext, Severity
from smus_cicd.helpers.catalog_import import parse_form_content

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_error(code: str = "EntityNotFoundException") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "not found"}}, "op")


def _make_context(
    catalog_data: Optional[Dict[str, Any]] = None,
    region: str = "us-east-1",
    domain_id: str = "dzd_test",
    project_id: str = "proj_test",
    has_target: bool = True,
) -> DryRunContext:
    return DryRunContext(
        manifest_file="manifest.yaml",
        target_config=object() if has_target else None,
        config=(
            {
                "region": region,
                "domain_id": domain_id,
                "project_id": project_id,
            }
            if has_target
            else None
        ),
        catalog_data=catalog_data,
    )


def _glue_asset(
    db_name: str,
    table_name: str,
    asset_name: str = "my-asset",
    table_type: str = "",
    ds_form: bool = False,
    ds_type: str = "GLUE",
    extra_forms: Optional[List[Dict[str, Any]]] = None,
    type_identifier: str = "",
) -> Dict[str, Any]:
    """Build a catalog asset dict with a GlueTableFormType form."""
    forms: List[Dict[str, Any]] = [
        {
            "typeIdentifier": "amazon.datazone.GlueTableFormType",
            "content": json.dumps(
                {
                    "databaseName": db_name,
                    "tableName": table_name,
                    "tableType": table_type,
                }
            ),
        }
    ]
    if ds_form:
        forms.append(
            {
                "typeIdentifier": "amazon.datazone.DataSourceReferenceFormType",
                "content": json.dumps({"dataSourceType": ds_type}),
            }
        )
    if extra_forms:
        forms.extend(extra_forms)
    asset: Dict[str, Any] = {
        "type": "assets",
        "name": asset_name,
        "identifier": "id-1",
        "formsInput": forms,
    }
    if type_identifier:
        asset["typeIdentifier"] = type_identifier
    return asset


def _asset_type_resource(
    name: str = "CustomType",
    forms_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "type": "assetTypes",
        "name": name,
        "identifier": "at-1",
        "formsInput": forms_input or {},
    }


@pytest.fixture
def checker() -> DependencyChecker:
    return DependencyChecker()


# ---------------------------------------------------------------------------
# Skip / early-return paths
# ---------------------------------------------------------------------------


class TestDependencyCheckerSkipPaths:
    def test_no_catalog_data_produces_warning(self, checker):
        ctx = _make_context(catalog_data=None)
        findings = checker.check(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "no catalog data" in findings[0].message.lower()

    def test_no_target_config_produces_warning(self, checker):
        ctx = _make_context(has_target=False, catalog_data={"resources": []})
        # target_config is None
        ctx.target_config = None
        findings = checker.check(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert (
            "manifest" in findings[0].message.lower()
            or "target" in findings[0].message.lower()
        )

    def test_no_config_dict_produces_warning(self, checker):
        ctx = DryRunContext(
            manifest_file="m.yaml",
            target_config=object(),
            config=None,
            catalog_data={"resources": [{"type": "assets"}]},
        )
        findings = checker.check(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING

    def test_empty_resources_produces_ok(self, checker):
        ctx = _make_context(catalog_data={"resources": []})
        findings = checker.check(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.OK
        assert "no catalog resources" in findings[0].message.lower()


# ---------------------------------------------------------------------------
# Glue database validation
# ---------------------------------------------------------------------------


class TestGlueDatabaseValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_existing_database_no_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0
        glue.get_database.assert_called_once_with(Name="mydb")

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_database_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.side_effect = _client_error("EntityNotFoundException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("missing_db", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        db_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "database" in f.message.lower()
        ]
        assert len(db_errors) >= 1
        assert "missing_db" in db_errors[0].message

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_database_access_denied_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.side_effect = _client_error("AccessDeniedException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("secret_db", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "secret_db" in f.message
        ]
        assert len(errors) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_database_generic_exception_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.side_effect = RuntimeError("boom")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("bad_db", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "bad_db" in f.message
        ]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Glue table / view validation
# ---------------------------------------------------------------------------


class TestGlueTableValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_table_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.side_effect = _client_error("EntityNotFoundException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "missing_tbl")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        tbl_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "table" in f.message.lower()
        ]
        assert len(tbl_errors) >= 1
        assert "missing_tbl" in tbl_errors[0].message

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_view_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.side_effect = _client_error("EntityNotFoundException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "missing_view", table_type="VIRTUAL_VIEW")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        view_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "view" in f.message.lower()
        ]
        assert len(view_errors) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_existing_table_no_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "good_tbl")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert len(errors) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_table_access_denied_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.side_effect = _client_error("AccessDeniedException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "secret_tbl")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "secret_tbl" in f.message
        ]
        assert len(errors) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_view_skips_partition_check(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "my_view", table_type="VIEW")
        ctx = _make_context(catalog_data={"resources": [asset]})
        checker.check(ctx)

        glue.get_partitions.assert_not_called()


# ---------------------------------------------------------------------------
# Partition accessibility
# ---------------------------------------------------------------------------


class TestPartitionAccessibility:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_accessible_partitions_no_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "partition" in f.message.lower()
        ]
        assert len(warnings) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_inaccessible_partitions_produce_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.side_effect = _client_error("AccessDeniedException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "partition" in f.message.lower()
        ]
        assert len(warnings) == 1
        assert "inaccessible" in warnings[0].message.lower()

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_partition_generic_exception_produces_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.side_effect = RuntimeError("timeout")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "partition" in f.message.lower()
        ]
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Data source validation
# ---------------------------------------------------------------------------


class TestDataSourceValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_matching_data_source_no_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}

        dz = MagicMock()
        dz.list_data_sources.return_value = {
            "items": [{"type": "GLUE", "status": "READY", "name": "mydb-source"}]
        }

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = _glue_asset("mydb", "mytable", ds_form=True)
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        ds_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "data source" in f.message.lower()
        ]
        assert len(ds_warnings) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_data_source_produces_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}

        dz = MagicMock()
        dz.list_data_sources.return_value = {"items": []}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = _glue_asset("mydb", "mytable", ds_form=True)
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        ds_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "data source" in f.message.lower()
        ]
        assert len(ds_warnings) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_data_source_api_failure_produces_warning(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}

        dz = MagicMock()
        dz.list_data_sources.side_effect = RuntimeError("api down")

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = _glue_asset("mydb", "mytable", ds_form=True)
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        ds_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "data source" in f.message.lower()
        ]
        assert len(ds_warnings) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_no_domain_id_skips_data_source_check(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable", ds_form=True)
        ctx = _make_context(catalog_data={"resources": [asset]}, domain_id="")
        findings = checker.check(ctx)

        ds_warnings = [f for f in findings if "data source" in f.message.lower()]
        assert len(ds_warnings) == 0


# ---------------------------------------------------------------------------
# Custom form type validation
# ---------------------------------------------------------------------------


class TestCustomFormTypeValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_existing_form_type_no_error(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.return_value = {"name": "MyForm", "revision": "1"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        at = _asset_type_resource(
            forms_input={"myForm": {"typeIdentifier": "custom.MyFormType"}}
        )
        ctx = _make_context(catalog_data={"resources": [at]})
        findings = checker.check(ctx)

        ft_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "form type" in f.message.lower()
        ]
        assert len(ft_errors) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_form_type_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.side_effect = _client_error("ResourceNotFoundException")

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        at = _asset_type_resource(
            forms_input={"myForm": {"typeIdentifier": "custom.MissingForm"}}
        )
        ctx = _make_context(catalog_data={"resources": [at]})
        findings = checker.check(ctx)

        ft_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "custom.MissingForm" in f.message
        ]
        assert len(ft_errors) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_managed_form_type_skipped(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        at = _asset_type_resource(
            forms_input={"managed": {"typeIdentifier": "amazon.datazone.SomeFormType"}}
        )
        ctx = _make_context(catalog_data={"resources": [at]})
        findings = checker.check(ctx)

        ft_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "form type" in f.message.lower()
        ]
        assert len(ft_errors) == 0
        dz.get_form_type.assert_not_called()

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_typeName_fallback(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.return_value = {"name": "FallbackForm", "revision": "1"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        at = _asset_type_resource(
            forms_input={"myForm": {"typeName": "custom.FallbackForm"}}
        )
        ctx = _make_context(catalog_data={"resources": [at]})
        findings = checker.check(ctx)

        ft_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "form type" in f.message.lower()
        ]
        assert len(ft_errors) == 0


# ---------------------------------------------------------------------------
# Custom asset type validation
# ---------------------------------------------------------------------------


class TestCustomAssetTypeValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_existing_asset_type_no_error(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.search_types.return_value = {"items": [{"name": "CustomAsset"}]}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "typeIdentifier": "custom.MyAssetType",
            "formsInput": [],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        at_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "asset type" in f.message.lower()
        ]
        assert len(at_errors) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_asset_type_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.search_types.return_value = {"items": []}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "typeIdentifier": "custom.MissingAssetType",
            "formsInput": [],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        at_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "custom.MissingAssetType" in f.message
        ]
        assert len(at_errors) >= 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_managed_asset_type_skipped(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "typeIdentifier": "amazon.datazone.ManagedType",
            "formsInput": [],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        at_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "asset type" in f.message.lower()
        ]
        assert len(at_errors) == 0
        dz.search_types.assert_not_called()

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_search_types_api_failure_produces_error(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.search_types.side_effect = RuntimeError("api error")

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "typeIdentifier": "custom.FailType",
            "formsInput": [],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        at_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "custom.FailType" in f.message
        ]
        assert len(at_errors) >= 1


# ---------------------------------------------------------------------------
# Form type revision validation
# ---------------------------------------------------------------------------


class TestFormTypeRevisionValidation:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_matching_revision_no_warning(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.return_value = {"name": "MyForm", "revision": "3"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "formsInput": [
                {
                    "typeIdentifier": "custom.MyFormType",
                    "typeRevision": "3",
                    "content": "{}",
                }
            ],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        rev_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "revision" in f.message.lower()
        ]
        assert len(rev_warnings) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_mismatched_revision_produces_warning(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.return_value = {"name": "MyForm", "revision": "5"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "formsInput": [
                {
                    "typeIdentifier": "custom.MyFormType",
                    "typeRevision": "3",
                    "content": "{}",
                }
            ],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        rev_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "revision" in f.message.lower()
        ]
        assert len(rev_warnings) >= 1
        assert "does not match" in rev_warnings[0].message.lower()

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_unresolvable_revision_produces_warning(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        # Form type exists but has no revision field
        dz.get_form_type.return_value = {"name": "MyForm"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "formsInput": [
                {
                    "typeIdentifier": "custom.MyFormType",
                    "typeRevision": "2",
                    "content": "{}",
                }
            ],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        rev_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "revision" in f.message.lower()
        ]
        assert len(rev_warnings) >= 1
        assert "cannot be resolved" in rev_warnings[0].message.lower()

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_form_type_skips_revision_check(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.side_effect = _client_error("ResourceNotFoundException")

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "formsInput": [
                {
                    "typeIdentifier": "custom.GoneForm",
                    "typeRevision": "1",
                    "content": "{}",
                }
            ],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        # Should not have a revision warning — the form type itself is missing
        rev_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "revision" in f.message.lower()
        ]
        assert len(rev_warnings) == 0

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_managed_form_type_revision_skipped(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset = {
            "type": "assets",
            "name": "my-asset",
            "identifier": "id-1",
            "formsInput": [
                {
                    "typeIdentifier": "amazon.datazone.SomeFormType",
                    "typeRevision": "1",
                    "content": "{}",
                }
            ],
        }
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        rev_warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "revision" in f.message.lower()
        ]
        assert len(rev_warnings) == 0
        dz.get_form_type.assert_not_called()


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


class TestCachingBehaviour:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_database_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        # Two assets referencing the same database
        asset1 = _glue_asset("shared_db", "tbl1", asset_name="asset1")
        asset2 = _glue_asset("shared_db", "tbl2", asset_name="asset2")
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        checker.check(ctx)

        # get_database should be called only once for "shared_db"
        assert glue.get_database.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_table_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        # Two assets referencing the same table
        asset1 = _glue_asset("mydb", "shared_tbl", asset_name="asset1")
        asset2 = _glue_asset("mydb", "shared_tbl", asset_name="asset2")
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        checker.check(ctx)

        # get_table should be called only once for ("mydb", "shared_tbl")
        assert glue.get_table.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_partition_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}
        mock_boto3.client.return_value = glue

        asset1 = _glue_asset("mydb", "tbl", asset_name="asset1")
        asset2 = _glue_asset("mydb", "tbl", asset_name="asset2")
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        checker.check(ctx)

        assert glue.get_partitions.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_missing_database_cache_still_reports_for_second_asset(
        self, mock_boto3, checker
    ):
        glue = MagicMock()
        glue.get_database.side_effect = _client_error("EntityNotFoundException")
        mock_boto3.client.return_value = glue

        asset1 = _glue_asset("gone_db", "tbl1", asset_name="asset1")
        asset2 = _glue_asset("gone_db", "tbl2", asset_name="asset2")
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        findings = checker.check(ctx)

        db_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR
            and "database" in f.message.lower()
            and "gone_db" in f.message
        ]
        # Should report for both assets
        assert len(db_errors) == 2
        # But only one API call
        assert glue.get_database.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_form_type_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.return_value = {"name": "MyForm", "revision": "1"}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        # Two asset types referencing the same form type
        at1 = _asset_type_resource(
            name="Type1",
            forms_input={"f": {"typeIdentifier": "custom.SharedForm"}},
        )
        at2 = _asset_type_resource(
            name="Type2",
            forms_input={"f": {"typeIdentifier": "custom.SharedForm"}},
        )
        ctx = _make_context(catalog_data={"resources": [at1, at2]})
        checker.check(ctx)

        assert dz.get_form_type.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_asset_type_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.search_types.return_value = {"items": [{"name": "CustomAsset"}]}

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset1 = {
            "type": "assets",
            "name": "a1",
            "identifier": "id-1",
            "typeIdentifier": "custom.SharedAssetType",
            "formsInput": [],
        }
        asset2 = {
            "type": "assets",
            "name": "a2",
            "identifier": "id-2",
            "typeIdentifier": "custom.SharedAssetType",
            "formsInput": [],
        }
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        checker.check(ctx)

        assert dz.search_types.call_count == 1

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_data_source_cache_prevents_duplicate_api_calls(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.return_value = {}
        glue.get_table.return_value = {}
        glue.get_partitions.return_value = {}

        dz = MagicMock()
        dz.list_data_sources.return_value = {
            "items": [{"type": "GLUE", "status": "READY", "name": "src"}]
        }

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        asset1 = _glue_asset("mydb", "tbl1", asset_name="a1", ds_form=True)
        asset2 = _glue_asset("mydb", "tbl2", asset_name="a2", ds_form=True)
        ctx = _make_context(catalog_data={"resources": [asset1, asset2]})
        checker.check(ctx)

        # Both assets have same db_name → same cache key → one API call
        assert dz.list_data_sources.call_count == 1


# ---------------------------------------------------------------------------
# Glue client creation failure
# ---------------------------------------------------------------------------


class TestGlueClientFailure:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_glue_client_creation_failure_produces_warning(self, mock_boto3, checker):
        mock_boto3.client.side_effect = RuntimeError("no credentials")

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        warnings = [
            f
            for f in findings
            if f.severity == Severity.WARNING and "glue client" in f.message.lower()
        ]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# parse_form_content edge cases (shared function from catalog_import)
# ---------------------------------------------------------------------------


class TestParseFormContent:
    def test_none_content_returns_none(self):
        assert parse_form_content(None) is None

    def test_empty_string_returns_none(self):
        assert parse_form_content("") is None

    def test_dict_content_returned_as_is(self):
        d = {"key": "value"}
        assert parse_form_content(d) == d

    def test_valid_json_string_parsed(self):
        result = parse_form_content('{"a": 1}')
        assert result == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert parse_form_content("not json") is None

    def test_json_array_returns_none(self):
        assert parse_form_content("[1, 2]") is None

    def test_json_number_returns_none(self):
        assert parse_form_content("42") is None


# ---------------------------------------------------------------------------
# Finding metadata
# ---------------------------------------------------------------------------


class TestFindingMetadata:
    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_glue_error_has_service_and_resource(self, mock_boto3, checker):
        glue = MagicMock()
        glue.get_database.side_effect = _client_error("EntityNotFoundException")
        mock_boto3.client.return_value = glue

        asset = _glue_asset("mydb", "mytable")
        ctx = _make_context(catalog_data={"resources": [asset]})
        findings = checker.check(ctx)

        db_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "database" in f.message.lower()
        ]
        assert db_errors[0].service == "glue"
        assert db_errors[0].resource == "mydb"
        assert db_errors[0].details is not None
        assert db_errors[0].details["resource_type"] == "database"

    @patch("smus_cicd.commands.dry_run.checkers.dependency_checker.boto3")
    def test_form_type_error_has_service_and_details(self, mock_boto3, checker):
        glue = MagicMock()
        dz = MagicMock()
        dz.get_form_type.side_effect = _client_error("ResourceNotFoundException")

        def _client_factory(service, **kw):
            return glue if service == "glue" else dz

        mock_boto3.client.side_effect = _client_factory

        at = _asset_type_resource(
            forms_input={"f": {"typeIdentifier": "custom.MissingForm"}}
        )
        ctx = _make_context(catalog_data={"resources": [at]})
        findings = checker.check(ctx)

        ft_errors = [
            f
            for f in findings
            if f.severity == Severity.ERROR and "form type" in f.message.lower()
        ]
        assert ft_errors[0].service == "datazone"
        assert ft_errors[0].resource == "custom.MissingForm"
        assert ft_errors[0].details["form_type"] == "custom.MissingForm"

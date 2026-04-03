"""Unit tests for the destroy command.

Covers:
  Level 1 (U1–U6):   Operator registry
  Level 2 (U7–U14):  QuickSight list helpers
  Level 3 (U15–U26): Pure helper functions
  Level 4 (U27–U36): Validation phase
  Level 5 (U37–U49): Destruction phase
  Level 6 (U50–U73): Command entry point and CLI
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from smus_cicd.cli import app
from smus_cicd.helpers.operator_registry import OPERATOR_REGISTRY, _delete_glue_job
from smus_cicd.helpers.quicksight import (
    QuickSightDeploymentError,
    list_dashboards,
    list_data_sources,
)
from smus_cicd.commands.destroy import (
    ResourceResult,
    ResourceToDelete,
    S3Target,
    ValidationResult,
    _discover_workflow_created_resources,
    _destroy_stage,
    _get_active_workflow_runs,
    _parse_workflow_yaml_from_s3,
    _resolve_resource_prefix,
    _resolve_s3_targets,
    _validate_stage,
    destroy_command,
)
from smus_cicd.application.application_manifest import (
    ApplicationManifest,
    ContentConfig,
    DeploymentConfiguration,
    DomainConfig,
    GitTargetConfig,
    ProjectConfig,
    QuickSightDashboardConfig,
    StageConfig,
    StorageConfig,
)


# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------

GLUE_OPERATOR_KEY = "airflow.providers.amazon.aws.operators.glue.GlueJobOperator"
runner = CliRunner()

PATCH_FROM_FILE = "smus_cicd.commands.destroy.ApplicationManifest.from_file"
PATCH_VALIDATE = "smus_cicd.commands.destroy._validate_stage"
PATCH_DESTROY_STAGE = "smus_cicd.commands.destroy._destroy_stage"
PATCH_CONFIRM = "smus_cicd.commands.destroy.Confirm.ask"
PATCH_STOP_RUN = "smus_cicd.commands.destroy.stop_workflow_run"
PATCH_DELETE_WF = "smus_cicd.commands.destroy.delete_workflow"
PATCH_GET_ACTIVE = "smus_cicd.commands.destroy._get_active_workflow_runs"
PATCH_DOMAIN = "smus_cicd.commands.destroy.get_domain_from_target_config"
PATCH_PROJECT_ID = "smus_cicd.commands.destroy.get_project_id_by_name"
PATCH_DELETE_PROJECT = "smus_cicd.commands.destroy.delete_project"
PATCH_BOTO3 = "smus_cicd.commands.destroy.boto3"
PATCH_CONNECTIONS = "smus_cicd.commands.destroy.get_project_connections"
PATCH_DASHBOARDS = "smus_cicd.commands.destroy.list_dashboards"
PATCH_DATASETS = "smus_cicd.commands.destroy.list_datasets"
PATCH_DATASOURCES = "smus_cicd.commands.destroy.list_data_sources"
PATCH_LIST_WORKFLOWS = "smus_cicd.commands.destroy.list_workflows"
PATCH_LIST_RUNS = "smus_cicd.commands.destroy.list_workflow_runs"
PATCH_IS_ACTIVE = "smus_cicd.commands.destroy.is_workflow_run_active"
PATCH_PARSE_YAML = "smus_cicd.commands.destroy._parse_workflow_yaml_from_s3"
PATCH_STS = "smus_cicd.commands.destroy.boto3"


def _make_manifest(app_name="TestApp", quicksight_assets=None, workflows=None, storage=None):
    return ApplicationManifest(
        application_name=app_name,
        content=ContentConfig(
            quicksight=[QuickSightDashboardConfig(name=q) for q in (quicksight_assets or [])],
            workflows=workflows or [],
            storage=storage or [],
        ),
        stages={},
    )


def _make_stage_config(
    project_name="test-project",
    region="us-east-1",
    create=False,
    has_quicksight=False,
    qs_prefix="deployed-{stage.name}-covid-",
    storage=None,
    git=None,
):
    qs_config = None
    if has_quicksight:
        qs_config = {
            "overrideParameters": {
                "ResourceIdOverrideConfiguration": {"PrefixForAllResources": qs_prefix}
            }
        }
    dc = DeploymentConfiguration(
        storage=[
            StorageConfig(name=s["name"], connectionName=s["connectionName"],
                          targetDirectory=s.get("targetDirectory", ""))
            for s in (storage or [])
        ],
        git=[
            GitTargetConfig(name=g["name"], connectionName=g["connectionName"],
                            targetDirectory=g.get("targetDirectory", ""))
            for g in (git or [])
        ],
        quicksight=qs_config,
    )
    return StageConfig(
        project=ProjectConfig(name=project_name, create=create),
        domain=DomainConfig(region=region),
        stage="DEV",
        deployment_configuration=dc,
    )


def _make_vr(resources=None, active_runs=None, errors=None):
    return ValidationResult(
        errors=errors or [],
        warnings=[],
        resources=resources or [],
        active_workflow_runs=active_runs or {},
    )


def _make_manifest_mock(stages=None, app_name="TestApp", workflows=None):
    stages_dict = {}
    for name in (stages or ["dev"]):
        stages_dict[name] = StageConfig(
            project=ProjectConfig(name=f"{name}-project"),
            domain=DomainConfig(region="us-east-1"),
            stage=name.upper(),
            deployment_configuration=DeploymentConfiguration(),
        )
    return ApplicationManifest(
        application_name=app_name,
        content=ContentConfig(workflows=workflows or []),
        stages=stages_dict,
    )


def _ok_results():
    return [ResourceResult("quicksight_dashboard", "dash-1", "deleted", "OK")]


# ---------------------------------------------------------------------------
# Level 1: Operator registry (U1–U6)
# ---------------------------------------------------------------------------

class TestOperatorRegistry:
    def test_u1_registry_contains_glue_operator(self):
        assert GLUE_OPERATOR_KEY in OPERATOR_REGISTRY

    def test_u2_glue_entry_resource_name_field(self):
        assert OPERATOR_REGISTRY[GLUE_OPERATOR_KEY]["resource_name_field"] == "job_name"

    def test_u3_glue_entry_delete_fn_is_callable(self):
        assert callable(OPERATOR_REGISTRY[GLUE_OPERATOR_KEY]["delete_fn"])

    @patch("smus_cicd.helpers.operator_registry.boto3")
    def test_u4_delete_glue_job_calls_correct_api(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        _delete_glue_job("my-glue-job", "us-east-1")
        mock_boto3.client.assert_called_once_with("glue", region_name="us-east-1")
        mock_client.delete_job.assert_called_once_with(JobName="my-glue-job")

    @patch("smus_cicd.helpers.operator_registry.boto3")
    def test_u5_entity_not_found_raises_resource_not_found_error(self, mock_boto3):
        from smus_cicd.helpers.operator_registry import ResourceNotFoundError
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.delete_job.side_effect = ClientError(
            {"Error": {"Code": "EntityNotFoundException", "Message": "Not found"}}, "DeleteJob"
        )
        with pytest.raises(ResourceNotFoundError):
            _delete_glue_job("missing-job", "us-east-1")

    @patch("smus_cicd.helpers.operator_registry.boto3")
    def test_u6_other_errors_propagated(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.delete_job.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "DeleteJob"
        )
        with pytest.raises(ClientError):
            _delete_glue_job("some-job", "us-east-1")


# ---------------------------------------------------------------------------
# Level 2: QuickSight list helpers (U7–U14)
# ---------------------------------------------------------------------------

class TestListDashboards:
    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u7_single_page(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_dashboards.return_value = {
            "DashboardSummaryList": [{"DashboardId": "d1"}, {"DashboardId": "d2"}]
        }
        assert list_dashboards("123456789012", "us-east-1") == [{"DashboardId": "d1"}, {"DashboardId": "d2"}]

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u8_multi_page_follows_next_token(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_dashboards.side_effect = [
            {"DashboardSummaryList": [{"DashboardId": "d1"}], "NextToken": "tok"},
            {"DashboardSummaryList": [{"DashboardId": "d2"}]},
        ]
        result = list_dashboards("123456789012", "us-east-1")
        assert result == [{"DashboardId": "d1"}, {"DashboardId": "d2"}]
        assert mock_client.list_dashboards.call_count == 2

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u9_empty_response(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_dashboards.return_value = {"DashboardSummaryList": []}
        assert list_dashboards("123456789012", "us-east-1") == []

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u10_client_error_raises(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_dashboards.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "ListDashboards"
        )
        with pytest.raises(QuickSightDeploymentError):
            list_dashboards("123456789012", "us-east-1")


class TestListDataSources:
    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u11_single_page(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_data_sources.return_value = {
            "DataSources": [{"DataSourceId": "ds1"}, {"DataSourceId": "ds2"}]
        }
        assert list_data_sources("123456789012", "us-east-1") == [{"DataSourceId": "ds1"}, {"DataSourceId": "ds2"}]

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u12_multi_page_follows_next_token(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_data_sources.side_effect = [
            {"DataSources": [{"DataSourceId": "ds1"}], "NextToken": "tok"},
            {"DataSources": [{"DataSourceId": "ds2"}]},
        ]
        result = list_data_sources("123456789012", "us-east-1")
        assert result == [{"DataSourceId": "ds1"}, {"DataSourceId": "ds2"}]
        assert mock_client.list_data_sources.call_count == 2

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u13_empty_response(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_data_sources.return_value = {"DataSources": []}
        assert list_data_sources("123456789012", "us-east-1") == []

    @patch("smus_cicd.helpers.quicksight.boto3")
    def test_u14_client_error_raises(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_data_sources.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "ListDataSources"
        )
        with pytest.raises(QuickSightDeploymentError):
            list_data_sources("123456789012", "us-east-1")


# ---------------------------------------------------------------------------
# Level 3: Pure helper functions (U15–U26)
# ---------------------------------------------------------------------------

class TestResolveResourcePrefix:
    def test_u15_replaces_stage_name(self):
        qs_config = {"overrideParameters": {"ResourceIdOverrideConfiguration": {"PrefixForAllResources": "deployed-{stage.name}-covid-"}}}
        assert _resolve_resource_prefix("dev", qs_config) == "deployed-dev-covid-"

    def test_u15b_test_stage(self):
        qs_config = {"overrideParameters": {"ResourceIdOverrideConfiguration": {"PrefixForAllResources": "deployed-{stage.name}-covid-"}}}
        assert _resolve_resource_prefix("test", qs_config) == "deployed-test-covid-"

    def test_u16_no_variable_unchanged(self):
        qs_config = {"overrideParameters": {"ResourceIdOverrideConfiguration": {"PrefixForAllResources": "static-prefix-"}}}
        assert _resolve_resource_prefix("dev", qs_config) == "static-prefix-"

    def test_u17_empty_config_returns_empty(self):
        assert _resolve_resource_prefix("dev", {}) == ""


class TestDiscoverWorkflowCreatedResources:
    def _yaml(self, tasks):
        return {"wf": {"tasks": tasks}}

    def test_u18_glue_operator_returns_glue_job(self):
        result = _discover_workflow_created_resources(
            self._yaml({"t1": {"operator": GLUE_OPERATOR_KEY, "job_name": "my-job"}}), "dev"
        )
        assert len(result) == 1
        assert result[0].resource_type == "glue_job"
        assert result[0].resource_id == "my-job"

    def test_u19_unregistered_operator_returns_skipped(self):
        result = _discover_workflow_created_resources(
            self._yaml({"t1": {"operator": "SageMakerNotebookOperator"}}), "dev"
        )
        assert result[0].resource_type == "skipped"
        assert result[0].metadata["reason"] == "operator not in registry"

    def test_u20_template_variable_in_job_name_skipped(self):
        result = _discover_workflow_created_resources(
            self._yaml({"t1": {"operator": GLUE_OPERATOR_KEY, "job_name": "{proj.name}-job"}}), "dev"
        )
        assert result[0].resource_type == "skipped"
        assert "template variable" in result[0].metadata["reason"]

    def test_u21_mixed_operators_correct_counts(self):
        result = _discover_workflow_created_resources(self._yaml({
            "g": {"operator": GLUE_OPERATOR_KEY, "job_name": "real-job"},
            "n": {"operator": "SageMakerNotebookOperator"},
            "t": {"operator": GLUE_OPERATOR_KEY, "job_name": "{x}-job"},
        }), "dev")
        assert len(result) == 3
        assert sum(1 for r in result if r.resource_type == "glue_job") == 1
        assert sum(1 for r in result if r.resource_type == "skipped") == 2

    def test_u22_empty_tasks_returns_empty(self):
        assert _discover_workflow_created_resources({"wf": {"tasks": {}}}, "dev") == []


class TestResolveS3Targets:
    def _connections(self, entries):
        return {name: {"s3Uri": uri, "bucket_name": uri.replace("s3://", "").split("/")[0]}
                for name, uri in entries}

    def test_u23_two_non_overlapping_entries(self):
        sc = _make_stage_config(
            storage=[{"name": "a", "connectionName": "c1", "targetDirectory": "a/bundle"},
                     {"name": "b", "connectionName": "c2", "targetDirectory": "b/files"}]
        )
        result = _resolve_s3_targets(sc, self._connections([("c1", "s3://bkt/base/"), ("c2", "s3://bkt/base/")]))
        assert len(result) == 2

    def test_u24_overlapping_prefixes_deduplicates(self):
        sc = _make_stage_config(
            storage=[{"name": "bundle", "connectionName": "c1", "targetDirectory": "bundle"},
                     {"name": "wf", "connectionName": "c1", "targetDirectory": "bundle/workflows"}]
        )
        result = _resolve_s3_targets(sc, self._connections([("c1", "s3://bkt/base/")]))
        assert len(result) == 1

    def test_u25_storage_and_git_combined(self):
        sc = _make_stage_config(
            storage=[{"name": "app", "connectionName": "c1", "targetDirectory": "app"}],
            git=[{"name": "repo", "connectionName": "c1", "targetDirectory": "repos"}],
        )
        result = _resolve_s3_targets(sc, self._connections([("c1", "s3://bkt/base/")]))
        assert len(result) == 2

    def test_u26_no_deployment_configuration_returns_empty(self):
        sc = StageConfig(project=ProjectConfig(name="p"), domain=DomainConfig(region="us-east-1"),
                         stage="DEV", deployment_configuration=None)
        assert _resolve_s3_targets(sc, {}) == []


# ---------------------------------------------------------------------------
# Level 4: Validation phase (U27–U36)
# ---------------------------------------------------------------------------

class TestValidateStageClean:
    @patch(PATCH_PARSE_YAML, return_value={})
    @patch(PATCH_LIST_RUNS, return_value=[])
    @patch(PATCH_LIST_WORKFLOWS, return_value=[])
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    def test_u27_clean_stage_no_errors(self, *_):
        result = _validate_stage("dev", _make_stage_config(), _make_manifest(), "us-east-1")
        assert result.errors == []


class TestValidateStageQuickSightCollisions:
    def _sts_mock(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts

    @patch(PATCH_DATASOURCES, return_value=[])
    @patch(PATCH_DATASETS, return_value=[])
    @patch(PATCH_DASHBOARDS)
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_STS)
    def test_u28_dashboard_collision(self, mock_boto3, mock_domain, mock_project, mock_conns,
                                     mock_dashboards, mock_datasets, mock_sources):
        self._sts_mock(mock_boto3)
        mock_dashboards.return_value = [
            {"DashboardId": "deployed-dev-covid-d1"},
            {"DashboardId": "deployed-dev-covid-d2"},
        ]
        result = _validate_stage("dev", _make_stage_config(has_quicksight=True),
                                 _make_manifest(quicksight_assets=["TotalDeathByCountry"]), "us-east-1")
        assert any("dashboard" in e.lower() or "collision" in e.lower() for e in result.errors)

    @patch(PATCH_DATASOURCES, return_value=[])
    @patch(PATCH_DATASETS)
    @patch(PATCH_DASHBOARDS, return_value=[])
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_STS)
    def test_u29_dataset_collision(self, mock_boto3, mock_domain, mock_project, mock_conns,
                                   mock_dashboards, mock_datasets, mock_sources):
        self._sts_mock(mock_boto3)
        mock_datasets.return_value = [{"DataSetId": "deployed-dev-covid-ds1"}, {"DataSetId": "deployed-dev-covid-ds2"}]
        result = _validate_stage("dev", _make_stage_config(has_quicksight=True),
                                 _make_manifest(quicksight_assets=["TotalDeathByCountry"]), "us-east-1")
        assert any("dataset" in e.lower() or "collision" in e.lower() for e in result.errors)

    @patch(PATCH_DATASOURCES)
    @patch(PATCH_DATASETS, return_value=[])
    @patch(PATCH_DASHBOARDS, return_value=[])
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_STS)
    def test_u30_data_source_collision(self, mock_boto3, mock_domain, mock_project, mock_conns,
                                       mock_dashboards, mock_datasets, mock_sources):
        self._sts_mock(mock_boto3)
        mock_sources.return_value = [{"DataSourceId": "deployed-dev-covid-s1"}, {"DataSourceId": "deployed-dev-covid-s2"}]
        result = _validate_stage("dev", _make_stage_config(has_quicksight=True),
                                 _make_manifest(quicksight_assets=["TotalDeathByCountry"]), "us-east-1")
        assert any("data source" in e.lower() or "collision" in e.lower() for e in result.errors)


class TestValidateStageWorkflows:
    @patch(PATCH_PARSE_YAML, return_value={})
    @patch(PATCH_LIST_RUNS, return_value=[])
    @patch(PATCH_LIST_WORKFLOWS)
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    def test_u31_workflow_name_collision(self, mock_domain, mock_project, mock_conns, mock_wf, *_):
        mock_wf.return_value = [
            {"name": "TestApp_test_project_my_dag", "workflow_arn": "arn:1"},
            {"name": "TestApp_test_project_my_dag", "workflow_arn": "arn:2"},
        ]
        result = _validate_stage("dev", _make_stage_config(project_name="test-project"),
                                 _make_manifest(app_name="TestApp", workflows=[{"workflowName": "my-dag"}]),
                                 "us-east-1")
        assert any("collision" in e.lower() or "workflow" in e.lower() for e in result.errors)

    @patch(PATCH_PARSE_YAML, return_value={})
    @patch(PATCH_IS_ACTIVE, return_value=True)
    @patch(PATCH_LIST_RUNS)
    @patch(PATCH_LIST_WORKFLOWS)
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    def test_u32_active_runs_populated(self, mock_domain, mock_project, mock_conns, mock_wf, mock_runs, *_):
        mock_wf.return_value = [{"name": "TestApp_test_project_my_dag", "workflow_arn": "arn:wf1"}]
        mock_runs.return_value = [{"run_id": "run-001", "status": "RUNNING", "ended_at": None}]
        result = _validate_stage("dev", _make_stage_config(project_name="test-project"),
                                 _make_manifest(app_name="TestApp", workflows=[{"workflowName": "my-dag"}]),
                                 "us-east-1")
        assert "run-001" in result.active_workflow_runs.get("TestApp_test_project_my_dag", [])

    @patch(PATCH_LIST_RUNS, return_value=[])
    @patch(PATCH_LIST_WORKFLOWS)
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    def test_u33_yaml_not_found_warning(self, mock_domain, mock_project, mock_conns, mock_wf, mock_runs):
        mock_wf.return_value = [{"name": "TestApp_test_project_my_dag", "workflow_arn": "arn:wf1"}]
        sc = _make_stage_config(project_name="test-project",
                                storage=[{"name": "workflows", "connectionName": "c1", "targetDirectory": "wf"}])
        with patch(PATCH_CONNECTIONS, return_value={"c1": {"s3Uri": "s3://bkt/base/", "bucket_name": "bkt"}}):
            with patch(PATCH_PARSE_YAML, return_value={}):
                result = _validate_stage("dev", sc,
                                         _make_manifest(app_name="TestApp", workflows=[{"workflowName": "my-dag"}]),
                                         "us-east-1")
        assert any("yaml" in w.lower() or "workflow" in w.lower() for w in result.warnings)
        assert result.errors == []

    @patch(PATCH_PARSE_YAML, return_value={})
    @patch(PATCH_LIST_RUNS, return_value=[])
    @patch(PATCH_LIST_WORKFLOWS)
    @patch(PATCH_CONNECTIONS, return_value={})
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    def test_u34_multiple_stages_all_errors_collected(self, mock_domain, mock_project, mock_conns, mock_wf, *_):
        mock_wf.return_value = [{"name": "TestApp_proj_dag1", "workflow_arn": "arn:1"},
                                 {"name": "TestApp_proj_dag1", "workflow_arn": "arn:2"}]
        manifest = _make_manifest(app_name="TestApp", workflows=[{"workflowName": "dag1"}])
        sc = _make_stage_config(project_name="proj")
        r1 = _validate_stage("dev", sc, manifest, "us-east-1")
        r2 = _validate_stage("test", sc, manifest, "us-east-1")
        assert len(r1.errors + r2.errors) >= 2

    def test_u35_no_deployment_configuration_resolve_s3_empty(self):
        sc = StageConfig(project=ProjectConfig(name="p"), domain=DomainConfig(region="us-east-1"),
                         stage="DEV", deployment_configuration=None)
        assert _resolve_s3_targets(sc, {}) == []

    @patch(PATCH_DOMAIN, side_effect=Exception("Domain not found"))
    def test_u36_domain_failure_records_error(self, _):
        result = _validate_stage("dev", _make_stage_config(), _make_manifest(), "us-east-1")
        assert any("domain" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Level 5: Destruction phase (U37–U49)
# ---------------------------------------------------------------------------

def _simple_manifest():
    return ApplicationManifest(application_name="App", content=ContentConfig(), stages={})


class TestDestroyOrdering:
    @patch(PATCH_DELETE_PROJECT)
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_BOTO3)
    @patch(PATCH_DELETE_WF)
    @patch(PATCH_STOP_RUN)
    @patch(PATCH_GET_ACTIVE, return_value=["run-001"])
    def test_u37_destruction_order(self, mock_get_active, mock_stop, mock_delete_wf,
                                   mock_boto3, mock_domain, mock_project_id, mock_delete_project):
        """U37: stop_run → glue_delete → delete_workflow → QS → S3 → delete_project."""
        call_order = []
        mock_stop.side_effect = lambda **kw: call_order.append("stop_run") or {"success": True}
        mock_delete_wf.side_effect = lambda arn, region: call_order.append("delete_workflow")

        sts_client = MagicMock()
        sts_client.get_caller_identity.return_value = {"Account": "111122223333"}
        qs_client = MagicMock()
        s3_client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter([{"Contents": [{"Key": "k1"}]}])
        s3_client.get_paginator.return_value = paginator

        def client_factory(service, region_name=None):
            if service == "sts":
                return sts_client
            if service == "quicksight":
                qs_client.delete_dashboard.side_effect = lambda **kw: call_order.append("delete_dashboard")
                return qs_client
            if service == "s3":
                s3_client.delete_objects.side_effect = lambda **kw: call_order.append("delete_s3")
                return s3_client
            return MagicMock()

        mock_boto3.client.side_effect = client_factory
        mock_delete_project.side_effect = lambda *a, **kw: call_order.append("delete_project")

        glue_client = MagicMock()
        glue_client.delete_job.side_effect = lambda **kw: call_order.append("delete_glue")

        with patch("smus_cicd.helpers.operator_registry.boto3") as mock_glue_boto3:
            mock_glue_boto3.client.return_value = glue_client
            wf_arn = "arn:aws:airflow:us-east-1:111:workflow/wf1"
            resources = [
                ResourceToDelete("airflow_workflow", wf_arn, "dev", {"workflow_name": "App_proj_dag"}),
                ResourceToDelete("glue_job", "my-glue-job", "dev", {"operator": GLUE_OPERATOR_KEY, "task_name": "t1"}),
                ResourceToDelete("quicksight_dashboard", "deployed-dev-dash1", "dev", {}),
                ResourceToDelete("s3_prefix", "s3://bucket/prefix", "dev", {"bucket": "bucket", "prefix": "prefix"}),
            ]
            vr = _make_vr(resources=resources, active_runs={"App_proj_dag": ["run-001"]})
            _destroy_stage("dev", _make_stage_config(create=True), _simple_manifest(), vr, "us-east-1", "TEXT")

        assert call_order.index("stop_run") < call_order.index("delete_workflow")
        assert call_order.index("delete_glue") < call_order.index("delete_workflow")
        assert call_order.index("delete_workflow") < call_order.index("delete_dashboard")
        assert call_order.index("delete_dashboard") < call_order.index("delete_s3")
        assert call_order.index("delete_s3") < call_order.index("delete_project")


class TestStopWorkflowRunFailure:
    @patch(PATCH_DELETE_WF)
    @patch(PATCH_STOP_RUN, side_effect=Exception("Stop failed"))
    @patch(PATCH_GET_ACTIVE, return_value=["run-001"])
    @patch(PATCH_BOTO3)
    def test_u38_stop_fails_workflow_not_deleted(self, mock_boto3, mock_get_active, mock_stop, mock_delete_wf):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        wf_arn = "arn:aws:airflow:us-east-1:111:workflow/wf1"
        vr = _make_vr(resources=[ResourceToDelete("airflow_workflow", wf_arn, "dev", {"workflow_name": "my_wf"})],
                      active_runs={"my_wf": ["run-001"]})
        results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        mock_delete_wf.assert_not_called()
        assert any(r.status == "error" for r in results)


class TestWorkflowRunRecheck:
    @patch(PATCH_DELETE_WF)
    @patch(PATCH_STOP_RUN)
    @patch(PATCH_GET_ACTIVE, return_value=[])
    @patch(PATCH_BOTO3)
    def test_u39_completed_run_not_stopped(self, mock_boto3, mock_get_active, mock_stop, mock_delete_wf):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        wf_arn = "arn:aws:airflow:us-east-1:111:workflow/wf1"
        vr = _make_vr(resources=[ResourceToDelete("airflow_workflow", wf_arn, "dev", {"workflow_name": "my_wf"})],
                      active_runs={"my_wf": ["run-001"]})
        _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        mock_stop.assert_not_called()

    @patch(PATCH_DELETE_WF)
    @patch(PATCH_STOP_RUN)
    @patch(PATCH_GET_ACTIVE, return_value=["new-run-002"])
    @patch(PATCH_BOTO3)
    def test_u40_new_run_after_validation_stopped(self, mock_boto3, mock_get_active, mock_stop, mock_delete_wf):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        wf_arn = "arn:aws:airflow:us-east-1:111:workflow/wf1"
        vr = _make_vr(resources=[ResourceToDelete("airflow_workflow", wf_arn, "dev", {"workflow_name": "my_wf"})],
                      active_runs={"my_wf": ["old-run-001"]})
        _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        mock_stop.assert_called_once()
        assert "new-run-002" in str(mock_stop.call_args)


class TestProjectCreateFlag:
    @patch(PATCH_DELETE_PROJECT)
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_BOTO3)
    def test_u41_project_create_false_no_delete(self, mock_boto3, mock_domain, mock_project_id, mock_delete_project):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        _destroy_stage("dev", _make_stage_config(create=False), _simple_manifest(), _make_vr(), "us-east-1", "TEXT")
        mock_delete_project.assert_not_called()

    @patch(PATCH_DELETE_PROJECT)
    @patch(PATCH_PROJECT_ID, return_value="proj-123")
    @patch(PATCH_DOMAIN, return_value=("dom-123", "my-domain"))
    @patch(PATCH_BOTO3)
    def test_u42_project_create_true_delete_called(self, mock_boto3, mock_domain, mock_project_id, mock_delete_project):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        _destroy_stage("dev", _make_stage_config(create=True), _simple_manifest(), _make_vr(), "us-east-1", "TEXT")
        mock_delete_project.assert_called_once()


class TestNotFoundHandling:
    @patch(PATCH_BOTO3)
    def test_u43_quicksight_not_found_recorded(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        qs = MagicMock()
        qs.delete_dashboard.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, "DeleteDashboard"
        )
        mock_boto3.client.side_effect = lambda s, region_name=None: sts if s == "sts" else qs
        vr = _make_vr(resources=[ResourceToDelete("quicksight_dashboard", "dash-1", "dev", {})])
        results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert any(r.status == "not_found" for r in results)

    @patch(PATCH_BOTO3)
    def test_u44_glue_not_found_recorded(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        mock_boto3.client.return_value = sts
        with patch("smus_cicd.helpers.operator_registry.boto3") as mock_glue:
            glue = MagicMock()
            glue.delete_job.side_effect = ClientError(
                {"Error": {"Code": "EntityNotFoundException", "Message": "Not found"}}, "DeleteJob"
            )
            mock_glue.client.return_value = glue
            vr = _make_vr(resources=[ResourceToDelete("glue_job", "missing-job", "dev",
                                                       {"operator": GLUE_OPERATOR_KEY, "task_name": "t1"})])
            results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert any(r.status == "not_found" for r in results)

    @patch(PATCH_BOTO3)
    def test_u45_s3_empty_prefix_not_found(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter([{}])
        s3.get_paginator.return_value = paginator
        mock_boto3.client.side_effect = lambda s, region_name=None: sts if s == "sts" else s3
        vr = _make_vr(resources=[ResourceToDelete("s3_prefix", "s3://bkt/p", "dev", {"bucket": "bkt", "prefix": "p"})])
        results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert any(r.status == "not_found" for r in results)


class TestErrorResilience:
    @patch(PATCH_BOTO3)
    def test_u46_non_recoverable_error_continues(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        qs = MagicMock()
        call_count = [0]

        def delete_dashboard(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ClientError({"Error": {"Code": "InternalFailure", "Message": "Error"}}, "DeleteDashboard")

        qs.delete_dashboard.side_effect = delete_dashboard
        mock_boto3.client.side_effect = lambda s, region_name=None: sts if s == "sts" else qs
        vr = _make_vr(resources=[ResourceToDelete("quicksight_dashboard", "dash-1", "dev", {}),
                                   ResourceToDelete("quicksight_dashboard", "dash-2", "dev", {})])
        results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        statuses = {r.resource_id: r.status for r in results}
        assert statuses["dash-1"] == "error"
        assert statuses["dash-2"] == "deleted"

    @patch(PATCH_BOTO3)
    def test_u47_all_absent_all_not_found(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        qs = MagicMock()
        qs.delete_dashboard.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, "DeleteDashboard"
        )
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter([{}])
        s3.get_paginator.return_value = paginator

        def client_factory(s, region_name=None):
            if s == "sts":
                return sts
            if s == "quicksight":
                return qs
            return s3

        mock_boto3.client.side_effect = client_factory
        vr = _make_vr(resources=[ResourceToDelete("quicksight_dashboard", "dash-1", "dev", {}),
                                   ResourceToDelete("s3_prefix", "s3://bkt/p", "dev", {"bucket": "bkt", "prefix": "p"})])
        results = _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert not any(r.status == "error" for r in results)
        assert sum(1 for r in results if r.status == "not_found") == 2

    @patch(PATCH_BOTO3)
    def test_u48_only_prefix_matching_ids_deleted(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        deleted_ids = []
        qs = MagicMock()
        qs.delete_dashboard.side_effect = lambda **kw: deleted_ids.append(kw.get("DashboardId"))
        mock_boto3.client.side_effect = lambda s, region_name=None: sts if s == "sts" else qs
        vr = _make_vr(resources=[ResourceToDelete("quicksight_dashboard", "deployed-dev-covid-dash1", "dev", {})])
        _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert deleted_ids == ["deployed-dev-covid-dash1"]

    @patch(PATCH_BOTO3)
    def test_u49_s3_deletion_scoped_to_prefix(self, mock_boto3):
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "111122223333"}
        deleted_keys = []
        s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.side_effect = lambda Bucket, Prefix: (
            iter([{"Contents": [{"Key": "base/bundle/f1.py"}, {"Key": "base/bundle/f2.py"}]}])
            if Prefix == "base/bundle" else iter([{}])
        )
        s3.get_paginator.return_value = paginator
        s3.delete_objects.side_effect = lambda Bucket, Delete: deleted_keys.extend(o["Key"] for o in Delete["Objects"])
        mock_boto3.client.side_effect = lambda s, region_name=None: sts if s == "sts" else s3
        vr = _make_vr(resources=[ResourceToDelete("s3_prefix", "s3://bkt/base/bundle", "dev",
                                                   {"bucket": "bkt", "prefix": "base/bundle"})])
        _destroy_stage("dev", _make_stage_config(), _simple_manifest(), vr, "us-east-1", "TEXT")
        assert all(k.startswith("base/bundle") for k in deleted_keys)
        assert "base/bundle/f1.py" in deleted_keys


# ---------------------------------------------------------------------------
# Level 6: Command entry point and CLI (U50–U73)
# ---------------------------------------------------------------------------

class TestInvalidStageName:
    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u50_invalid_stage_exits_1(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev", "test"])
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "nonexistent", "--force"])
        assert result.exit_code == 1
        assert "nonexistent" in result.output or "nonexistent" in (result.stderr or "")
        mock_validate.assert_not_called()
        mock_destroy.assert_not_called()


class TestManifestNotFound:
    @patch(PATCH_FROM_FILE, side_effect=ValueError("Not found"))
    def test_u51_manifest_not_found_exits_1(self, _):
        result = runner.invoke(app, ["destroy", "--manifest", "nonexistent.yaml", "--force"])
        assert result.exit_code == 1


class TestValidationErrorsAbort:
    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u52_validation_errors_abort(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr(errors=["QuickSight collision"])
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        assert result.exit_code == 1
        mock_destroy.assert_not_called()

    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u53_all_stage_errors_in_report(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev", "test"])
        mock_validate.side_effect = [_make_vr(errors=["dev collision"]), _make_vr(errors=["test collision"])]
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev,test", "--force"])
        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert "dev collision" in combined
        assert "test collision" in combined
        mock_destroy.assert_not_called()


class TestDestructionPlan:
    @patch(PATCH_CONFIRM, return_value=False)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u54_plan_printed_before_confirmation(self, mock_from_file, mock_validate, mock_confirm):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr(resources=[
            ResourceToDelete("quicksight_dashboard", "dash-1", "dev", {}),
        ])
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev"])
        assert result.exit_code == 0
        assert "dash-1" in result.output


class TestForceAndConfirmation:
    @patch(PATCH_DESTROY_STAGE, return_value=_ok_results())
    @patch(PATCH_CONFIRM, return_value=True)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u55_user_confirms_proceeds(self, mock_from_file, mock_validate, mock_confirm, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev"])
        mock_destroy.assert_called_once()

    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_CONFIRM, return_value=False)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u56_user_declines_exit_0_no_deletion(self, mock_from_file, mock_validate, mock_confirm, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev"])
        assert result.exit_code == 0
        mock_destroy.assert_not_called()

    @patch(PATCH_DESTROY_STAGE, return_value=_ok_results())
    @patch(PATCH_CONFIRM)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u57_force_skips_prompt(self, mock_from_file, mock_validate, mock_confirm, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        mock_confirm.assert_not_called()
        mock_destroy.assert_called_once()

    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u58_force_with_collision_still_aborts(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr(errors=["Collision!"])
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        assert result.exit_code == 1
        mock_destroy.assert_not_called()

    @patch(PATCH_DESTROY_STAGE, return_value=_ok_results())
    @patch(PATCH_CONFIRM)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u59_force_with_active_runs_no_prompt(self, mock_from_file, mock_validate, mock_confirm, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = ValidationResult(
            errors=[], warnings=[],
            resources=[ResourceToDelete("airflow_workflow", "arn:wf1", "dev", {"workflow_name": "my_wf"})],
            active_workflow_runs={"my_wf": ["run-001"]},
        )
        runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        mock_confirm.assert_not_called()
        mock_destroy.assert_called_once()


class TestExitCodes:
    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u60_error_result_exits_1(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        mock_destroy.return_value = [ResourceResult("quicksight_dashboard", "d1", "error", "API error")]
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        assert result.exit_code == 1

    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u61_all_deleted_exits_0(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        mock_destroy.return_value = [ResourceResult("quicksight_dashboard", "d1", "deleted", "OK")]
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        assert result.exit_code == 0


class TestJsonOutput:
    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u62_json_output_valid_structure(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"], app_name="MyApp")
        mock_validate.return_value = _make_vr()
        mock_destroy.return_value = [ResourceResult("quicksight_dashboard", "dash-1", "deleted", "OK")]
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force", "--output", "JSON"])
        assert result.exit_code == 0
        output = result.output
        data = json.loads(output[output.find("{"):output.rfind("}") + 1])
        assert data["application_name"] == "MyApp"
        assert "dev" in data["stages"]
        assert data["stages"]["dev"][0]["resource_id"] == "dash-1"

    @patch(PATCH_DESTROY_STAGE, return_value=[])
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u63_json_stdout_parseable(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force", "--output", "JSON"])
        output = result.output
        json.loads(output[output.find("{"):output.rfind("}") + 1])


class TestSummaryOutput:
    @patch(PATCH_DESTROY_STAGE)
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u64_summary_shows_counts(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev"])
        mock_validate.return_value = _make_vr()
        mock_destroy.return_value = [
            ResourceResult("quicksight_dashboard", "d1", "deleted", "OK"),
            ResourceResult("s3_prefix", "s3://b/p", "not_found", "Empty"),
            ResourceResult("glue_job", "j1", "skipped", "Template var"),
        ]
        result = runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev", "--force"])
        assert "deleted=1" in result.output
        assert "not_found=1" in result.output
        assert "skipped=1" in result.output


class TestCliRegistration:
    def test_u65_destroy_command_registered(self):
        result = runner.invoke(app, ["destroy", "--help"])
        assert result.exit_code == 0
        assert "manifest" in result.output.lower()


class TestEdgeCases:
    def test_u69_workflow_yaml_no_tasks_empty_list(self):
        assert _discover_workflow_created_resources({"wf": {"tasks": {}}}, "dev") == []

    def test_u70_parse_yaml_s3_error_returns_empty(self):
        with patch("smus_cicd.commands.destroy.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_client.get_object.side_effect = Exception("S3 error")
            mock_boto3.client.return_value = mock_client
            assert _parse_workflow_yaml_from_s3("bucket", "key.yaml", "us-east-1") == {}

    def test_u71_parse_yaml_invalid_yaml_returns_empty(self):
        with patch("smus_cicd.commands.destroy.boto3") as mock_boto3:
            mock_client = MagicMock()
            body = MagicMock()
            body.read.return_value = b": invalid: yaml: {"
            mock_client.get_object.return_value = {"Body": body}
            mock_boto3.client.return_value = mock_client
            assert _parse_workflow_yaml_from_s3("bucket", "key.yaml", "us-east-1") == {}

    @patch(PATCH_DESTROY_STAGE, return_value=_ok_results())
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u72_multiple_targets_each_processed(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev", "test"])
        mock_validate.return_value = _make_vr()
        runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--targets", "dev,test", "--force"])
        assert mock_validate.call_count == 2
        assert mock_destroy.call_count == 2

    @patch(PATCH_DESTROY_STAGE, return_value=_ok_results())
    @patch(PATCH_VALIDATE)
    @patch(PATCH_FROM_FILE)
    def test_u73_default_targets_all_stages(self, mock_from_file, mock_validate, mock_destroy):
        mock_from_file.return_value = _make_manifest_mock(stages=["dev", "test", "prod"])
        mock_validate.return_value = _make_vr()
        runner.invoke(app, ["destroy", "--manifest", "m.yaml", "--force"])
        assert mock_validate.call_count == 3
        assert mock_destroy.call_count == 3


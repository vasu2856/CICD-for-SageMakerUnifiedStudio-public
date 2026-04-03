"""Integration test for Dashboard-Glue-Quick workflow deployment."""

import json
import os
import re
import subprocess
import time

import boto3
import pytest

from tests.integration.base import IntegrationTestBase


def _get_account_id():
    """Get AWS account ID dynamically via STS."""
    return boto3.client("sts").get_caller_identity()["Account"]


def _get_region():
    """Get region from TEST_DOMAIN_REGION env var, defaulting to us-east-2."""
    return os.environ.get("TEST_DOMAIN_REGION", "us-east-2")


class TestDashboardGlueQuickWorkflow(IntegrationTestBase):
    """Test Dashboard-Glue-Quick workflow deployment with QuickSight."""

    def setup_method(self, method):
        """Set up test environment."""
        super().setup_method(method)
        self.setup_test_directory()
        self.cleanup_glue_databases()
        self.cleanup_quicksight_dashboards()
        self.setup_quicksight_test_dashboard()

    def cleanup_quicksight_dashboards(self):
        """Delete test QuickSight dashboards from previous runs."""
        region = _get_region()
        account_id = _get_account_id()
        quicksight_client = boto3.client("quicksight", region_name=region)

        dashboards_to_delete = ["deployed-test-covid-dashboard"]
        for dashboard_id in dashboards_to_delete:
            try:
                quicksight_client.delete_dashboard(
                    AwsAccountId=account_id, DashboardId=dashboard_id
                )
                self.logger.info(f"✅ Deleted QuickSight dashboard: {dashboard_id}")
            except quicksight_client.exceptions.ResourceNotFoundException:
                pass
            except Exception as e:
                self.logger.info(f"⚠️ Could not delete dashboard {dashboard_id}: {e}")

    def setup_quicksight_test_dashboard(self):
        """Import test dashboard if it doesn't exist."""
        from smus_cicd.helpers.quicksight import lookup_dashboard_by_name

        region = _get_region()
        account_id = _get_account_id()
        quicksight_client = boto3.client("quicksight", region_name=region)
        dashboard_name = "TotalDeathByCountry"

        try:
            dashboard_id = lookup_dashboard_by_name(dashboard_name, account_id, region)
            self.logger.info(
                f"✅ Test dashboard already exists: {dashboard_name} (ID: {dashboard_id})"
            )
        except Exception:
            self.logger.info(f"📊 Importing test dashboard: {dashboard_name}")
            setup_script = os.path.join(
                os.path.dirname(__file__),
                "../../../../examples/analytic-workflow/dashboard-glue-quick/quicksight/setup_test_dashboard.py",
            )
            result = subprocess.run(
                ["python", setup_script], capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info(f"✅ Test dashboard imported: {dashboard_name}")
            else:
                self.logger.warning(
                    f"⚠️ Failed to import test dashboard: {result.stderr}"
                )

    def cleanup_glue_databases(self):
        """Delete test Glue databases and S3 data."""
        region = _get_region()
        glue_client = boto3.client("glue", region_name=region)
        s3_client = boto3.client("s3", region_name=region)

        try:
            glue_client.delete_table(DatabaseName="covid19_db", Name="us_simplified")
            self.logger.info("✅ Deleted old covid19_db.us_simplified table")
        except glue_client.exceptions.EntityNotFoundException:
            pass
        except Exception as e:
            self.logger.warning(f"⚠️ Could not delete covid19_db.us_simplified: {e}")

        for db_name in ["analytic_workflow_test_db", "covid19_summary_db"]:
            try:
                try:
                    db_info = glue_client.get_database(Name=db_name)
                    location_uri = db_info.get("Database", {}).get("LocationUri", "")
                    if location_uri.startswith("s3://"):
                        bucket_and_key = location_uri[5:].split("/", 1)
                        bucket = bucket_and_key[0]
                        prefix = bucket_and_key[1] if len(bucket_and_key) > 1 else ""
                        paginator = s3_client.get_paginator("list_objects_v2")
                        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                            objects = page.get("Contents", [])
                            if objects:
                                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                                s3_client.delete_objects(
                                    Bucket=bucket, Delete={"Objects": delete_keys}
                                )
                                self.logger.info(
                                    f"✅ Deleted S3 data: s3://{bucket}/{prefix}"
                                )
                except glue_client.exceptions.EntityNotFoundException:
                    pass

                glue_client.delete_database(Name=db_name)
                self.logger.info(f"✅ Deleted Glue database: {db_name}")
            except glue_client.exceptions.EntityNotFoundException:
                pass
            except Exception as e:
                self.logger.info(f"⚠️ Could not delete database {db_name}: {e}")

    def get_pipeline_file(self):
        return os.path.join(
            os.path.dirname(__file__),
            "../../../../examples/analytic-workflow/dashboard-glue-quick/manifest.yaml",
        )

    def verify_quicksight_dashboard_deployed(self):
        """Verify QuickSight dashboard was deployed successfully."""
        region = _get_region()
        account_id = _get_account_id()
        quicksight_client = boto3.client("quicksight", region_name=region)
        dashboard_prefix = "deployed-test-covid-"

        try:
            response = quicksight_client.list_dashboards(AwsAccountId=account_id)
            dashboards = response.get("DashboardSummaryList", [])

            deployed_dashboard = next(
                (d for d in dashboards if d["DashboardId"].startswith(dashboard_prefix)),
                None,
            )
            if not deployed_dashboard:
                pytest.fail(
                    f"Dashboard with prefix {dashboard_prefix} not found after deploy"
                )

            dashboard_id = deployed_dashboard["DashboardId"]
            self.logger.info(f"✅ Dashboard deployed: {dashboard_id}")
            self.logger.info(f"   Name: {deployed_dashboard['Name']}")

            detail_response = quicksight_client.describe_dashboard(
                AwsAccountId=account_id, DashboardId=dashboard_id
            )
            self.logger.info(
                f"   Version: {detail_response['Dashboard']['Version']['VersionNumber']}"
            )
            assert deployed_dashboard["Name"].startswith(
                "deployed-test-"
            ), "Dashboard name should have deployment prefix"

            dataset_count = len(
                quicksight_client.list_data_sets(AwsAccountId=account_id).get(
                    "DataSetSummaries", []
                )
            )
            self.logger.info(f"✅ Datasets found: {dataset_count}")
            assert dataset_count > 0, "Should have at least one dataset"

            source_count = len(
                quicksight_client.list_data_sources(AwsAccountId=account_id).get(
                    "DataSources", []
                )
            )
            self.logger.info(f"✅ Data sources found: {source_count}")
            assert source_count > 0, "Should have at least one data source"

        except Exception as e:
            pytest.fail(f"Error verifying QuickSight dashboard: {e}")

    @pytest.mark.integration
    def test_dashboard_glue_quick_workflow_deployment(self):
        """Test Dashboard-Glue-Quick workflow deployment with QuickSight."""
        if not self.verify_aws_connectivity():
            pytest.skip("AWS connectivity not available")

        region = _get_region()
        account_id = _get_account_id()
        pipeline_file = self.get_pipeline_file()
        workflow_name = "covid_dashboard_glue_quick_pipeline"

        # Cleanup: Delete QuickSight deployed assets from previous runs
        self.logger.info("\n=== Cleanup: Delete QuickSight deployed assets ===")
        try:
            qs = boto3.client("quicksight", region_name=region)
            for dash in qs.list_dashboards(AwsAccountId=account_id)["DashboardSummaryList"]:
                if dash["DashboardId"].startswith("deployed-test"):
                    qs.delete_dashboard(AwsAccountId=account_id, DashboardId=dash["DashboardId"])
                    self.logger.info(f"✅ Deleted dashboard: {dash['DashboardId']}")
            for ds in qs.list_data_sets(AwsAccountId=account_id)["DataSetSummaries"]:
                if ds["DataSetId"].startswith("deployed-test"):
                    qs.delete_data_set(AwsAccountId=account_id, DataSetId=ds["DataSetId"])
                    self.logger.info(f"✅ Deleted dataset: {ds['DataSetId']}")
            for src in qs.list_data_sources(AwsAccountId=account_id)["DataSources"]:
                if src["DataSourceId"].startswith("deployed-test"):
                    qs.delete_data_source(AwsAccountId=account_id, DataSourceId=src["DataSourceId"])
                    self.logger.info(f"✅ Deleted data source: {src['DataSourceId']}")
        except Exception as e:
            self.logger.info(f"⚠️ Could not delete QuickSight assets: {e}")

        # Step 1: Describe --connect (test target only)
        self.logger.info("\n=== Step 1: Describe with Connections ===")
        result = self.run_cli_command(
            ["describe", "--manifest", pipeline_file, "--targets", "test", "--connect"]
        )
        assert result["success"], f"Describe --connect failed: {result['output']}"
        self.logger.info("✅ Describe --connect successful")

        # Step 2: Bundle from local filesystem (no dev project needed)
        self.logger.info("\n=== Step 2: Bundle from local filesystem ===")
        result = self.run_cli_command(
            ["bundle", "--manifest", pipeline_file, "--targets", "test", "--local"]
        )
        assert result["success"], f"Bundle failed: {result['output']}"
        self.logger.info("✅ Bundle successful")

        # Step 3: Deploy
        self.logger.info("\n=== Step 3: Deploy ===")
        result = self.run_cli_command(
            ["deploy", "--targets", "test", "--manifest", pipeline_file]
        )
        assert result["success"], f"Deploy failed: {result['output']}"
        self.logger.info("✅ Deploy successful")

        # Step 3.5: Verify QuickSight Dashboard Deployed
        self.logger.info("\n=== Step 3.5: Verify QuickSight Dashboard ===")
        self.verify_quicksight_dashboard_deployed()

        # Step 5: Monitor
        self.logger.info("\n=== Step 5: Monitor ===")
        result = self.run_cli_command(
            ["monitor", "--targets", "test", "--manifest", pipeline_file]
        )
        assert result["success"], f"Monitor failed: {result['output']}"
        self.logger.info("✅ Monitor successful")

        # Step 6: Run workflow and extract ARN
        self.logger.info("\n=== Step 6: Run Workflow ===")
        result = self.run_cli_command(
            ["run", "--workflow", workflow_name, "--targets", "test", "--manifest", pipeline_file]
        )
        assert result["success"], f"Run workflow failed: {result['output']}"

        workflow_arn_match = re.search(
            r"🔗 ARN: (arn:aws:airflow-serverless:[^\s]+)", result["output"]
        )
        workflow_arn = workflow_arn_match.group(1) if workflow_arn_match else None
        self.logger.info(
            f"✅ Workflow started: {workflow_arn}" if workflow_arn else "✅ Workflow started (ARN not found)"
        )

        # Step 7: Monitor workflow status
        self.logger.info("\n=== Step 7: Monitor Workflow Status ===")
        result = self.run_cli_command(
            ["monitor", "--targets", "test", "--manifest", pipeline_file]
        )
        assert result["success"], f"Monitor after run failed: {result['output']}"
        self.logger.info("✅ Monitor after run successful")

        # Step 8: Wait for workflow completion using logs
        self.logger.info("\n=== Step 8: Wait for Workflow Completion ===")
        if workflow_arn:
            self.logger.info(f"📋 Monitoring workflow: {workflow_arn}")
            result = self.run_cli_command(["logs", "--live", "--workflow", workflow_arn])
            run_id_match = re.search(r"Run:\s+([a-zA-Z0-9]+)", result["output"])
            run_id = run_id_match.group(1) if run_id_match else None
            if run_id:
                self.assert_workflow_run_after_test_start(run_id, workflow_arn)
            if result["success"]:
                self.logger.info("✅ Workflow completed successfully")
            else:
                self.logger.info(f"⚠️ Workflow failed or timed out: {result['output']}")
        else:
            self.logger.info("⚠️ Could not extract workflow ARN, skipping log wait")

        # Step 8.5: Validate table data
        self.logger.info("\n=== Step 8.5: Validate Table Data ===")
        sts = boto3.client("sts", region_name=region)
        caller = sts.get_caller_identity()
        role_arn = caller["Arn"].replace(":assumed-role/", ":role/").rsplit("/", 1)[0]
        lf = boto3.client("lakeformation", region_name=region)

        for grant_kwargs in [
            {"Resource": {"Database": {"Name": "covid19_db"}}, "Permissions": ["DESCRIBE"]},
            {"Resource": {"Table": {"DatabaseName": "covid19_db", "Name": "us_simplified"}}, "Permissions": ["DESCRIBE"]},
            {"Resource": {"TableWithColumns": {"DatabaseName": "covid19_db", "Name": "us_simplified", "ColumnWildcard": {}}}, "Permissions": ["SELECT"]},
        ]:
            try:
                lf.grant_permissions(
                    Principal={"DataLakePrincipalIdentifier": role_arn}, **grant_kwargs
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Could not grant LF permissions: {e}")

        # Resolve Athena output bucket from project connections
        athena_output = self._get_athena_output_location(pipeline_file, region)
        athena = boto3.client("athena", region_name=region)

        query_id = athena.start_query_execution(
            QueryString="SELECT COUNT(*) as row_count FROM covid19_db.us_simplified",
            ResultConfiguration={"OutputLocation": athena_output},
        )["QueryExecutionId"]
        time.sleep(5)
        result_data = athena.get_query_results(QueryExecutionId=query_id)
        row_count = int(result_data["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"])
        self.logger.info(f"📊 Table row count: {row_count:,}")
        assert row_count > 1000000, f"Expected >1M rows, got {row_count:,}"
        self.logger.info("✅ Row count validation passed")

        query_id = athena.start_query_execution(
            QueryString="SELECT * FROM covid19_db.us_simplified LIMIT 10",
            ResultConfiguration={"OutputLocation": athena_output},
        )["QueryExecutionId"]
        for _ in range(10):
            time.sleep(3)
            status = athena.get_query_execution(QueryExecutionId=query_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                break
        assert state == "SUCCEEDED", (
            f"Query failed: {status['QueryExecution']['Status'].get('StateChangeReason', state)}"
        )
        rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
        assert len(rows) >= 2, f"Expected at least 2 rows, got {len(rows)}"
        date_value = rows[1]["Data"][0].get("VarCharValue", "")
        assert re.match(r"\d{4}-\d{2}-\d{2}", date_value), f"Invalid date format: {date_value}"
        self.logger.info(f"✅ First record date: {date_value}")
        self.logger.info("✅ Table data validation passed")

        # Step 9: Run pipeline tests
        self.logger.info("\n=== Step 9: Run Pipeline Tests ===")
        result = self.run_cli_command(
            ["test", "--targets", "test", "--test-output", "console", "--manifest", pipeline_file]
        )
        assert result["success"], f"Pipeline tests failed: {result['output']}"
        self.logger.info("✅ Pipeline tests passed")

        # Step 10: Run destroy
        self.logger.info("\n=== Step 10: Run Destroy ===")
        result = self.run_cli_command(
            ["destroy", "--manifest", pipeline_file, "--targets", "test", "--force"]
        )
        assert result["success"], f"Destroy command must succeed: {result['output']}"
        self.logger.info("✅ Destroy command successful")

        # Step 11: Verify resources are gone
        self.logger.info("\n=== Step 11: Verify Resources Deleted ===")
        qs_client = boto3.client("quicksight", region_name=region)
        prefix = "deployed-test-covid-"

        remaining_dashboards = [
            d for d in qs_client.list_dashboards(AwsAccountId=account_id).get("DashboardSummaryList", [])
            if d["DashboardId"].startswith(prefix)
        ]
        assert remaining_dashboards == [], f"QuickSight dashboards still exist: {remaining_dashboards}"
        self.logger.info("✅ QuickSight dashboards deleted")

        remaining_datasets = [
            d for d in qs_client.list_data_sets(AwsAccountId=account_id).get("DataSetSummaries", [])
            if d["DataSetId"].startswith(prefix)
        ]
        assert remaining_datasets == [], f"QuickSight datasets still exist: {remaining_datasets}"
        self.logger.info("✅ QuickSight datasets deleted")

        remaining_sources = [
            s for s in qs_client.list_data_sources(AwsAccountId=account_id).get("DataSources", [])
            if s["DataSourceId"].startswith(prefix)
        ]
        assert remaining_sources == [], f"QuickSight data sources still exist: {remaining_sources}"
        self.logger.info("✅ QuickSight data sources deleted")

        glue_client = boto3.client("glue", region_name=region)
        for job_name in ["setup-covid-db-job", "summary-glue-job", "set-permission-check-job"]:
            try:
                glue_client.get_job(JobName=job_name)
                assert False, f"Glue job '{job_name}' still exists after destroy"
            except glue_client.exceptions.EntityNotFoundException:
                self.logger.info(f"✅ Glue job '{job_name}' deleted")

        from smus_cicd.helpers.airflow_serverless import generate_workflow_name, list_workflows
        from smus_cicd.application.application_manifest import ApplicationManifest

        manifest_obj = ApplicationManifest.from_file(pipeline_file)
        test_stage = manifest_obj.stages["test"]
        wf_name = generate_workflow_name(
            bundle_name=manifest_obj.application_name,
            project_name=test_stage.project.name,
            dag_name=workflow_name,
        )
        remaining_wf = [wf for wf in list_workflows(region=region) if wf["name"] == wf_name]
        assert remaining_wf == [], f"Airflow workflow '{wf_name}' still exists: {remaining_wf}"
        self.logger.info(f"✅ Airflow workflow '{wf_name}' deleted")

        from smus_cicd.helpers.datazone import get_domain_from_target_config, get_project_id_by_name

        try:
            domain_id, _ = get_domain_from_target_config(test_stage)
            project_id = get_project_id_by_name(
                test_stage.project.name, domain_id, test_stage.domain.region
            )
            assert project_id is not None, "DataZone project should still exist (project.create=false)"
            self.logger.info("✅ DataZone project still exists (project.create=false)")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not verify DataZone project: {e}")

        # Step 12: Idempotency check
        self.logger.info("\n=== Step 12: Idempotency Check ===")
        result2 = self.run_cli_command(
            ["destroy", "--manifest", pipeline_file, "--targets", "test", "--force", "--output", "JSON"]
        )
        assert result2["success"], f"Second destroy must succeed (idempotent): {result2['output']}"
        output = result2["output"]
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0:
            data = json.loads(output[json_start:json_end])
            error_results = [
                r for results in data.get("stages", {}).values() for r in results if r["status"] == "error"
            ]
            assert error_results == [], f"Second destroy should have no errors: {error_results}"
            self.logger.info("✅ Idempotency check passed — second destroy has no errors")

        self.logger.info("✅ Dashboard-Glue-Quick workflow test completed successfully")

    def _get_athena_output_location(self, pipeline_file: str, region: str) -> str:
        """Resolve Athena output S3 location from project connections."""
        try:
            from smus_cicd.application.application_manifest import ApplicationManifest
            from smus_cicd.helpers.connections import get_project_connections
            from smus_cicd.helpers.datazone import get_domain_from_target_config, get_project_id_by_name

            manifest_obj = ApplicationManifest.from_file(pipeline_file)
            test_stage = manifest_obj.stages["test"]
            domain_id, _ = get_domain_from_target_config(test_stage)
            project_id = get_project_id_by_name(test_stage.project.name, domain_id, region)
            connections = get_project_connections(project_id=project_id, domain_id=domain_id, region=region)
            s3_shared = connections.get("default.s3_shared", {})
            s3_uri = s3_shared.get("s3Uri", "").rstrip("/")
            if s3_uri:
                return f"{s3_uri}/athena-results/"
        except Exception as e:
            self.logger.warning(f"⚠️ Could not resolve Athena output from connections: {e}")

        # Fallback: construct from account/region
        account_id = _get_account_id()
        return f"s3://amazon-sagemaker-{account_id}-{region}-*/athena-results/"

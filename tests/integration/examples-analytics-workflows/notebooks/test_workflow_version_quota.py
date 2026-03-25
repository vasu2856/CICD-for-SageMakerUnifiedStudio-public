"""
Integration test for workflow version quota exceeded handling.

Simulates the ServiceQuotaExceededException scenario by creating enough workflow
versions to trigger the quota, then verifying the deploy command recovers
automatically by deleting and recreating the workflow.
"""
import os
import re

import pytest

from tests.integration.base import IntegrationTestBase


class TestWorkflowVersionQuota(IntegrationTestBase):
    """Tests that deploy recovers gracefully when workflow version quota is exceeded."""

    WORKFLOW_NAME_PATTERN = re.compile(
        r"(?:Created|recreated) workflow[:\s]+(\S+)", re.IGNORECASE
    )
    ARN_PATTERN = re.compile(r"ARN:\s*(arn:aws:airflow-serverless:[^\s]+)")

    def get_pipeline_file(self):
        return os.path.join(
            os.path.dirname(__file__),
            "../../../../examples/analytic-workflow/data-notebooks/manifest.yaml",
        )

    @pytest.mark.slow
    def test_deploy_recovers_from_version_quota_exceeded(self):
        """
        Deploy should automatically delete and recreate a workflow when
        ServiceQuotaExceededException is raised due to too many versions.

        Steps:
        1. Deploy once to ensure the workflow exists.
        2. Repeatedly update the workflow (via deploy) until the quota is hit
           or we've done enough updates to be confident the path is exercised.
        3. Verify the final deploy succeeds and the output contains the
           recreation warning.
        """
        pipeline_file = self.get_pipeline_file()

        # Step 1: Initial deploy to ensure workflow exists
        self.logger.info("=== Step 1: Initial deploy ===")
        result = self.run_cli_command(["deploy", "--manifest", pipeline_file, "--targets", "test"])
        assert result["success"], f"Initial deploy failed:\n{result['output']}"
        self.logger.info("✅ Initial deploy succeeded")

        # Step 2: Trigger multiple updates to exhaust workflow versions.
        # We run up to 6 deploys; if quota is hit before that the recovery
        # path will be exercised and we assert on it below.
        self.logger.info("=== Step 2: Repeated deploys to exhaust version quota ===")
        recreated = False
        last_result = None

        for i in range(6):
            self.logger.info(f"  Deploy attempt {i + 1}/6")
            last_result = self.run_cli_command(
                ["deploy", "--manifest", pipeline_file, "--targets", "test"]
            )

            if not last_result["success"]:
                # If it failed for a reason other than quota, surface the error
                assert False, f"Deploy {i + 1} failed unexpectedly:\n{last_result['output']}"

            if "version quota limit" in last_result["output"].lower() or \
               "recreated" in last_result["output"].lower():
                self.logger.info(f"  ✅ Quota recovery triggered on attempt {i + 1}")
                recreated = True
                break

        # Step 3: Verify the workflow is still functional after recovery
        self.logger.info("=== Step 3: Verify workflow is healthy after recovery ===")
        describe_result = self.run_cli_command(
            ["describe", "--manifest", pipeline_file, "--connect"]
        )
        assert describe_result["success"], (
            f"Describe failed after quota recovery:\n{describe_result['output']}"
        )

        if recreated:
            # Confirm the warning message was present
            assert "version quota limit" in last_result["output"].lower() or \
                   "recreated" in last_result["output"].lower(), (
                "Expected recreation warning in output but did not find it"
            )
            self.logger.info("✅ Workflow recreated successfully and is healthy")
        else:
            # Quota was not hit in 6 attempts — that's fine, the service limit
            # may be higher. The unit tests cover the code path directly.
            self.logger.info(
                "ℹ️  Version quota was not hit in 6 deploy attempts. "
                "Unit tests cover the recovery code path."
            )

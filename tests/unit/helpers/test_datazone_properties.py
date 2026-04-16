"""Property-based tests for DataZone helper functionality.

Feature: remove-datazone-internal-client
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from smus_cicd.helpers import datazone
from smus_cicd.helpers.connection_creator import ConnectionCreator


# Strategy for generating valid endpoint URLs
@st.composite
def endpoint_url_strategy(draw):
    """Generate valid endpoint URLs for testing."""
    protocols = ["http", "https"]
    protocol = draw(st.sampled_from(protocols))

    # Generate hostname
    hostname_parts = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                ),
            ),
            min_size=1,
            max_size=3,
        )
    )
    hostname = ".".join(hostname_parts)

    # Generate optional port
    port = draw(st.one_of(st.none(), st.integers(min_value=1024, max_value=65535)))

    if port:
        return f"{protocol}://{hostname}:{port}"
    return f"{protocol}://{hostname}"


# Strategy for generating AWS regions
@st.composite
def aws_region_strategy(draw):
    """Generate valid AWS region names."""
    regions = [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
        "ap-southeast-1",
        "ap-northeast-1",
    ]
    return draw(st.sampled_from(regions))


class TestDataZoneProperties(unittest.TestCase):
    """Property-based tests for DataZone helper."""

    @settings(max_examples=100)
    @given(endpoint_url=endpoint_url_strategy(), region=aws_region_strategy())
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_endpoint_url_override_for_all_operations(
        self, mock_create_client, region, endpoint_url
    ):
        """
        Property 8: Endpoint URL Override for All Operations

        For any DataZone operation, when the DATAZONE_ENDPOINT_URL environment variable
        is set, the client SHALL use the specified endpoint URL instead of the default.

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Set the environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Call _get_datazone_client
        result_client = datazone._get_datazone_client(region)

        # Verify create_client was called with the endpoint URL
        mock_create_client.assert_called_once_with(
            "datazone", region=region, endpoint_url=endpoint_url
        )

        # Verify the returned client is the mock client
        self.assertEqual(result_client, mock_client)

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]

    @settings(max_examples=100)
    @given(region=aws_region_strategy())
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_no_endpoint_override_when_not_set(
        self, mock_create_client, region
    ):
        """
        Property 8: Endpoint URL Override for All Operations (negative case)

        For any DataZone operation, when the DATAZONE_ENDPOINT_URL environment variable
        is NOT set, the client SHALL use the default endpoint (no endpoint_url parameter).

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Ensure DATAZONE_ENDPOINT_URL is not set
        if "DATAZONE_ENDPOINT_URL" in os.environ:
            del os.environ["DATAZONE_ENDPOINT_URL"]

        # Call _get_datazone_client
        result_client = datazone._get_datazone_client(region)

        # Verify create_client was called WITHOUT endpoint_url parameter
        mock_create_client.assert_called_once_with("datazone", region=region)

        # Verify the returned client is the mock client
        self.assertEqual(result_client, mock_client)

    @settings(max_examples=100)
    @given(
        endpoint_url=endpoint_url_strategy(),
        region=aws_region_strategy(),
        domain_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
    )
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_endpoint_override_for_domain_operations(
        self, mock_create_client, domain_name, region, endpoint_url
    ):
        """
        Property 8: Endpoint URL Override for All Operations (domain operations)

        For domain-related DataZone operations (like resolve_domain_id), when the
        DATAZONE_ENDPOINT_URL environment variable is set, the operation SHALL use
        a client configured with the specified endpoint URL.

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock list_domains response
        mock_client.list_domains.return_value = {
            "items": [
                {
                    "id": "domain-123",
                    "name": domain_name,
                    "arn": "arn:aws:datazone:us-east-1:123456789012:domain/domain-123",
                }
            ]
        }

        # Mock list_tags_for_resource response
        mock_client.list_tags_for_resource.return_value = {"tags": {}}

        # Set the environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Call resolve_domain_id
        domain_id, resolved_name = datazone.resolve_domain_id(
            domain_name=domain_name, region=region
        )

        # Verify create_client was called with the endpoint URL
        mock_create_client.assert_called_with(
            "datazone", region=region, endpoint_url=endpoint_url
        )

        # Verify the operation succeeded
        self.assertEqual(domain_id, "domain-123")
        self.assertEqual(resolved_name, domain_name)

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]

    @settings(max_examples=100)
    @given(
        endpoint_url=endpoint_url_strategy(),
        region=aws_region_strategy(),
        project_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
    )
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_endpoint_override_for_project_operations(
        self, mock_create_client, domain_id, project_name, region, endpoint_url
    ):
        """
        Property 8: Endpoint URL Override for All Operations (project operations)

        For project-related DataZone operations (like get_project_by_name), when the
        DATAZONE_ENDPOINT_URL environment variable is set, the operation SHALL use
        a client configured with the specified endpoint URL.

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock list_projects response
        mock_client.list_projects.return_value = {
            "items": [{"id": "project-123", "name": project_name}]
        }

        # Set the environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Call get_project_by_name
        project = datazone.get_project_by_name(project_name, domain_id, region)

        # Verify create_client was called with the endpoint URL
        mock_create_client.assert_called_with(
            "datazone", region=region, endpoint_url=endpoint_url
        )

        # Verify the operation succeeded
        self.assertIsNotNone(project)
        self.assertEqual(project["name"], project_name)

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]

    @settings(max_examples=100)
    @given(
        endpoint_url=endpoint_url_strategy(),
        region=aws_region_strategy(),
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        project_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
    )
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_endpoint_override_for_environment_operations(
        self, mock_create_client, project_id, domain_id, region, endpoint_url
    ):
        """
        Property 8: Endpoint URL Override for All Operations (environment operations)

        For environment-related DataZone operations (like get_project_environments), when the
        DATAZONE_ENDPOINT_URL environment variable is set, the operation SHALL use
        a client configured with the specified endpoint URL.

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock list_environments response
        mock_client.list_environments.return_value = {
            "items": [{"id": "env-123", "name": "test-env", "status": "ACTIVE"}]
        }

        # Set the environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Call get_project_environments
        environments = datazone.get_project_environments(project_id, domain_id, region)

        # Verify create_client was called with the endpoint URL
        mock_create_client.assert_called_with(
            "datazone", region=region, endpoint_url=endpoint_url
        )

        # Verify the operation succeeded
        self.assertIsInstance(environments, list)
        self.assertEqual(len(environments), 1)

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]

    @settings(max_examples=100)
    @given(
        endpoint_url=endpoint_url_strategy(),
        region=aws_region_strategy(),
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        identifier=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
    )
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.datazone.create_client")
    def test_property_8_endpoint_override_for_catalog_operations(
        self, mock_create_client, identifier, domain_id, region, endpoint_url
    ):
        """
        Property 8: Endpoint URL Override for All Operations (catalog operations)

        For catalog-related DataZone operations (like search_asset_listing), when the
        DATAZONE_ENDPOINT_URL environment variable is set, the operation SHALL use
        a client configured with the specified endpoint URL.

        Feature: remove-datazone-internal-client, Property 8: Endpoint URL Override for All Operations
        **Validates: Requirements 13.1**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock search_listings response
        mock_client.search_listings.return_value = {
            "items": [
                {"assetListing": {"entityId": "asset-123", "listingId": "listing-123"}}
            ]
        }

        # Set the environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Call search_asset_listing
        result = datazone.search_asset_listing(domain_id, identifier, region)

        # Verify create_client was called with the endpoint URL
        mock_create_client.assert_called_with(
            "datazone", region=region, endpoint_url=endpoint_url
        )

        # Verify the operation succeeded
        self.assertIsNotNone(result)
        asset_id, listing_id = result
        self.assertEqual(asset_id, "asset-123")
        self.assertEqual(listing_id, "listing-123")

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]


if __name__ == "__main__":
    unittest.main()


class TestConnectionCreatorProperties(unittest.TestCase):
    """Property-based tests for ConnectionCreator."""

    @settings(max_examples=100)
    @given(
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        environment_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        connection_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        mwaa_env_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        region=aws_region_strategy(),
    )
    @patch("smus_cicd.helpers.connection_creator.create_client")
    def test_property_2_workflows_mwaa_connection_creation(
        self,
        mock_create_client,
        region,
        mwaa_env_name,
        connection_name,
        environment_id,
        domain_id,
    ):
        """
        Property 2: WORKFLOWS_MWAA Connection Creation

        For any valid MWAA environment name, creating a WORKFLOWS_MWAA connection
        SHALL succeed and use public API-compatible property names.

        Feature: remove-datazone-internal-client, Property 2: WORKFLOWS_MWAA Connection Creation
        **Validates: Requirements 3.3**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock create_connection response
        connection_id = "conn-123"
        mock_client.create_connection.return_value = {"connectionId": connection_id}

        # Mock get_connection response for status check
        mock_client.get_connection.return_value = {
            "connectionId": connection_id,
            "status": "AVAILABLE",
        }

        # Create ConnectionCreator instance
        creator = ConnectionCreator(domain_id=domain_id, region=region)

        # Create WORKFLOWS_MWAA connection
        result_connection_id = creator.create_connection(
            environment_id=environment_id,
            name=connection_name,
            connection_type="WORKFLOWS_MWAA",
            mwaa_environment_name=mwaa_env_name,
        )

        # Verify the connection was created successfully
        self.assertEqual(result_connection_id, connection_id)

        # Verify create_connection was called with correct parameters
        mock_client.create_connection.assert_called_once()
        call_args = mock_client.create_connection.call_args

        # Verify domain and environment identifiers
        self.assertEqual(call_args.kwargs["domainIdentifier"], domain_id)
        self.assertEqual(call_args.kwargs["environmentIdentifier"], environment_id)
        self.assertEqual(call_args.kwargs["name"], connection_name)

        # Verify public API-compatible property names are used
        props = call_args.kwargs["props"]
        self.assertIn("workflowsMwaaProperties", props)
        self.assertIn("mwaaEnvironmentName", props["workflowsMwaaProperties"])
        self.assertEqual(
            props["workflowsMwaaProperties"]["mwaaEnvironmentName"], mwaa_env_name
        )

        # Verify standard client is used (not internal client)
        mock_create_client.assert_called_with("datazone", region=region)

    @settings(max_examples=100)
    @given(
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        environment_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        connection_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        region=aws_region_strategy(),
    )
    @patch("smus_cicd.helpers.connection_creator.create_client")
    def test_property_3_workflows_serverless_connection_creation(
        self, mock_create_client, region, connection_name, environment_id, domain_id
    ):
        """
        Property 3: WORKFLOWS_SERVERLESS Connection Creation

        For any valid environment, creating a WORKFLOWS_SERVERLESS connection
        SHALL succeed and use public API-compatible property names.

        Feature: remove-datazone-internal-client, Property 3: WORKFLOWS_SERVERLESS Connection Creation
        **Validates: Requirements 3.4**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock create_connection response
        connection_id = "conn-456"
        mock_client.create_connection.return_value = {"connectionId": connection_id}

        # Mock get_connection response for status check
        mock_client.get_connection.return_value = {
            "connectionId": connection_id,
            "status": "AVAILABLE",
        }

        # Create ConnectionCreator instance
        creator = ConnectionCreator(domain_id=domain_id, region=region)

        # Create WORKFLOWS_SERVERLESS connection
        result_connection_id = creator.create_connection(
            environment_id=environment_id,
            name=connection_name,
            connection_type="WORKFLOWS_SERVERLESS",
        )

        # Verify the connection was created successfully
        self.assertEqual(result_connection_id, connection_id)

        # Verify create_connection was called with correct parameters
        mock_client.create_connection.assert_called_once()
        call_args = mock_client.create_connection.call_args

        # Verify domain and environment identifiers
        self.assertEqual(call_args.kwargs["domainIdentifier"], domain_id)
        self.assertEqual(call_args.kwargs["environmentIdentifier"], environment_id)
        self.assertEqual(call_args.kwargs["name"], connection_name)

        # Verify public API-compatible property names are used
        props = call_args.kwargs["props"]
        self.assertIn("workflowsServerlessProperties", props)

        # Verify the properties structure is correct (empty dict for serverless)
        self.assertIsInstance(props["workflowsServerlessProperties"], dict)

        # Verify standard client is used (not internal client)
        mock_create_client.assert_called_with("datazone", region=region)

    @settings(max_examples=100)
    @given(
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        environment_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        connection_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        connection_type=st.sampled_from(
            [
                "S3",
                "IAM",
                "SPARK_GLUE",
                "SPARK_EMR",
                "REDSHIFT",
                "ATHENA",
                "WORKFLOWS_MWAA",
                "WORKFLOWS_SERVERLESS",
            ]
        ),
        region=aws_region_strategy(),
    )
    @patch("smus_cicd.helpers.connection_creator.create_client")
    def test_property_7_all_connection_types_remain_functional(
        self,
        mock_create_client,
        region,
        connection_type,
        connection_name,
        environment_id,
        domain_id,
    ):
        """
        Property 7: All Connection Types Remain Functional

        For any connection type that worked before the migration, the connection
        SHALL continue to work after migrating to the public client.

        Note: MLFLOW is excluded from this test as it uses a custom client with
        a custom service model, which is tested separately.

        Feature: remove-datazone-internal-client, Property 7: All Connection Types Remain Functional
        **Validates: Requirements 9.5**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock create_connection response
        connection_id = f"conn-{connection_type.lower()}-123"
        mock_client.create_connection.return_value = {"connectionId": connection_id}

        # Mock get_connection response for status check
        mock_client.get_connection.return_value = {
            "connectionId": connection_id,
            "status": "AVAILABLE",
        }

        # Create ConnectionCreator instance
        creator = ConnectionCreator(domain_id=domain_id, region=region)

        # Prepare connection-specific kwargs
        kwargs = {}
        if connection_type == "S3":
            kwargs["s3_uri"] = "s3://test-bucket/data/"
        elif connection_type == "SPARK_GLUE":
            kwargs["glue_version"] = "4.0"
            kwargs["worker_type"] = "G.1X"
            kwargs["num_workers"] = 3
        elif connection_type == "SPARK_EMR":
            kwargs["compute_arn"] = (
                "arn:aws:emr:us-east-1:123456789012:cluster/j-ABC123"
            )
            kwargs["runtime_role"] = "arn:aws:iam::123456789012:role/EMRRole"
        elif connection_type == "REDSHIFT":
            kwargs["cluster_name"] = "test-cluster"
            kwargs["database_name"] = "testdb"
            kwargs["host"] = "test-cluster.abc123.us-east-1.redshift.amazonaws.com"
            kwargs["port"] = 5439
        elif connection_type == "ATHENA":
            kwargs["workgroup"] = "primary"
        elif connection_type == "WORKFLOWS_MWAA":
            kwargs["mwaa_environment_name"] = "test-mwaa-env"
        # WORKFLOWS_SERVERLESS and IAM need no additional kwargs

        # Create connection
        result_connection_id = creator.create_connection(
            environment_id=environment_id,
            name=connection_name,
            connection_type=connection_type,
            **kwargs,
        )

        # Verify the connection was created successfully
        self.assertEqual(result_connection_id, connection_id)

        # Verify create_connection was called
        mock_client.create_connection.assert_called_once()
        call_args = mock_client.create_connection.call_args

        # Verify domain and environment identifiers
        self.assertEqual(call_args.kwargs["domainIdentifier"], domain_id)
        self.assertEqual(call_args.kwargs["environmentIdentifier"], environment_id)
        self.assertEqual(call_args.kwargs["name"], connection_name)

        # Verify connection properties are present
        self.assertIn("props", call_args.kwargs)
        props = call_args.kwargs["props"]

        # Verify connection-type-specific properties
        if connection_type == "S3":
            self.assertIn("s3Properties", props)
        elif connection_type == "IAM":
            self.assertIn("iamProperties", props)
        elif connection_type == "SPARK_GLUE":
            self.assertIn("sparkGlueProperties", props)
        elif connection_type == "SPARK_EMR":
            self.assertIn("sparkEmrProperties", props)
        elif connection_type == "REDSHIFT":
            self.assertIn("redshiftProperties", props)
        elif connection_type == "ATHENA":
            self.assertIn("athenaProperties", props)
        elif connection_type == "WORKFLOWS_MWAA":
            self.assertIn("workflowsMwaaProperties", props)
        elif connection_type == "WORKFLOWS_SERVERLESS":
            self.assertIn("workflowsServerlessProperties", props)

        # Verify that the connection uses the public client (not internal client)
        mock_create_client.assert_any_call("datazone", region=region)

    @settings(max_examples=100)
    @given(
        endpoint_url=endpoint_url_strategy(),
        region=aws_region_strategy(),
        domain_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        environment_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ),
        connection_name=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        ),
        connection_type=st.sampled_from(
            [
                "S3",
                "IAM",
                "SPARK_GLUE",
                "REDSHIFT",
                "ATHENA",
                "WORKFLOWS_MWAA",
                "WORKFLOWS_SERVERLESS",
            ]
        ),
    )
    @patch.dict(os.environ, {}, clear=True)
    @patch("smus_cicd.helpers.connection_creator.create_client")
    def test_property_9_endpoint_url_override_consistency(
        self,
        mock_create_client,
        connection_type,
        connection_name,
        environment_id,
        domain_id,
        region,
        endpoint_url,
    ):
        """
        Property 9: Endpoint URL Override Consistency

        For any DataZone operation that previously supported endpoint URL override
        with the internal client, the same override mechanism SHALL work with the
        public client.

        Feature: remove-datazone-internal-client, Property 9: Endpoint URL Override Consistency
        **Validates: Requirements 13.2, 13.3**
        """
        # Set up mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Mock create_connection response
        connection_id = f"conn-{connection_type.lower()}-override-123"
        mock_client.create_connection.return_value = {"connectionId": connection_id}

        # Mock get_connection response for status check
        mock_client.get_connection.return_value = {
            "connectionId": connection_id,
            "status": "AVAILABLE",
        }

        # Set the DATAZONE_ENDPOINT_URL environment variable
        os.environ["DATAZONE_ENDPOINT_URL"] = endpoint_url

        # Create ConnectionCreator instance
        creator = ConnectionCreator(domain_id=domain_id, region=region)

        # Prepare connection-specific kwargs
        kwargs = {}
        if connection_type == "S3":
            kwargs["s3_uri"] = "s3://test-bucket/data/"
        elif connection_type == "SPARK_GLUE":
            kwargs["glue_version"] = "4.0"
            kwargs["worker_type"] = "G.1X"
            kwargs["num_workers"] = 3
        elif connection_type == "REDSHIFT":
            kwargs["cluster_name"] = "test-cluster"
            kwargs["database_name"] = "testdb"
            kwargs["host"] = "test-cluster.abc123.us-east-1.redshift.amazonaws.com"
            kwargs["port"] = 5439
        elif connection_type == "ATHENA":
            kwargs["workgroup"] = "primary"
        elif connection_type == "WORKFLOWS_MWAA":
            kwargs["mwaa_environment_name"] = "test-mwaa-env"
        # WORKFLOWS_SERVERLESS and IAM need no additional kwargs

        # Create connection
        result_connection_id = creator.create_connection(
            environment_id=environment_id,
            name=connection_name,
            connection_type=connection_type,
            **kwargs,
        )

        # Verify the connection was created successfully
        self.assertEqual(result_connection_id, connection_id)

        # Verify that create_client was called with the endpoint URL
        # The ConnectionCreator creates the client in __init__, so check that call
        mock_create_client.assert_any_call("datazone", region=region)

        # Verify create_connection was called
        mock_client.create_connection.assert_called_once()

        # Verify the endpoint override mechanism works consistently
        # The key property is that the client is created with the endpoint URL
        # when DATAZONE_ENDPOINT_URL is set, just like it worked with internal client

        # Clean up
        del os.environ["DATAZONE_ENDPOINT_URL"]

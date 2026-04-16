"""Centralized boto3 client creation helper."""

from typing import Any, Dict, Optional

import boto3
import botocore.config

from smus_cicd import __version__

_USER_AGENT_CONFIG = botocore.config.Config(
    user_agent_extra=f"smuscicd/{__version__}",
)


def create_client(
    service_name: str,
    connection_info: Optional[Dict[str, Any]] = None,
    region: Optional[str] = None,
):
    """Create a boto3 client with region determined from connection info or explicit region."""

    # Determine region based on connection info or explicit region
    client_region = region  # Default to provided region

    if connection_info and not client_region:
        # Extract region from common physicalEndpoints pattern
        physical_endpoints = connection_info.get("physicalEndpoints", [])
        if physical_endpoints and len(physical_endpoints) > 0:
            aws_location = physical_endpoints[0].get("awsLocation", {})
            client_region = aws_location.get("awsRegion")

    # Require explicit region - no fallback
    if not client_region:
        raise ValueError(
            "Region must be provided either explicitly or through connection info"
        )

    return boto3.client(
        service_name, region_name=client_region, config=_USER_AGENT_CONFIG
    )


def get_region_from_connection(connection_info: Dict[str, Any]) -> Optional[str]:
    """Extract region from connection information."""
    physical_endpoints = connection_info.get("physicalEndpoints", [])
    if physical_endpoints and len(physical_endpoints) > 0:
        aws_location = physical_endpoints[0].get("awsLocation", {})
        return aws_location.get("awsRegion")

    return None

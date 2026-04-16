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
    **kwargs: Any,
):
    """Create a boto3 client with consistent user-agent and optional region.

    Parameters
    ----------
    service_name : str
        AWS service name (e.g. ``"s3"``, ``"sts"``).
    connection_info : dict, optional
        DataZone connection dict; region is extracted from
        ``physicalEndpoints[0].awsLocation.awsRegion`` when *region* is not
        given.
    region : str, optional
        Explicit AWS region.  When *None* and *connection_info* does not
        provide a region the client is created without ``region_name``
        (useful for global services like STS).
    **kwargs
        Extra keyword arguments forwarded to ``boto3.client`` (e.g.
        ``endpoint_url``).
    """
    client_region = region

    if connection_info and not client_region:
        physical_endpoints = connection_info.get("physicalEndpoints", [])
        if physical_endpoints and len(physical_endpoints) > 0:
            aws_location = physical_endpoints[0].get("awsLocation", {})
            client_region = aws_location.get("awsRegion")

    client_kwargs: Dict[str, Any] = {"config": _USER_AGENT_CONFIG, **kwargs}
    if client_region:
        client_kwargs["region_name"] = client_region

    return boto3.client(service_name, **client_kwargs)


def get_region_from_connection(connection_info: Dict[str, Any]) -> Optional[str]:
    """Extract region from connection information."""
    physical_endpoints = connection_info.get("physicalEndpoints", [])
    if physical_endpoints and len(physical_endpoints) > 0:
        aws_location = physical_endpoints[0].get("awsLocation", {})
        return aws_location.get("awsRegion")

    return None

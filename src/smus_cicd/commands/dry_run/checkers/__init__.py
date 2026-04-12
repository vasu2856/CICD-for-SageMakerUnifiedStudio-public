"""Checker protocol and base types for dry-run validation phases."""

from __future__ import annotations

from typing import List, Protocol

from smus_cicd.commands.dry_run.models import DryRunContext, Finding


class Checker(Protocol):
    """Protocol that all dry-run phase checkers must implement."""

    def check(self, context: DryRunContext) -> List[Finding]: ...  # noqa: E704


def is_catalog_disabled(context: DryRunContext) -> bool:
    """Return True if catalog import is disabled in the deployment configuration.

    Mirrors the check in ``deploy.py::_import_catalog_from_bundle``:
    ``target_config.deployment_configuration.catalog.get("disable", False)``
    """
    target = context.target_config
    if not target:
        return False
    dep_cfg = getattr(target, "deployment_configuration", None)
    if not dep_cfg:
        return False
    catalog_cfg = getattr(dep_cfg, "catalog", None)
    if not catalog_cfg:
        return False
    if isinstance(catalog_cfg, dict):
        return catalog_cfg.get("disable", False)
    return getattr(catalog_cfg, "disable", False)


def get_project_connections(context: DryRunContext, region: str) -> dict:
    """Fetch project connections from DataZone.

    Returns the connections dict.
    Raises ValueError if no project name is available.
    Raises RuntimeError if the API returns an error or no connections.
    """
    config = context.config or {}
    project_name = config.get("project_name")
    if not project_name:
        project_cfg = getattr(context.target_config, "project", None)
        project_name = getattr(project_cfg, "name", None) if project_cfg else None

    if not project_name:
        raise ValueError("No project_name available to resolve connections")

    from smus_cicd.helpers.utils import get_datazone_project_info

    info = get_datazone_project_info(project_name, config)
    if "error" in info:
        raise RuntimeError(
            f"Failed to resolve project connections for '{project_name}': {info['error']}"
        )
    connections = info.get("connections")
    if connections is None:
        raise RuntimeError(f"No connections found for project '{project_name}'")
    return connections

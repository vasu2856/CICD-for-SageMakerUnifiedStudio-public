"""Bootstrap action simulation checker (Phase 11).

Lists each bootstrap action that would execute, including type and
parameters.  References bootstrap action types from
``docs/bootstrap-actions.md`` and uses the action registry from
``bootstrap/action_registry.py`` to verify that each action type has a
registered handler.

- If no bootstrap actions are configured, returns OK with
  "no bootstrap actions configured".
- For each action, reports OK with the action type and key parameters.
- If an action type has no registered handler, reports WARNING.

Requirements: 5.6
"""

from __future__ import annotations

import logging
from typing import List

from smus_cicd.bootstrap.action_registry import registry
from smus_cicd.commands.dry_run.models import DryRunContext, Finding, Severity

logger = logging.getLogger(__name__)


class BootstrapChecker:
    """Lists bootstrap actions that would execute during deployment."""

    def check(self, context: DryRunContext) -> List[Finding]:
        findings: List[Finding] = []

        bootstrap = getattr(context.target_config, "bootstrap", None)
        actions = getattr(bootstrap, "actions", None) or [] if bootstrap else []

        if not actions:
            findings.append(
                Finding(
                    severity=Severity.OK,
                    message="No bootstrap actions configured.",
                    service="bootstrap",
                )
            )
            return findings

        for action in actions:
            action_type = getattr(action, "type", str(action))
            parameters = getattr(action, "parameters", {}) or {}

            # Check whether the action type has a registered handler
            has_handler = self._has_handler(action_type)

            param_keys = sorted(parameters.keys()) if parameters else []
            param_summary = ", ".join(f"{k}={parameters[k]!r}" for k in param_keys)

            if has_handler:
                message = f"Bootstrap action '{action_type}'"
                if param_summary:
                    message += f": {param_summary}"
                findings.append(
                    Finding(
                        severity=Severity.OK,
                        message=message,
                        resource=action_type,
                        service="bootstrap",
                        details={
                            "type": action_type,
                            "parameters": parameters,
                        },
                    )
                )
            else:
                findings.append(
                    Finding(
                        severity=Severity.ERROR,
                        message=(
                            f"Bootstrap action '{action_type}': "
                            f"no registered handler found"
                        ),
                        resource=action_type,
                        service="bootstrap",
                        details={
                            "type": action_type,
                            "parameters": parameters,
                        },
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_handler(action_type: str) -> bool:
        """Return True if the action registry has a handler for *action_type*."""
        try:
            registry.get_handler(action_type)
            return True
        except (ValueError, KeyError):
            return False

"""Destroy command for SMUS CI/CD CLI.

Implements the inverse of deploy: reads a manifest, discovers all deployed
resources for the targeted stage(s), validates for collisions, then deletes
everything in a safe dependency order.

The heavy lifting is split across helper modules:
  - destroy_models.py:    Data models and DESTROY_SUPPORTED_RESOURCE_TYPES
  - destroy_validator.py: Validation phase (_validate_stage and pure helpers)
  - destroy_executor.py:  Destruction phase (_destroy_stage)
"""

import json
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.prompt import Confirm

from ..application import ApplicationManifest
from ..helpers.destroy_executor import _destroy_stage
from ..helpers.destroy_models import (
    DESTROY_SUPPORTED_RESOURCE_TYPES,
    ResourceResult,
    ResourceToDelete,
    S3Target,
    ValidationResult,
)
from ..helpers.destroy_validator import (
    _discover_workflow_created_resources,
    _resolve_resource_prefix,
    _resolve_s3_targets,
    _validate_stage,
)

console = Console()
err_console = Console(stderr=True)


def destroy_command(
    manifest: str = "manifest.yaml",
    targets: str = "",
    force: bool = False,
    output: str = "TEXT",
) -> None:
    """
    Destroy all resources deployed by the manifest.

    Runs a full validation cycle across all targeted stages before any
    destructive action. Prints a destruction plan and prompts for confirmation
    unless --force is set.

    Example: aws-smus-cicd-cli destroy --manifest manifest.yaml --targets dev --force
    """
    is_json = output.upper() == "JSON"

    def _out(msg: str) -> None:
        """Print to stdout (TEXT) or stderr (JSON)."""
        if is_json:
            err_console.print(msg)
        else:
            console.print(msg)

    # -----------------------------------------------------------------------
    # 1. Parse manifest
    # -----------------------------------------------------------------------
    try:
        app_manifest = ApplicationManifest.from_file(manifest)
    except Exception as e:
        _out(f"[red]Error parsing manifest '{manifest}': {e}[/red]")
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 2. Resolve target list
    # -----------------------------------------------------------------------
    if not targets or not targets.strip():
        valid_names = ", ".join(app_manifest.stages.keys())
        _out(f"[red]--targets is required. Available stages: {valid_names}[/red]")
        raise typer.Exit(1)

    target_list = [t.strip() for t in targets.split(",")]

    invalid = [t for t in target_list if t not in app_manifest.stages]
    if invalid:
        valid_names = ", ".join(app_manifest.stages.keys())
        _out(
            f"[red]Invalid stage name(s): {', '.join(invalid)}. "
            f"Valid stages: {valid_names}[/red]"
        )
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 3. Skip stages with absent/empty deployment_configuration
    # -----------------------------------------------------------------------
    active_targets: List[str] = []
    for stage_name in target_list:
        sc = app_manifest.stages[stage_name]
        if not sc.deployment_configuration:
            _out(
                f"[yellow]⚠️  Stage '{stage_name}' has no deployment_configuration "
                "— skipping[/yellow]"
            )
            continue
        active_targets.append(stage_name)

    if not active_targets:
        _out("[yellow]No stages with deployment_configuration to destroy.[/yellow]")
        raise typer.Exit(0)

    # -----------------------------------------------------------------------
    # 4. Validation phase — ALL stages before any destructive action
    # -----------------------------------------------------------------------
    _out(f"\n[blue]🔍 Validating {len(active_targets)} stage(s)...[/blue]")

    validation_results: Dict[str, ValidationResult] = {}
    for stage_name in active_targets:
        sc = app_manifest.stages[stage_name]
        region = sc.domain.region
        _out(f"  Validating stage '{stage_name}'...")
        try:
            vr = _validate_stage(stage_name, sc, app_manifest, region)
        except Exception as e:
            vr = ValidationResult(
                errors=[f"[{stage_name}] Unexpected validation error: {e}"],
                warnings=[],
                resources=[],
                active_workflow_runs={},
            )
        validation_results[stage_name] = vr

        for warning in vr.warnings:
            _out(f"  [yellow]⚠️  {_escape_markup(warning)}[/yellow]")

    # -----------------------------------------------------------------------
    # 5. Check for validation errors
    # -----------------------------------------------------------------------
    all_errors: List[str] = []
    for vr in validation_results.values():
        all_errors.extend(vr.errors)

    if all_errors:
        _out("\n[red]❌ Validation errors found — aborting before any deletion:[/red]")
        for err in all_errors:
            _out(f"  [red]• {_escape_markup(err)}[/red]")
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # 6. Print destruction plan
    # -----------------------------------------------------------------------
    _out("\n[blue]📋 Destruction plan:[/blue]")
    total_resources = 0
    for stage_name in active_targets:
        vr = validation_results[stage_name]
        _out(f"\n  [bold]Stage: {stage_name}[/bold]")
        by_type: Dict[str, List[ResourceToDelete]] = {}
        for r in vr.resources:
            by_type.setdefault(r.resource_type, []).append(r)

        if not by_type:
            _out("    (no resources found)")
        else:
            for rtype, rlist in by_type.items():
                _out(f"    {rtype}:")
                for r in rlist:
                    _out(f"      - {r.resource_id}")
                    total_resources += 1

        if vr.active_workflow_runs:
            _out("    [yellow]Active workflow runs (will be terminated when workflow is deleted):[/yellow]")
            for wf_name, run_ids in vr.active_workflow_runs.items():
                _out(f"      {wf_name}: {run_ids}")

    _out(f"\n  Total resources to process: {total_resources}")

    _out(
        "\n[yellow]⚠️  WARNING: The destroy command deletes ALL resources listed "
        "above based on the manifest and workflow definitions. This includes "
        "resources that may have been created manually by users, not only those "
        "created by the CI/CD tool. Review the destruction plan carefully before "
        "confirming.[/yellow]"
    )

    # -----------------------------------------------------------------------
    # 7. Confirmation prompt (unless --force)
    # -----------------------------------------------------------------------
    if not force:
        if not is_json:
            console.print()
            console.print(
                "[yellow]⚠️  WARNING: This will permanently delete the above "
                "resources![/yellow]"
            )
            confirmed = Confirm.ask(
                "Are you sure you want to proceed with destruction?"
            )
            if not confirmed:
                console.print("Destruction cancelled.")
                raise typer.Exit(0)
        else:
            err_console.print(
                "[yellow]Use --force to skip confirmation in JSON output mode.[/yellow]"
            )
            raise typer.Exit(0)

    # -----------------------------------------------------------------------
    # 8. Destruction phase
    # -----------------------------------------------------------------------
    _out("\n[blue]🗑️  Starting destruction...[/blue]")

    all_results: Dict[str, List[ResourceResult]] = {}
    for stage_name in active_targets:
        sc = app_manifest.stages[stage_name]
        region = sc.domain.region
        vr = validation_results[stage_name]

        _out(f"\n[blue]  Stage: {stage_name}[/blue]")
        try:
            stage_results = _destroy_stage(
                stage_name=stage_name,
                stage_config=sc,
                manifest=app_manifest,
                validation_result=vr,
                region=region,
                output=output,
            )
        except Exception as e:
            _out(f"  [red]❌ Unexpected error destroying stage '{stage_name}': {e}[/red]")
            stage_results = [
                ResourceResult(
                    resource_type="stage", resource_id=stage_name,
                    status="error", message=str(e),
                )
            ]
        all_results[stage_name] = stage_results

    # -----------------------------------------------------------------------
    # 9. Summary
    # -----------------------------------------------------------------------
    has_errors = False

    if is_json:
        stages_output = {}
        for stage_name, stage_results in all_results.items():
            stages_output[stage_name] = [
                {
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "status": r.status,
                    "message": r.message,
                }
                for r in stage_results
            ]
            if any(r.status == "error" for r in stage_results):
                has_errors = True

        output_data = {
            "application_name": app_manifest.application_name,
            "targets": active_targets,
            "stages": stages_output,
        }
        print(json.dumps(output_data, indent=2))
    else:
        console.print("\n[blue]📊 Destruction Summary[/blue]")
        for stage_name, stage_results in all_results.items():
            counts = {"deleted": 0, "not_found": 0, "skipped": 0, "error": 0}
            for r in stage_results:
                if r.status in counts:
                    counts[r.status] += 1
                if r.status == "error":
                    has_errors = True

            console.print(
                f"  {stage_name}: "
                f"deleted={counts['deleted']} "
                f"not_found={counts['not_found']} "
                f"skipped={counts['skipped']} "
                f"error={counts['error']}"
            )

    if has_errors:
        raise typer.Exit(1)

"""Thin command-line entry points for public Verfeinert workflows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Mapping

import yaml

from verfeinert.core import CoreValidationError
from verfeinert.core import read_json
from verfeinert.core import read_yaml
from verfeinert.workflow import (
    WORKFLOW_CHECKPOINT_SCHEMA_VERSION,
    WORKFLOW_REPORT_SCHEMA_VERSION,
    WorkflowConfig,
    read_workflow_checkpoint_json,
    render_workflow_report_markdown,
    run_workflow,
)
from verfeinert.ansatz_analyzer.visualization import VisualizationDependencyError


class CliError(RuntimeError):
    """Raised for user-facing CLI input errors."""


CONFIG_ERROR_EXIT_CODE = 2
WORKFLOW_ERROR_EXIT_CODE = 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Verfeinert command-line interface."""
    parser = argparse.ArgumentParser(
        prog="verfeinert",
        description="Run reproducible Verfeinert workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a workflow config")
    validate_parser.add_argument(
        "config",
        help="path to a workflow YAML configuration (JSON is also accepted)",
    )
    validate_parser.add_argument("--output-root", default=None, help="override paths.output_root")

    run_parser = subparsers.add_parser("run", help="run a workflow config")
    run_parser.add_argument(
        "config",
        help="path to a workflow YAML configuration (JSON is also accepted)",
    )
    run_parser.add_argument("--output-root", default=None, help="override paths.output_root")

    resume_parser = subparsers.add_parser("resume", help="resume from a workflow checkpoint")
    resume_parser.add_argument(
        "checkpoint_or_run",
        help="path to a checkpoint JSON artifact or a run directory containing checkpoints/latest.json",
    )
    resume_parser.add_argument(
        "--config",
        default=None,
        help="path to a resume workflow YAML or JSON configuration",
    )
    resume_parser.add_argument("--output-root", default=None, help="override paths.output_root")

    inspect_parser = subparsers.add_parser("inspect", help="inspect a workflow artifact")
    inspect_parser.add_argument("artifact", help="path to a workflow report or checkpoint JSON")
    inspect_parser.add_argument(
        "--format",
        choices=("auto", "json", "markdown"),
        default="auto",
        help="output format for supported artifacts",
    )

    args = parser.parse_args(argv)
    if args.command == "validate":
        try:
            config = _load_workflow_config(args.config, output_root=args.output_root)
        except (CliError, CoreValidationError, ValueError) as exc:
            _print_error(exc)
            return CONFIG_ERROR_EXIT_CODE
        print(json.dumps(_validation_summary(config, config_path=args.config), sort_keys=True))
        return 0
    if args.command == "run":
        return _run_command(args.config, output_root=args.output_root)
    if args.command == "resume":
        return _resume_command(
            args.checkpoint_or_run,
            config_path=args.config,
            output_root=args.output_root,
        )
    if args.command == "inspect":
        try:
            text = _inspect_artifact(args.artifact, output_format=args.format)
        except (CliError, CoreValidationError, OSError, ValueError) as exc:
            _print_error(exc)
            return CONFIG_ERROR_EXIT_CODE
        print(text, end="" if text.endswith("\n") else "\n")
        return 0
    parser.error(f"unknown command: {args.command}")
    return CONFIG_ERROR_EXIT_CODE


def _run_command(config_path: str | Path, *, output_root: str | Path | None) -> int:
    try:
        result = _run_config(config_path, output_root=output_root)
    except VisualizationDependencyError as exc:
        print(
            "verfeinert: error: visualization extra is required for "
            f"requested visualization output: {exc}",
            file=sys.stderr,
        )
        return WORKFLOW_ERROR_EXIT_CODE
    except (CliError, CoreValidationError, ValueError) as exc:
        _print_error(exc)
        return WORKFLOW_ERROR_EXIT_CODE
    except Exception as exc:  # pragma: no cover - exercised by installed CLI users.
        print(
            f"verfeinert: workflow failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return WORKFLOW_ERROR_EXIT_CODE
    print(json.dumps(_result_summary(result), sort_keys=True))
    return 0


def _resume_command(
    checkpoint_or_run: str | Path,
    *,
    config_path: str | Path | None,
    output_root: str | Path | None,
) -> int:
    try:
        checkpoint_path = _resolve_checkpoint_source(checkpoint_or_run)
        if config_path is None:
            checkpoint = read_workflow_checkpoint_json(checkpoint_path)
            mapping = _resume_mapping_from_checkpoint(checkpoint)
        else:
            mapping = _load_config_mapping(config_path)
        mapping = _with_resume_checkpoint(mapping, checkpoint_path)
        mapping = _with_output_root(mapping, output_root)
        result = run_workflow(WorkflowConfig.from_mapping(mapping))
    except VisualizationDependencyError as exc:
        print(
            "verfeinert: error: visualization extra is required for "
            f"requested visualization output: {exc}",
            file=sys.stderr,
        )
        return WORKFLOW_ERROR_EXIT_CODE
    except (CliError, CoreValidationError, ValueError, OSError) as exc:
        _print_error(exc)
        return CONFIG_ERROR_EXIT_CODE
    except Exception as exc:  # pragma: no cover - exercised by installed CLI users.
        print(
            f"verfeinert: workflow failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return WORKFLOW_ERROR_EXIT_CODE
    print(json.dumps(_result_summary(result, resumed_from=checkpoint_path), sort_keys=True))
    return 0


def _run_config(config_path: str | Path, *, output_root: str | Path | None):
    config = _load_workflow_config(config_path, output_root=output_root)
    return run_workflow(config)


def _load_workflow_config(
    config_path: str | Path,
    *,
    output_root: str | Path | None,
) -> WorkflowConfig:
    return WorkflowConfig.from_mapping(_with_output_root(_load_config_mapping(config_path), output_root))


def _load_config_mapping(config_path: str | Path) -> dict[str, Any]:
    try:
        payload = read_yaml(config_path)
    except FileNotFoundError as exc:
        raise CliError(f"workflow config file not found: {config_path}") from exc
    except PermissionError as exc:
        raise CliError(f"workflow config file is not readable: {config_path}") from exc
    except OSError as exc:
        raise CliError(f"unable to read workflow config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CliError(f"unable to parse workflow config {config_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CliError("workflow config must be a mapping.")
    return dict(payload)


def _with_output_root(mapping: Mapping[str, Any], output_root: str | Path | None) -> dict[str, Any]:
    mapping = dict(mapping)
    if output_root is not None:
        paths = dict(mapping.get("paths", {}))
        paths["output_root"] = str(output_root)
        mapping["paths"] = paths
    return mapping


def _with_resume_checkpoint(
    mapping: Mapping[str, Any],
    checkpoint_path: str | Path,
) -> dict[str, Any]:
    mapping = dict(mapping)
    if "resume" in mapping:
        resume = dict(mapping.get("resume") or {})
        resume["checkpoint"] = str(checkpoint_path)
        mapping["resume"] = resume
        return mapping
    workflow = dict(mapping.get("workflow", {}))
    resume = dict(workflow.get("resume", {}))
    resume["checkpoint"] = str(checkpoint_path)
    workflow["resume"] = resume
    mapping["workflow"] = workflow
    return mapping


def _resolve_checkpoint_source(checkpoint_or_run: str | Path) -> Path:
    source = Path(checkpoint_or_run).expanduser()
    checkpoint_path = source / "checkpoints" / "latest.json" if source.is_dir() else source
    if not checkpoint_path.is_file():
        raise CliError(f"workflow checkpoint not found: {checkpoint_path}")
    return checkpoint_path


def _resume_mapping_from_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    workflow = dict(checkpoint.get("workflow", {}))
    snapshot = workflow.get("config")
    if not isinstance(snapshot, Mapping):
        raise CliError("workflow checkpoint does not contain a resumable config snapshot.")
    mapping = dict(snapshot)
    completed = set(str(stage) for stage in workflow.get("completed_stages", ()))
    stage_plan = dict(workflow.get("stage_plan", {}))
    snapshot_workflow = dict(mapping.get("workflow", {}))
    scientific = _remaining_operations(
        stage_plan.get("scientific", snapshot_workflow.get("scientific_execution", ())),
        completed,
    )
    postprocessing = _remaining_operations(
        stage_plan.get("postprocessing", snapshot_workflow.get("postprocessing", ())),
        completed,
    )
    snapshot_workflow["scientific_execution"] = list(scientific)
    snapshot_workflow["postprocessing"] = list(postprocessing)
    snapshot_workflow.pop("stages", None)
    mapping["workflow"] = snapshot_workflow
    mapping.pop("stages", None)
    return mapping


def _remaining_operations(value: object, completed: set[str]) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    return tuple(str(stage) for stage in value if str(stage) not in completed)


def _inspect_artifact(artifact: str | Path, *, output_format: str) -> str:
    path = Path(artifact).expanduser()
    try:
        document = read_json(path)
    except FileNotFoundError as exc:
        raise CliError(f"workflow artifact not found: {artifact}") from exc
    if not isinstance(document, Mapping):
        raise CliError("workflow artifact must be a JSON object.")
    schema_version = document.get("schema_version")
    if schema_version == WORKFLOW_REPORT_SCHEMA_VERSION:
        if output_format == "json":
            return json.dumps(document, indent=2, sort_keys=True) + "\n"
        return render_workflow_report_markdown(document)
    if schema_version == WORKFLOW_CHECKPOINT_SCHEMA_VERSION:
        checkpoint = read_workflow_checkpoint_json(path)
        return json.dumps(_checkpoint_summary(checkpoint, path=path), sort_keys=True) + "\n"
    raise CliError(f"unsupported workflow artifact schema: {schema_version!r}")


def _validation_summary(config: WorkflowConfig, *, config_path: str | Path) -> dict[str, Any]:
    return {
        "status": "valid",
        "terminal_status": "valid",
        "config_path": str(config_path),
        "run_id": config.run_id,
        "output_root": str(config.output_root),
        "scientific_execution": list(config.scientific_execution),
        "postprocessing": list(config.postprocessing),
        "checkpoint_enabled": config.checkpoint.enabled,
        "resume_checkpoint": config.resume.checkpoint,
    }


def _result_summary(result: Any, *, resumed_from: str | Path | None = None) -> dict[str, Any]:
    payload = dict(result.to_dict())
    payload["status"] = "completed"
    payload["terminal_status"] = "completed"
    if resumed_from is not None:
        payload["resumed_from"] = str(resumed_from)
    return payload


def _checkpoint_summary(checkpoint: Mapping[str, Any], *, path: str | Path) -> dict[str, Any]:
    workflow = dict(checkpoint.get("workflow", {}))
    refs = dict(dict(checkpoint.get("artifacts", {})).get("refs", {}))
    return {
        "status": "valid",
        "terminal_status": str(checkpoint.get("status", "unknown")),
        "schema_version": checkpoint.get("schema_version"),
        "path": str(path),
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "run_id": checkpoint.get("run_id"),
        "completed_stages": list(workflow.get("completed_stages", ())),
        "artifact_ref_kinds": sorted(str(key) for key in refs),
    }


def _print_error(exc: BaseException) -> None:
    print(f"verfeinert: error: {exc}", file=sys.stderr)


__all__ = ["CliError", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

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
from verfeinert.core import read_yaml
from verfeinert.workflow import WorkflowConfig, run_workflow


class CliError(RuntimeError):
    """Raised for user-facing CLI input errors."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Verfeinert command-line interface."""
    parser = argparse.ArgumentParser(prog="verfeinert", description="Run Verfeinert workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a workflow YAML config")
    run_parser.add_argument("config", help="path to a workflow YAML configuration")
    run_parser.add_argument("--output-root", default=None, help="override paths.output_root")

    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            result = _run_config(args.config, output_root=args.output_root)
        except (CliError, CoreValidationError, ValueError) as exc:
            print(f"verfeinert: error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), sort_keys=True))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


def _run_config(config_path: str | Path, *, output_root: str | Path | None):
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
    mapping = dict(payload)
    if output_root is not None:
        paths = dict(mapping.get("paths", {}))
        paths["output_root"] = str(output_root)
        mapping["paths"] = paths
    return run_workflow(WorkflowConfig.from_mapping(mapping))


__all__ = ["CliError", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

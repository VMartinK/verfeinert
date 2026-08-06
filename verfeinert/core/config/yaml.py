"""YAML configuration loading for Verfeinert run configs."""

from __future__ import annotations

from pathlib import Path

import yaml

from verfeinert.core.config.models import RunConfig
from verfeinert.core.validation import CoreValidationError


def load_run_config_yaml(path: str | Path) -> RunConfig:
    """Load a YAML run configuration into the validated Python model."""
    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        raise CoreValidationError("YAML configuration must not be empty.")
    if not isinstance(data, dict):
        raise CoreValidationError("YAML configuration must contain a mapping.")
    return RunConfig.from_mapping(data)


__all__ = ["load_run_config_yaml"]

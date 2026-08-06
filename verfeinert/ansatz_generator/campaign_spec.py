"""Lightweight campaign spec load/write/validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from verfeinert.core.io import read_json, read_yaml, to_json_safe, write_json, write_yaml

from .validation import GeneratorValidationError


def load_campaign_spec(path: str | Path) -> dict[str, Any]:
    """Load a campaign spec from JSON or YAML."""
    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Campaign spec not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".json":
        payload = read_json(source)
    elif suffix in {".yaml", ".yml"}:
        payload = read_yaml(source)
    else:
        raise GeneratorValidationError(f"Unsupported campaign spec extension: {suffix}")
    if not isinstance(payload, dict):
        raise GeneratorValidationError("Campaign spec file must contain a mapping/object.")
    return payload


def write_campaign_spec(path: str | Path, spec: dict[str, Any], *, overwrite: bool = False) -> Path:
    """Write a campaign spec as JSON or YAML."""
    validate_campaign_spec(spec)
    target = Path(path).expanduser()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Campaign spec already exists: {target}")
    suffix = target.suffix.lower()
    if suffix == ".json":
        return write_json(target, spec)
    if suffix in {".yaml", ".yml"}:
        return write_yaml(target, spec)
    raise GeneratorValidationError(f"Unsupported campaign spec extension: {suffix}")


def validate_campaign_spec(spec: dict[str, Any]) -> None:
    """Conservatively validate an analysis/generation campaign spec."""
    if not isinstance(spec, dict):
        raise TypeError("campaign spec must be a dictionary.")
    identity = spec.get("campaign_slug") or spec.get("slug") or spec.get("name")
    if not isinstance(identity, str) or not identity.strip():
        raise GeneratorValidationError("campaign spec requires campaign_slug, slug, or name.")
    layers = spec.get("layers", spec.get("analysis_layers"))
    if layers is not None:
        if not isinstance(layers, (list, tuple)) or not layers:
            raise GeneratorValidationError("layers/analysis_layers must be a non-empty list.")
        try:
            parsed_layers = tuple(int(layer) for layer in layers)
        except Exception as exc:
            raise GeneratorValidationError("layers/analysis_layers must contain integers.") from exc
        if any(layer <= 0 for layer in parsed_layers):
            raise GeneratorValidationError("layers/analysis_layers must contain positive integers.")
    indicators = (
        "templates",
        "parent_templates",
        "parents",
        "recipes",
        "mutation",
        "generation",
        "metrics",
        "analysis",
    )
    if not any(key in spec for key in indicators):
        raise GeneratorValidationError("campaign spec requires at least one analysis or generation section.")


def load_and_validate_campaign_spec(path: str | Path) -> dict[str, Any]:
    """Load and validate a campaign spec."""
    spec = load_campaign_spec(path)
    validate_campaign_spec(spec)
    return to_json_safe(spec)


__all__ = [
    "load_and_validate_campaign_spec",
    "load_campaign_spec",
    "validate_campaign_spec",
    "write_campaign_spec",
]

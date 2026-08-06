"""I/O helpers for canonical evolver input and state documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from verfeinert.core.io import read_json

from .validation import (
    validate_analysis_result_document,
    validate_candidate_document,
    validate_evolution_run_document,
    validate_staged_package_document,
)


def read_candidate_json(path: str | Path) -> dict[str, Any]:
    """Read and validate one canonical Candidate JSON document."""
    return validate_candidate_document(_read_mapping(path))


def read_staged_package_json(path: str | Path) -> dict[str, Any]:
    """Read and validate one canonical StagedPackage JSON document."""
    return validate_staged_package_document(_read_mapping(path))


def read_analysis_result_json(path: str | Path) -> dict[str, Any]:
    """Read and validate one canonical AnalysisResult JSON document."""
    return validate_analysis_result_document(_read_mapping(path))


def read_evolution_run_json(path: str | Path) -> dict[str, Any]:
    """Read and validate one canonical EvolutionRun JSON document."""
    return validate_evolution_run_document(_read_mapping(path))


def _read_mapping(path: str | Path) -> Mapping[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


__all__ = [
    "read_analysis_result_json",
    "read_candidate_json",
    "read_evolution_run_json",
    "read_staged_package_json",
]

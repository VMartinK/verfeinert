"""Export EvolutionRunState records as canonical EvolutionRun JSON."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from verfeinert.core.io import ensure_output_root, write_json

from ..models import EvolutionRunState
from ..validation import validate_evolution_run_document


def export_evolution_run_json(state: EvolutionRunState | Mapping[str, Any]) -> dict[str, Any]:
    """Return a schema-validated EvolutionRun JSON document."""
    if isinstance(state, EvolutionRunState):
        document = state.to_dict()
    elif isinstance(state, Mapping):
        document = dict(state)
    else:
        raise TypeError("state must be EvolutionRunState or mapping.")
    return validate_evolution_run_document(document)


def write_evolution_run_json(
    state: EvolutionRunState | Mapping[str, Any],
    *,
    output_root: str | Path,
    input_roots: tuple[str | Path, ...] | list[str | Path] = (),
    filename: str = "evolution_run.json",
) -> Path:
    """Write a validated EvolutionRun JSON document under a caller-owned root."""
    document = export_evolution_run_json(state)
    root = ensure_output_root(output_root, input_roots=input_roots)
    target = root / document["evolution_run_id"] / filename
    return write_json(target, document)


__all__ = ["export_evolution_run_json", "write_evolution_run_json"]

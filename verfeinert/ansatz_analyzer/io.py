"""Input and output helpers for canonical analyzer documents."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from verfeinert.core.io import ensure_output_root, read_json, write_json

from .config import AnalyzerConfig
from .models import AnalysisResultRecord, CandidateView
from .validation import (
    AnalyzerValidationError,
    validate_analysis_result_document,
    validate_analyzer_input_document,
    validate_candidate_document,
)


def load_candidate_views(source: str | Path | Mapping[str, Any]) -> list[CandidateView]:
    """Load canonical Candidate views from a Candidate or StagedPackage source."""
    document = _load_mapping(source)
    validated = validate_analyzer_input_document(document)
    if validated["schema_version"] == "verfeinert.candidate.v1":
        return [CandidateView.from_document(validated)]
    return [
        CandidateView.from_document(candidate)
        for candidate in validated.get("candidates", [])
    ]


def load_candidate_document(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and validate a single canonical Candidate document."""
    document = _load_mapping(source)
    return validate_candidate_document(document)


def write_analysis_result_json(
    record: AnalysisResultRecord | Mapping[str, Any],
    config: AnalyzerConfig,
) -> Path:
    """Write one canonical AnalysisResult JSON document under a guarded root."""
    if not isinstance(config, AnalyzerConfig):
        raise AnalyzerValidationError("config must be an AnalyzerConfig.")
    payload = record.to_dict() if isinstance(record, AnalysisResultRecord) else dict(record)
    validated = validate_analysis_result_document(payload)
    output_root = ensure_output_root(
        config.output_root,
        input_roots=config.input_roots,
    )
    result_root = output_root / config.run_id
    result_root.mkdir(parents=True, exist_ok=True)
    path = result_root / f"{_safe_filename(validated['analysis_result_id'])}.json"
    write_json(path, validated)
    return path


def _load_mapping(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if isinstance(source, (str, Path)):
        payload = read_json(source)
        if not isinstance(payload, Mapping):
            raise AnalyzerValidationError("JSON analyzer input must be an object.")
        return dict(payload)
    raise AnalyzerValidationError("source must be a path or mapping.")


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "analysis_result"


__all__ = [
    "load_candidate_document",
    "load_candidate_views",
    "write_analysis_result_json",
]

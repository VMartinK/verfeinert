"""Stdlib derived artifact writers for analyzer result views."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from verfeinert.core.hashing import hash_file
from verfeinert.core.io import ensure_output_root, write_json
from verfeinert.core.io.serialization import to_json_safe

from ..collections import AnalysisResultCollection
from ..pareto import ParetoResult
from ..ranking import RankingResult


@dataclass(frozen=True)
class DerivedArtifact:
    """Metadata for one derived analyzer artifact."""

    path: Path
    kind: str
    format: str
    transform: str
    transform_version: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe artifact record."""
        return to_json_safe(
            {
                "path": str(self.path),
                "kind": self.kind,
                "format": self.format,
                "transform": self.transform,
                "transform_version": self.transform_version,
                "sha256": self.sha256,
            },
        )


def write_ranking_json(
    result: RankingResult,
    *,
    output_root: str | Path,
    run_id: str,
    input_roots=(),
    filename: str = "ranking.json",
) -> DerivedArtifact:
    """Write a derived ranking JSON artifact under a guarded output root."""
    if not isinstance(result, RankingResult):
        raise TypeError("result must be a RankingResult.")
    path = _artifact_path(output_root, run_id, filename, input_roots=input_roots)
    write_json(path, result.to_dict())
    return _artifact(
        path,
        kind="derived_table",
        file_format="json",
        transform="ranking",
        transform_version=result.to_dict()["transform_version"],
    )


def write_ranking_csv(
    result: RankingResult,
    *,
    output_root: str | Path,
    run_id: str,
    input_roots=(),
    filename: str = "ranking.csv",
) -> DerivedArtifact:
    """Write a derived ranking CSV artifact under a guarded output root."""
    if not isinstance(result, RankingResult):
        raise TypeError("result must be a RankingResult.")
    path = _artifact_path(output_root, run_id, filename, input_roots=input_roots)
    rows = result.to_rows()
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    return _artifact(
        path,
        kind="derived_table",
        file_format="csv",
        transform="ranking",
        transform_version=result.to_dict()["transform_version"],
    )


def write_pareto_json(
    result: ParetoResult,
    *,
    output_root: str | Path,
    run_id: str,
    input_roots=(),
    filename: str = "pareto.json",
) -> DerivedArtifact:
    """Write a derived Pareto JSON artifact under a guarded output root."""
    if not isinstance(result, ParetoResult):
        raise TypeError("result must be a ParetoResult.")
    path = _artifact_path(output_root, run_id, filename, input_roots=input_roots)
    payload = result.to_dict()
    write_json(path, payload)
    return _artifact(
        path,
        kind="derived_table",
        file_format="json",
        transform=payload["transform"],
        transform_version=payload["transform_version"],
    )


def write_pareto_csv(
    result: ParetoResult,
    *,
    output_root: str | Path,
    run_id: str,
    input_roots=(),
    filename: str = "pareto.csv",
) -> DerivedArtifact:
    """Write a flat Pareto CSV artifact under a guarded output root."""
    if not isinstance(result, ParetoResult):
        raise TypeError("result must be a ParetoResult.")
    path = _artifact_path(output_root, run_id, filename, input_roots=input_roots)
    rows = _pareto_rows(result)
    _write_rows(path, rows)
    return _artifact(
        path,
        kind="derived_table",
        file_format="csv",
        transform="pareto_classification",
        transform_version=result.to_dict()["transform_version"],
    )


def write_analysis_results_csv(
    collection: AnalysisResultCollection,
    *,
    output_root: str | Path,
    run_id: str,
    input_roots=(),
    filename: str = "analysis_results.csv",
) -> DerivedArtifact:
    """Write a flat CSV view of canonical AnalysisResult documents."""
    if not isinstance(collection, AnalysisResultCollection):
        raise TypeError("collection must be an AnalysisResultCollection.")
    path = _artifact_path(output_root, run_id, filename, input_roots=input_roots)
    rows = [_analysis_result_row(document) for document in collection]
    _write_rows(path, rows)
    return _artifact(
        path,
        kind="derived_table",
        file_format="csv",
        transform="analysis_results",
        transform_version="1",
    )


def _artifact_path(
    output_root: str | Path,
    run_id: str,
    filename: str,
    *,
    input_roots,
) -> Path:
    root = ensure_output_root(output_root, input_roots=input_roots)
    path = root / _safe_filename(run_id) / "derived" / _safe_filename(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _artifact(
    path: Path,
    *,
    kind: str,
    file_format: str,
    transform: str,
    transform_version: str,
) -> DerivedArtifact:
    return DerivedArtifact(
        path=path,
        kind=kind,
        format=file_format,
        transform=transform,
        transform_version=transform_version,
        sha256=hash_file(path),
    )


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row}) or ["artifact_empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _analysis_result_row(document: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "analysis_result_id": document["analysis_result_id"],
        "candidate_id": document["candidate_ref"]["candidate_id"],
    }
    for key, value in document.get("cost", {}).items():
        if key == "metadata":
            continue
        row[f"cost_{key}"] = value
    for metric in document.get("metrics", []):
        metric_name = str(metric.get("name", "")).strip()
        if not metric_name:
            continue
        row[f"metric_{metric_name}_status"] = metric.get("status")
        value = metric.get("value")
        if isinstance(value, dict):
            for key, item in value.items():
                row[f"metric_{metric_name}_{key}"] = item
        else:
            row[f"metric_{metric_name}"] = value
    return to_json_safe(row)


def _pareto_rows(result: ParetoResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    transform_version = result.to_dict()["transform_version"]
    for candidate in result.candidates:
        row: dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "analysis_result_id": candidate.analysis_result_id,
            "cost_value": candidate.cost_value,
            "pareto_rank": candidate.pareto_rank,
            "is_frontier": candidate.is_frontier,
            "dominated_by": "|".join(candidate.dominated_by),
            "dominates": "|".join(candidate.dominates),
            "dominated_by_reference": candidate.dominated_by_reference,
            "dominates_reference": candidate.dominates_reference,
            "warnings": "|".join(candidate.warnings),
            "transform_version": transform_version,
        }
        for name, value in candidate.objective_values.items():
            row[f"objective_{name}"] = value
        rows.append(to_json_safe(row))
    return rows


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    normalized = normalized.strip("._-")
    return normalized or "artifact"


__all__ = [
    "DerivedArtifact",
    "write_analysis_results_csv",
    "write_pareto_csv",
    "write_pareto_json",
    "write_ranking_csv",
    "write_ranking_json",
]

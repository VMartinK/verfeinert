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
    return _artifact(path, kind="derived_table", file_format="json", result=result)


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
    return _artifact(path, kind="derived_table", file_format="csv", result=result)


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
    result: RankingResult,
) -> DerivedArtifact:
    return DerivedArtifact(
        path=path,
        kind=kind,
        format=file_format,
        transform="ranking",
        transform_version=result.to_dict()["transform_version"],
        sha256=hash_file(path),
    )


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    normalized = normalized.strip("._-")
    return normalized or "artifact"


__all__ = [
    "DerivedArtifact",
    "write_ranking_csv",
    "write_ranking_json",
]

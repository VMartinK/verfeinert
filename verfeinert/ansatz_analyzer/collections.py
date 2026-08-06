"""Validated collections of canonical AnalysisResult documents."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verfeinert.core.io import read_json
from verfeinert.core.io.serialization import to_json_safe

from .models import ANALYSIS_RESULT_SCHEMA_VERSION, AnalysisResultRecord
from .validation import AnalyzerValidationError, validate_analysis_result_document


class AnalysisResultCollectionError(ValueError):
    """Raised when an AnalysisResult collection violates collection invariants."""


@dataclass(frozen=True)
class AnalysisResultCollection:
    """Internal ordered collection over canonical AnalysisResult documents."""

    documents: tuple[dict[str, Any], ...]
    collection_id: str = "analysis-result-collection"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validated = tuple(_validate_result_document(item) for item in self.documents)
        schema_versions = {item["schema_version"] for item in validated}
        if schema_versions and schema_versions != {ANALYSIS_RESULT_SCHEMA_VERSION}:
            raise AnalysisResultCollectionError(
                f"Collection schema versions must be homogeneous: {sorted(schema_versions)}",
            )
        _require_unique(validated, "analysis_result_id")
        candidate_ids = [item["candidate_ref"]["candidate_id"] for item in validated]
        if len(set(candidate_ids)) != len(candidate_ids):
            duplicated = sorted(
                {candidate_id for candidate_id in candidate_ids if candidate_ids.count(candidate_id) > 1},
            )
            raise AnalysisResultCollectionError(
                f"Collection contains duplicate candidate IDs: {duplicated}",
            )
        object.__setattr__(self, "documents", validated)
        object.__setattr__(self, "collection_id", str(self.collection_id))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    @classmethod
    def from_records(
        cls,
        records: Iterable[AnalysisResultRecord | Mapping[str, Any]],
        *,
        collection_id: str = "analysis-result-collection",
        metadata: Mapping[str, Any] | None = None,
    ) -> "AnalysisResultCollection":
        """Build a collection from record objects or parsed mappings."""
        return cls(
            tuple(_record_to_mapping(record) for record in records),
            collection_id=collection_id,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_sources(
        cls,
        sources: Iterable[str | Path | Mapping[str, Any] | AnalysisResultRecord],
        *,
        collection_id: str = "analysis-result-collection",
        metadata: Mapping[str, Any] | None = None,
    ) -> "AnalysisResultCollection":
        """Load a collection from paths, directories, mappings, or records."""
        documents: list[dict[str, Any]] = []
        for source in sources:
            documents.extend(_documents_from_source(source))
        return cls.from_records(
            documents,
            collection_id=collection_id,
            metadata=metadata,
        )

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.documents)

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def analysis_result_ids(self) -> tuple[str, ...]:
        """Return analysis result identifiers in collection order."""
        return tuple(item["analysis_result_id"] for item in self.documents)

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        """Return candidate identifiers in collection order."""
        return tuple(item["candidate_ref"]["candidate_id"] for item in self.documents)

    def get_by_candidate_id(self, candidate_id: str) -> dict[str, Any]:
        """Return one result document by candidate ID."""
        for document in self.documents:
            if document["candidate_ref"]["candidate_id"] == str(candidate_id):
                return document
        raise KeyError(f"Candidate ID not found in collection: {candidate_id!r}")

    def get_by_analysis_result_id(self, analysis_result_id: str) -> dict[str, Any]:
        """Return one result document by AnalysisResult ID."""
        for document in self.documents:
            if document["analysis_result_id"] == str(analysis_result_id):
                return document
        raise KeyError(
            f"AnalysisResult ID not found in collection: {analysis_result_id!r}",
        )

    def iter_with_metric(
        self,
        metric_name: str,
        *,
        status: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield result documents containing a named metric."""
        for document in self.documents:
            metric = metric_record(document, metric_name)
            if metric is None:
                continue
            if status is not None and metric.get("status") != status:
                continue
            yield document

    def filter_by_classification(
        self,
        *,
        name: str | None = None,
        label: str | None = None,
    ) -> "AnalysisResultCollection":
        """Return documents with a matching classification name and/or label."""
        filtered = []
        for document in self.documents:
            for classification in document.get("classifications", []):
                name_matches = name is None or classification.get("name") == name
                label_matches = label is None or classification.get("label") == label
                if name_matches and label_matches:
                    filtered.append(document)
                    break
        return AnalysisResultCollection(
            tuple(filtered),
            collection_id=f"{self.collection_id}:filtered",
            metadata={
                "source_collection_id": self.collection_id,
                "classification_name": name,
                "classification_label": label,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe internal collection payload."""
        return to_json_safe(
            {
                "collection_id": self.collection_id,
                "schema_version": ANALYSIS_RESULT_SCHEMA_VERSION,
                "analysis_result_count": len(self.documents),
                "analysis_result_ids": list(self.analysis_result_ids),
                "candidate_ids": list(self.candidate_ids),
                "metadata": self.metadata,
                "analysis_results": list(self.documents),
            },
        )


def metric_record(
    result_document: Mapping[str, Any],
    metric_name: str,
) -> dict[str, Any] | None:
    """Return the first metric record with a matching canonical metric name."""
    document = validate_analysis_result_document(result_document)
    for metric in document.get("metrics", []):
        if metric.get("name") == metric_name:
            return metric
    return None


def metric_value(
    result_document: Mapping[str, Any],
    metric_name: str,
    *,
    value_key: str | None = None,
) -> float | None:
    """Return a numeric metric value from an AnalysisResult document."""
    metric = metric_record(result_document, metric_name)
    if metric is None or metric.get("status") != "computed":
        return None
    value = metric.get("value")
    if value_key is not None:
        if not isinstance(value, Mapping):
            return None
        value = value.get(value_key)
    elif isinstance(value, Mapping):
        value = value.get(metric_name, value.get("score"))
    return _as_float_or_none(value)


def cost_value(result_document: Mapping[str, Any], field_name: str) -> float | None:
    """Return a numeric cost field from an AnalysisResult document."""
    document = validate_analysis_result_document(result_document)
    return _as_float_or_none(document.get("cost", {}).get(field_name))


def _documents_from_source(
    source: str | Path | Mapping[str, Any] | AnalysisResultRecord,
) -> list[dict[str, Any]]:
    if isinstance(source, AnalysisResultRecord):
        return [source.to_dict()]
    if isinstance(source, Mapping):
        return [dict(source)]
    path = Path(source)
    if path.is_dir():
        return [
            _read_analysis_result_path(item)
            for item in sorted(path.glob("*.json"))
        ]
    return [_read_analysis_result_path(path)]


def _read_analysis_result_path(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise AnalyzerValidationError(f"{path} does not contain a JSON object.")
    document = dict(payload)
    document.setdefault("metadata", {})
    document["metadata"] = {
        **dict(document.get("metadata", {})),
        "source_path": str(path),
    }
    return document


def _record_to_mapping(record: AnalysisResultRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(record, AnalysisResultRecord):
        return record.to_dict()
    return dict(record)


def _validate_result_document(
    item: AnalysisResultRecord | Mapping[str, Any],
) -> dict[str, Any]:
    return validate_analysis_result_document(_record_to_mapping(item))


def _require_unique(documents: tuple[dict[str, Any], ...], field_name: str) -> None:
    values = [item[field_name] for item in documents]
    if len(set(values)) != len(values):
        duplicated = sorted({value for value in values if values.count(value) > 1})
        raise AnalysisResultCollectionError(
            f"Collection contains duplicate {field_name}: {duplicated}",
        )


def _as_float_or_none(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    numeric = float(value)
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        return None
    return numeric


__all__ = [
    "AnalysisResultCollection",
    "AnalysisResultCollectionError",
    "cost_value",
    "metric_record",
    "metric_value",
]

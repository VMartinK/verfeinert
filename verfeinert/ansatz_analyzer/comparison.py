"""Generic comparison over explicitly selected AnalysisResult collections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from verfeinert.core.io import read_json
from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.schema_resources import load_schema as load_packaged_schema
from verfeinert.core.schema_resources import schema_registry as packaged_schema_registry

from .collections import AnalysisResultCollection, cost_value, metric_record, metric_value
from .pareto import ObjectiveSpec, ParetoConfig, compute_pareto_classifications
from .ranking import RankingConfig, RankingResult, rank_analysis_results


COMPARISON_RESULT_SCHEMA_VERSION = "verfeinert.comparison_result.v1"
COMPARISON_TRANSFORM_VERSION = "1"
SOURCE_ROLES = ("source", "reference", "candidate", "baseline")


class ComparisonError(ValueError):
    """Raised when comparison inputs or configuration are invalid."""


class ComparisonCompatibilityError(ComparisonError):
    """Raised when selected artifacts cannot be compared scientifically."""


@dataclass(frozen=True)
class ComparisonSource:
    """One explicitly selected AnalysisResult source for a comparison."""

    source_id: str
    collection: AnalysisResultCollection
    role: str = "source"
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _identifier(self.source_id, "source_id"))
        if not isinstance(self.collection, AnalysisResultCollection):
            raise ComparisonError("ComparisonSource.collection must be an AnalysisResultCollection.")
        role = _non_empty_text(self.role, "source.role").lower()
        if role not in SOURCE_ROLES:
            raise ComparisonError(f"source.role must be one of {SOURCE_ROLES}.")
        object.__setattr__(self, "role", role)
        if self.label is not None:
            object.__setattr__(self, "label", _non_empty_text(self.label, "source.label"))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    @classmethod
    def from_sources(
        cls,
        source_id: str,
        sources: Sequence[str | Path | Mapping[str, Any]],
        *,
        role: str = "source",
        label: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        collection_id: str | None = None,
    ) -> "ComparisonSource":
        """Build a comparison source from explicit AnalysisResult artifacts."""
        collection = AnalysisResultCollection.from_sources(
            sources,
            collection_id=collection_id or f"{source_id}:analysis",
        )
        return cls(
            source_id=source_id,
            collection=collection,
            role=role,
            label=label,
            metadata=dict(metadata or {}),
        )

    def to_ref_dict(self) -> dict[str, Any]:
        """Return the persisted source reference without embedding result documents."""
        return to_json_safe(
            {
                "source_id": self.source_id,
                "role": self.role,
                "label": self.label,
                "collection_id": self.collection.collection_id,
                "analysis_result_count": len(self.collection),
                "analysis_result_ids": list(self.collection.analysis_result_ids),
                "candidate_ids": list(self.collection.candidate_ids),
                "metadata": self.metadata,
            },
        )


@dataclass(frozen=True)
class ComparisonConfig:
    """Configuration for a global comparison transform."""

    comparison_id: str = "comparison"
    objectives: tuple[ObjectiveSpec, ...] = (
        ObjectiveSpec("trainability", "maximize"),
        ObjectiveSpec("expressibility", "maximize"),
    )
    ranking: RankingConfig | None = field(default_factory=RankingConfig)
    include_ranking: bool = True
    cost_field: str = "structural_cost"
    cost_thresholds: tuple[float, ...] = ()
    validate_cost: bool = True
    display_aliases: Mapping[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_id", _identifier(self.comparison_id, "comparison_id"))
        objectives = tuple(
            item if isinstance(item, ObjectiveSpec) else ObjectiveSpec(**dict(item))  # type: ignore[arg-type]
            for item in self.objectives
        )
        if len(objectives) < 2:
            raise ComparisonError("comparison requires at least two objectives.")
        if len({item.metric_name for item in objectives}) != len(objectives):
            raise ComparisonError("comparison objective metric names must be unique.")
        ranking = self.ranking
        if ranking is not None and not isinstance(ranking, RankingConfig):
            ranking = RankingConfig(**dict(ranking))  # type: ignore[arg-type]
        thresholds = tuple(float(item) for item in self.cost_thresholds)
        if any(not math.isfinite(item) for item in thresholds):
            raise ComparisonError("cost_thresholds must contain finite values.")
        aliases = {
            _non_empty_text(key, "display_aliases key"): _non_empty_text(value, "display_aliases value")
            for key, value in dict(self.display_aliases).items()
        }
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "ranking", ranking)
        object.__setattr__(self, "include_ranking", bool(self.include_ranking))
        object.__setattr__(self, "cost_field", _non_empty_text(self.cost_field, "cost_field"))
        object.__setattr__(self, "cost_thresholds", thresholds)
        object.__setattr__(self, "validate_cost", bool(self.validate_cost))
        object.__setattr__(self, "display_aliases", aliases)
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe config snapshot."""
        return to_json_safe(
            {
                "comparison_id": self.comparison_id,
                "objectives": [
                    {
                        "metric_name": item.metric_name,
                        "direction": item.direction,
                        "value_key": item.value_key,
                    }
                    for item in self.objectives
                ],
                "ranking": self.ranking.to_dict() if self.ranking is not None else None,
                "include_ranking": self.include_ranking,
                "cost_field": self.cost_field,
                "cost_thresholds": list(self.cost_thresholds),
                "validate_cost": self.validate_cost,
                "display_aliases": dict(self.display_aliases),
                "metadata": self.metadata,
            },
        )


@dataclass(frozen=True)
class CompatibilityIssue:
    """One structured compatibility issue."""

    code: str
    message: str
    severity: str = "error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe issue payload."""
        return to_json_safe(
            {
                "code": self.code,
                "severity": self.severity,
                "message": self.message,
                "details": self.details,
            },
        )


@dataclass(frozen=True)
class CompatibilityReport:
    """Structured compatibility decision for selected comparison sources."""

    compatible: bool
    fingerprints: dict[str, Any]
    issues: tuple[CompatibilityIssue, ...] = ()
    ignored_differences: tuple[str, ...] = (
        "output_paths",
        "filenames",
        "visualization_settings",
        "cli_invocation",
        "display_labels",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe compatibility report."""
        return to_json_safe(
            {
                "compatible": self.compatible,
                "fingerprints": self.fingerprints,
                "issues": [item.to_dict() for item in self.issues],
                "ignored_differences": list(self.ignored_differences),
            },
        )


@dataclass(frozen=True)
class ComparisonCandidateRow:
    """One candidate row in a ComparisonResult."""

    source_id: str
    source_role: str
    source_label: str
    candidate_id: str
    analysis_result_id: str
    display_label: str
    objective_values: dict[str, float]
    cost_value: float | None
    is_global_pareto: bool
    pareto_rank: int | None
    rank: int | None = None
    score: float | None = None
    score_status: str | None = None
    cost_eligibility: dict[str, bool | None] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe comparison row."""
        return to_json_safe(
            {
                "source_id": self.source_id,
                "source_role": self.source_role,
                "source_label": self.source_label,
                "candidate_id": self.candidate_id,
                "analysis_result_id": self.analysis_result_id,
                "display_label": self.display_label,
                "objective_values": self.objective_values,
                "cost_value": self.cost_value,
                "is_global_pareto": self.is_global_pareto,
                "pareto_rank": self.pareto_rank,
                "rank": self.rank,
                "score": self.score,
                "score_status": self.score_status,
                "cost_eligibility": self.cost_eligibility,
                "lineage": self.lineage,
                "source_context": self.source_context,
                "warnings": list(self.warnings),
            },
        )


@dataclass(frozen=True)
class ComparisonResult:
    """JSON-first global comparison artifact."""

    comparison_id: str
    config: ComparisonConfig
    sources: tuple[dict[str, Any], ...]
    compatibility: CompatibilityReport
    rows: tuple[ComparisonCandidateRow, ...]
    global_frontier_candidate_ids: tuple[str, ...]
    source_analysis_result_ids: tuple[str, ...]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    warnings: tuple[str, ...] = ()

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        """Return comparison candidate IDs in deterministic row order."""
        return tuple(item.candidate_id for item in self.rows)

    def to_rows(self) -> list[dict[str, Any]]:
        """Return deterministic flat rows for CSV/table export."""
        rows: list[dict[str, Any]] = []
        objective_names = [item.metric_name for item in self.config.objectives]
        for item in self.rows:
            row: dict[str, Any] = {
                "comparison_id": self.comparison_id,
                "source_id": item.source_id,
                "source_role": item.source_role,
                "source_label": item.source_label,
                "candidate_id": item.candidate_id,
                "analysis_result_id": item.analysis_result_id,
                "display_label": item.display_label,
                "cost_value": item.cost_value,
                "is_global_pareto": item.is_global_pareto,
                "pareto_rank": item.pareto_rank,
                "rank": item.rank,
                "score": item.score,
                "score_status": item.score_status,
                "transform_version": COMPARISON_TRANSFORM_VERSION,
            }
            for name in objective_names:
                row[f"objective_{name}"] = item.objective_values.get(name)
            for threshold, eligible in item.cost_eligibility.items():
                row[f"cost_eligible_{threshold}"] = eligible
            for key, value in item.lineage.items():
                row[f"lineage_{key}"] = value
            for key, value in item.source_context.items():
                row[f"source_context_{key}"] = value
            row["warnings"] = "|".join(item.warnings)
            rows.append(to_json_safe(row))
        return rows

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe comparison artifact."""
        return to_json_safe(
            {
                "schema_version": COMPARISON_RESULT_SCHEMA_VERSION,
                "transform": "comparison",
                "transform_version": COMPARISON_TRANSFORM_VERSION,
                "comparison_id": self.comparison_id,
                "created_at": self.created_at,
                "source_analysis_result_ids": list(self.source_analysis_result_ids),
                "global_frontier_candidate_ids": list(self.global_frontier_candidate_ids),
                "config": self.config.to_dict(),
                "sources": list(self.sources),
                "compatibility": self.compatibility.to_dict(),
                "rows": [item.to_dict() for item in self.rows],
                "table_views": {
                    "candidate_summary": {
                        "row_count": len(self.rows),
                        "columns": sorted({key for row in self.to_rows() for key in row}),
                    },
                },
                "warnings": list(self.warnings),
            },
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComparisonResult":
        """Reconstruct a ComparisonResult from persisted JSON."""
        document = validate_comparison_result_document(payload)
        config = ComparisonConfig(**dict(document["config"]))
        issues = tuple(
            CompatibilityIssue(
                code=item["code"],
                severity=item.get("severity", "error"),
                message=item["message"],
                details=dict(item.get("details", {})),
            )
            for item in document["compatibility"].get("issues", [])
        )
        compatibility = CompatibilityReport(
            compatible=bool(document["compatibility"]["compatible"]),
            fingerprints=dict(document["compatibility"].get("fingerprints", {})),
            issues=issues,
            ignored_differences=tuple(document["compatibility"].get("ignored_differences", ())),
        )
        rows = tuple(
            ComparisonCandidateRow(
                source_id=item["source_id"],
                source_role=item["source_role"],
                source_label=item["source_label"],
                candidate_id=item["candidate_id"],
                analysis_result_id=item["analysis_result_id"],
                display_label=item["display_label"],
                objective_values=dict(item.get("objective_values", {})),
                cost_value=item.get("cost_value"),
                is_global_pareto=bool(item["is_global_pareto"]),
                pareto_rank=item.get("pareto_rank"),
                rank=item.get("rank"),
                score=item.get("score"),
                score_status=item.get("score_status"),
                cost_eligibility=dict(item.get("cost_eligibility", {})),
                lineage=dict(item.get("lineage", {})),
                source_context=dict(item.get("source_context", {})),
                warnings=tuple(item.get("warnings", ())),
            )
            for item in document["rows"]
        )
        return cls(
            comparison_id=document["comparison_id"],
            config=config,
            sources=tuple(dict(item) for item in document["sources"]),
            compatibility=compatibility,
            rows=rows,
            global_frontier_candidate_ids=tuple(document["global_frontier_candidate_ids"]),
            source_analysis_result_ids=tuple(document["source_analysis_result_ids"]),
            created_at=document["created_at"],
            warnings=tuple(document.get("warnings", ())),
        )


def compare_analysis_collections(
    sources: Sequence[ComparisonSource],
    *,
    config: ComparisonConfig | None = None,
) -> ComparisonResult:
    """Compare explicitly selected compatible AnalysisResult collections."""
    if len(tuple(sources)) < 2:
        raise ComparisonError("comparison requires at least two explicitly selected sources.")
    if any(not isinstance(source, ComparisonSource) for source in sources):
        raise ComparisonError("sources must contain ComparisonSource records.")
    source_ids = [source.source_id for source in sources]
    duplicated_sources = sorted({item for item in source_ids if source_ids.count(item) > 1})
    if duplicated_sources:
        raise ComparisonError(f"duplicate comparison source IDs: {duplicated_sources}")
    resolved = config or ComparisonConfig()
    _ensure_unique_candidate_ids(sources)
    compatibility = compatibility_report(sources, config=resolved)
    if not compatibility.compatible:
        messages = "; ".join(issue.message for issue in compatibility.issues)
        raise ComparisonCompatibilityError(messages)

    documents: list[dict[str, Any]] = []
    source_by_candidate: dict[str, ComparisonSource] = {}
    for source in sources:
        for document in source.collection:
            documents.append(document)
            source_by_candidate[document["candidate_ref"]["candidate_id"]] = source
    combined = AnalysisResultCollection.from_records(
        documents,
        collection_id=f"{resolved.comparison_id}:combined-analysis",
        metadata={"source_ids": source_ids},
    )
    pareto_config = ParetoConfig(
        objectives=resolved.objectives,
        cost_field=resolved.cost_field,
        cost_thresholds=resolved.cost_thresholds,
    )
    pareto = compute_pareto_classifications(combined, config=pareto_config)
    ranking: RankingResult | None = None
    ranking_by_candidate: dict[str, Any] = {}
    if resolved.include_ranking and resolved.ranking is not None:
        ranking = rank_analysis_results(combined, config=resolved.ranking)
        ranking_by_candidate = {
            item.candidate_id: item
            for item in ranking.ranked_candidates
        }
    pareto_by_candidate = {item.candidate_id: item for item in pareto.candidates}
    rows: list[ComparisonCandidateRow] = []
    for document in combined:
        candidate_id = document["candidate_ref"]["candidate_id"]
        source = source_by_candidate[candidate_id]
        pareto_row = pareto_by_candidate[candidate_id]
        ranking_row = ranking_by_candidate.get(candidate_id)
        rows.append(
            ComparisonCandidateRow(
                source_id=source.source_id,
                source_role=source.role,
                source_label=source.label or source.source_id,
                candidate_id=candidate_id,
                analysis_result_id=document["analysis_result_id"],
                display_label=resolved.display_aliases.get(candidate_id, candidate_id),
                objective_values=dict(pareto_row.objective_values),
                cost_value=pareto_row.cost_value,
                is_global_pareto=pareto_row.is_frontier,
                pareto_rank=pareto_row.pareto_rank,
                rank=ranking_row.rank if ranking_row is not None else None,
                score=ranking_row.score if ranking_row is not None else None,
                score_status=ranking_row.status if ranking_row is not None else None,
                cost_eligibility=_cost_eligibility(pareto_row.cost_value, resolved.cost_thresholds),
                lineage=_lineage_metadata(document),
                source_context=_source_context_metadata(document),
                warnings=tuple(pareto_row.warnings),
            ),
        )
    return ComparisonResult(
        comparison_id=resolved.comparison_id,
        config=resolved,
        sources=tuple(source.to_ref_dict() for source in sources),
        compatibility=compatibility,
        rows=tuple(rows),
        global_frontier_candidate_ids=pareto.frontier_candidate_ids,
        source_analysis_result_ids=combined.analysis_result_ids,
        warnings=tuple(dict.fromkeys([*pareto.warnings, *((ranking.warnings if ranking else ())) ])),
    )


def compatibility_report(
    sources: Sequence[ComparisonSource],
    *,
    config: ComparisonConfig | None = None,
) -> CompatibilityReport:
    """Return a structured compatibility report without computing comparison rows."""
    if len(tuple(sources)) < 2:
        raise ComparisonError("compatibility validation requires at least two selected sources.")
    resolved = config or ComparisonConfig()
    issues: list[CompatibilityIssue] = []
    fingerprints: dict[str, Any] = {
        "objectives": [
            {
                "metric_name": item.metric_name,
                "direction": item.direction,
                "value_key": item.value_key,
            }
            for item in resolved.objectives
        ],
        "ranking": resolved.ranking.to_dict() if resolved.ranking is not None else None,
        "cost": {
            "field": resolved.cost_field,
            "thresholds": list(resolved.cost_thresholds),
            "validated": resolved.validate_cost,
        },
        "sources": {},
    }
    required_metrics = _required_metric_names(resolved)
    for source in sources:
        source_fingerprints: dict[str, Any] = {"metrics": {}, "cost": None}
        for metric_name in sorted(required_metrics):
            values = []
            for document in source.collection:
                metric = metric_record(document, metric_name)
                if metric is None or metric.get("status") != "computed":
                    issues.append(
                        CompatibilityIssue(
                            code="missing_metric",
                            message=(
                                f"source {source.source_id!r} candidate "
                                f"{document['candidate_ref']['candidate_id']!r} lacks computed metric "
                                f"{metric_name!r}"
                            ),
                            details={
                                "source_id": source.source_id,
                                "candidate_id": document["candidate_ref"]["candidate_id"],
                                "metric_name": metric_name,
                            },
                        ),
                    )
                    continue
                values.append(_metric_fingerprint(metric_name, metric))
            source_fingerprints["metrics"][metric_name] = _single_fingerprint(
                values,
                issues=issues,
                source_id=source.source_id,
                kind=f"metric:{metric_name}",
            )
        if _requires_cost_validation(resolved):
            cost_values = [_cost_fingerprint(document, resolved.cost_field) for document in source.collection]
            source_fingerprints["cost"] = _single_fingerprint(
                cost_values,
                issues=issues,
                source_id=source.source_id,
                kind="cost_normalization",
            )
        fingerprints["sources"][source.source_id] = source_fingerprints

    issues.extend(_cross_source_issues(fingerprints))
    return CompatibilityReport(
        compatible=not any(issue.severity == "error" for issue in issues),
        fingerprints=fingerprints,
        issues=tuple(issues),
    )


def validate_comparison_result_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the versioned ComparisonResult JSON persistence contract."""
    if not isinstance(payload, Mapping):
        raise ComparisonError("ComparisonResult payload must be a mapping.")
    try:
        document = json.loads(json.dumps(payload))
    except TypeError as exc:
        raise ComparisonError(f"ComparisonResult payload is not JSON-serializable: {exc}") from exc
    try:
        _comparison_result_validator().validate(document)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        location = path or "<root>"
        raise ComparisonError(
            f"comparison_result document failed schema validation at {location}: {exc.message}",
        ) from exc
    return document


def read_comparison_result_json(path: str | Path) -> ComparisonResult:
    """Read a persisted ComparisonResult JSON artifact."""
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise ComparisonError(f"{path} does not contain a JSON object.")
    return ComparisonResult.from_dict(payload)


@lru_cache(maxsize=None)
def _comparison_result_validator() -> Draft202012Validator:
    schema = load_packaged_schema("comparison_result")
    return Draft202012Validator(
        schema,
        registry=packaged_schema_registry(("comparison_result",)),
    )


def _ensure_unique_candidate_ids(sources: Sequence[ComparisonSource]) -> None:
    owners: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    for source in sources:
        for candidate_id in source.collection.candidate_ids:
            if candidate_id in owners:
                duplicates.setdefault(candidate_id, [owners[candidate_id]]).append(source.source_id)
            else:
                owners[candidate_id] = source.source_id
    if duplicates:
        raise ComparisonError(
            "duplicate candidate IDs across comparison sources: "
            + json.dumps(duplicates, sort_keys=True),
        )


def _required_metric_names(config: ComparisonConfig) -> set[str]:
    names = {item.metric_name for item in config.objectives}
    if config.include_ranking and config.ranking is not None:
        for component in config.ranking.score_components:
            if not component.startswith("cost."):
                names.add(component)
    return names


def _requires_cost_validation(config: ComparisonConfig) -> bool:
    if not config.validate_cost:
        return False
    if config.cost_thresholds:
        return True
    if config.include_ranking and config.ranking is not None:
        if config.ranking.cost_threshold is not None:
            return True
        if any(component.startswith("cost.") for component in config.ranking.score_components):
            return True
    return True


def _metric_fingerprint(metric_name: str, metric: Mapping[str, Any]) -> dict[str, Any] | None:
    metadata = metric.get("metadata", {})
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    configuration = metadata.get("configuration")
    configuration = dict(configuration) if isinstance(configuration, Mapping) else {}
    if metric_name == "trainability":
        if not configuration or metadata.get("hamiltonian_kind") is None:
            return None
        return to_json_safe(
            {
                "metric": metric_name,
                "definition": "empirical_gradient_trainability",
                "configuration": _without_runtime_noise(configuration),
                "hamiltonian": {
                    "hamiltonian": metadata.get("hamiltonian"),
                    "hamiltonian_kind": metadata.get("hamiltonian_kind"),
                    "hamiltonian_definition": metadata.get("hamiltonian_definition"),
                    "hamiltonian_scale": metadata.get("hamiltonian_scale"),
                },
                "value_schema": _value_schema(metric.get("value")),
            },
        )
    if metric_name == "expressibility":
        if not configuration:
            return None
        return to_json_safe(
            {
                "metric": metric_name,
                "definition": "fidelity_kl_expressibility",
                "configuration": _without_runtime_noise(configuration),
                "value_schema": _value_schema(metric.get("value")),
            },
        )
    return to_json_safe(
        {
            "metric": metric_name,
            "configuration": _without_runtime_noise(configuration),
            "value_schema": _value_schema(metric.get("value")),
        },
    )


def _cost_fingerprint(document: Mapping[str, Any], cost_field: str) -> dict[str, Any] | None:
    if cost_value(document, cost_field) is None:
        return None
    cost = dict(document.get("cost", {}))
    metadata = cost.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    return to_json_safe(
        {
            "field": cost_field,
            "cost_model": metadata.get("cost_model"),
            "definition": metadata.get("definition"),
            "reference_id": metadata.get("reference_id"),
            "reference_bounds": metadata.get("reference_bounds"),
            "component_weights": metadata.get("component_weights"),
            "depth_source": metadata.get("depth_source"),
        },
    )


def _single_fingerprint(
    values: Sequence[Any],
    *,
    issues: list[CompatibilityIssue],
    source_id: str,
    kind: str,
) -> Any:
    present = [value for value in values if value is not None]
    if not present:
        issues.append(
            CompatibilityIssue(
                code="missing_provenance",
                message=f"source {source_id!r} lacks required {kind} provenance",
                details={"source_id": source_id, "kind": kind},
            ),
        )
        return None
    if len(present) != len(values):
        issues.append(
            CompatibilityIssue(
                code="missing_provenance",
                message=f"source {source_id!r} has rows without required {kind} provenance",
                details={"source_id": source_id, "kind": kind},
            ),
        )
    encoded = [_stable_json(value) for value in present]
    if len(set(encoded)) != 1:
        issues.append(
            CompatibilityIssue(
                code="inconsistent_source_provenance",
                message=f"source {source_id!r} contains inconsistent {kind} provenance",
                details={"source_id": source_id, "kind": kind},
            ),
        )
    return present[0]


def _cross_source_issues(fingerprints: Mapping[str, Any]) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    source_fingerprints = dict(fingerprints.get("sources", {}))
    if len(source_fingerprints) < 2:
        return issues
    metric_names = sorted(
        {
            metric_name
            for source in source_fingerprints.values()
            for metric_name in dict(source.get("metrics", {}))
        },
    )
    for metric_name in metric_names:
        values = {
            source_id: source.get("metrics", {}).get(metric_name)
            for source_id, source in source_fingerprints.items()
        }
        if len({_stable_json(value) for value in values.values()}) <= 1:
            continue
        code = "incompatible_metric_definition"
        message = f"incompatible metric definition for {metric_name!r}"
        if metric_name == "trainability":
            code = "incompatible_hamiltonian"
            message = "incompatible trainability Hamiltonian or trainability configuration"
        issues.append(
            CompatibilityIssue(
                code=code,
                message=message,
                details={"metric_name": metric_name, "source_fingerprints": values},
            ),
        )
    costs = {
        source_id: source.get("cost")
        for source_id, source in source_fingerprints.items()
    }
    if any(value is not None for value in costs.values()) and len({_stable_json(value) for value in costs.values()}) > 1:
        issues.append(
            CompatibilityIssue(
                code="incompatible_cost_normalization",
                message="incompatible structural-cost normalization provenance",
                details={"source_fingerprints": costs},
            ),
        )
    return issues


def _without_runtime_noise(configuration: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {
        "backend_label",
        "requires_qnode_execution",
        "max_total_state_calls",
        "max_total_qnode_calls",
        "max_gradient_components",
        "max_parameters_per_circuit",
    }
    return {
        key: value
        for key, value in sorted(dict(configuration).items())
        if key not in ignored
    }


def _value_schema(value: Any) -> Any:
    if isinstance(value, Mapping):
        return sorted(str(key) for key in value)
    return type(value).__name__


def _cost_eligibility(
    value: float | None,
    thresholds: Sequence[float],
) -> dict[str, bool | None]:
    result: dict[str, bool | None] = {}
    for threshold in thresholds:
        key = _threshold_token(threshold)
        result[key] = None if value is None else bool(value <= threshold)
    return result


def _lineage_metadata(document: Mapping[str, Any]) -> dict[str, Any]:
    semantics = document.get("metadata", {}).get("candidate_semantics", {})
    if not isinstance(semantics, Mapping):
        return {}
    lineage = semantics.get("lineage", {})
    return to_json_safe(dict(lineage)) if isinstance(lineage, Mapping) else {}


def _source_context_metadata(document: Mapping[str, Any]) -> dict[str, Any]:
    semantics = document.get("metadata", {}).get("candidate_semantics", {})
    if not isinstance(semantics, Mapping):
        return {}
    context = semantics.get("source_context", {})
    return to_json_safe(dict(context)) if isinstance(context, Mapping) else {}


def _stable_json(value: Any) -> str:
    return json.dumps(to_json_safe(value), sort_keys=True, separators=(",", ":"))


def _threshold_token(value: float) -> str:
    return str(float(value)).replace("-", "m").replace(".", "p")


def _identifier(value: object, field_name: str) -> str:
    text = _non_empty_text(value, field_name)
    if not text.replace("_", "-").replace(".", "-").replace(":", "-").replace("-", "").isalnum():
        raise ComparisonError(f"{field_name} is not a portable identifier.")
    return text


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComparisonError(f"{field_name} must be a non-empty string.")
    return value.strip()


__all__ = [
    "COMPARISON_RESULT_SCHEMA_VERSION",
    "COMPARISON_TRANSFORM_VERSION",
    "ComparisonCandidateRow",
    "ComparisonCompatibilityError",
    "ComparisonConfig",
    "ComparisonError",
    "ComparisonResult",
    "ComparisonSource",
    "CompatibilityIssue",
    "CompatibilityReport",
    "compare_analysis_collections",
    "compatibility_report",
    "read_comparison_result_json",
    "validate_comparison_result_document",
]

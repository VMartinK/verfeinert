"""Deterministic ranking over AnalysisResult collections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from .collections import AnalysisResultCollection, cost_value, metric_value


class RankingError(ValueError):
    """Raised when ranking configuration or inputs are invalid."""


RANKING_TRANSFORM_VERSION = "1"
SCORE_COMBINATIONS = ("product", "weighted_sum")


@dataclass(frozen=True)
class RankingConfig:
    """Configuration for derived candidate ranking."""

    score_components: Mapping[str, float] = field(
        default_factory=lambda: {"expressibility": 1.0, "trainability": 1.0},
    )
    combination: str = "product"
    ascending: bool = False
    top_n: int | None = None
    cost_threshold: float | None = None
    cost_field: str = "structural_cost"
    include_unrankable: bool = False

    def __post_init__(self) -> None:
        if self.combination not in SCORE_COMBINATIONS:
            raise RankingError(f"combination must be one of {SCORE_COMBINATIONS}.")
        if not isinstance(self.score_components, Mapping) or not self.score_components:
            raise RankingError("score_components must be a non-empty mapping.")
        components: dict[str, float] = {}
        for name, weight in self.score_components.items():
            if not isinstance(name, str) or not name.strip():
                raise RankingError("score component names must be non-empty strings.")
            numeric = float(weight)
            if not math.isfinite(numeric) or numeric < 0.0:
                raise RankingError("score component weights must be finite and non-negative.")
            components[name.strip()] = numeric
        if sum(components.values()) <= 0.0:
            raise RankingError("score component weights must sum to a positive value.")
        top_n = self.top_n
        if top_n is not None and int(top_n) <= 0:
            raise RankingError("top_n must be None or a positive integer.")
        cost_threshold = self.cost_threshold
        if cost_threshold is not None:
            cost_threshold = float(cost_threshold)
            if not math.isfinite(cost_threshold):
                raise RankingError("cost_threshold must be finite.")
        object.__setattr__(self, "score_components", components)
        object.__setattr__(self, "top_n", int(top_n) if top_n is not None else None)
        object.__setattr__(self, "cost_threshold", cost_threshold)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe config snapshot."""
        return to_json_safe(
            {
                "score_components": dict(self.score_components),
                "combination": self.combination,
                "ascending": self.ascending,
                "top_n": self.top_n,
                "cost_threshold": self.cost_threshold,
                "cost_field": self.cost_field,
                "include_unrankable": self.include_unrankable,
            },
        )


@dataclass(frozen=True)
class RankedCandidate:
    """One derived ranking row."""

    rank: int | None
    candidate_id: str
    analysis_result_id: str
    score: float | None
    component_values: dict[str, float]
    component_weights: dict[str, float]
    cost_value: float | None
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe ranking row."""
        return to_json_safe(
            {
                "rank": self.rank,
                "candidate_id": self.candidate_id,
                "analysis_result_id": self.analysis_result_id,
                "score": self.score,
                "component_values": self.component_values,
                "component_weights": self.component_weights,
                "cost_value": self.cost_value,
                "status": self.status,
                "reason": self.reason,
            },
        )


@dataclass(frozen=True)
class RankingResult:
    """Derived ranking result with provenance."""

    config: RankingConfig
    ranked_candidates: tuple[RankedCandidate, ...]
    source_analysis_result_ids: tuple[str, ...]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    warnings: tuple[str, ...] = ()

    @property
    def ranked_candidate_ids(self) -> tuple[str, ...]:
        """Return candidate IDs with assigned ranks."""
        return tuple(
            item.candidate_id
            for item in self.ranked_candidates
            if item.rank is not None
        )

    def to_rows(self) -> list[dict[str, Any]]:
        """Return flat rows for derived CSV export."""
        rows: list[dict[str, Any]] = []
        for item in self.ranked_candidates:
            row = {
                "rank": item.rank,
                "candidate_id": item.candidate_id,
                "analysis_result_id": item.analysis_result_id,
                "score": item.score,
                "cost_value": item.cost_value,
                "status": item.status,
                "reason": item.reason,
                "transform_version": RANKING_TRANSFORM_VERSION,
            }
            for component, value in item.component_values.items():
                row[f"component_{component}"] = value
                row[f"weight_{component}"] = item.component_weights[component]
            rows.append(to_json_safe(row))
        return rows

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe derived ranking payload."""
        return to_json_safe(
            {
                "schema_version": "verfeinert.ranking_result.v1",
                "transform": "ranking",
                "transform_version": RANKING_TRANSFORM_VERSION,
                "created_at": self.created_at,
                "source_analysis_result_ids": list(self.source_analysis_result_ids),
                "config": self.config.to_dict(),
                "ranked_candidates": [
                    item.to_dict()
                    for item in self.ranked_candidates
                ],
                "warnings": list(self.warnings),
            },
        )


def rank_analysis_results(
    collection: AnalysisResultCollection,
    *,
    config: RankingConfig | None = None,
) -> RankingResult:
    """Rank an AnalysisResult collection by a configured derived score."""
    if not isinstance(collection, AnalysisResultCollection):
        raise RankingError("collection must be an AnalysisResultCollection.")
    resolved = config or RankingConfig()
    rankable: list[RankedCandidate] = []
    unrankable: list[RankedCandidate] = []
    warnings: list[str] = []

    for document in collection:
        row = _candidate_ranking_row(document, resolved)
        if row.status == "rankable":
            rankable.append(row)
        else:
            warnings.append(f"{row.candidate_id}: {row.reason}")
            if resolved.include_unrankable:
                unrankable.append(row)

    rankable = sorted(
        rankable,
        key=lambda item: (
            item.score if resolved.ascending else -float(item.score),
            item.candidate_id,
        ),
    )
    if resolved.top_n is not None:
        rankable = rankable[: resolved.top_n]
    ranked = [
        RankedCandidate(
            rank=index,
            candidate_id=item.candidate_id,
            analysis_result_id=item.analysis_result_id,
            score=item.score,
            component_values=item.component_values,
            component_weights=item.component_weights,
            cost_value=item.cost_value,
            status=item.status,
            reason=item.reason,
        )
        for index, item in enumerate(rankable, start=1)
    ]
    return RankingResult(
        config=resolved,
        ranked_candidates=tuple(ranked + unrankable),
        source_analysis_result_ids=collection.analysis_result_ids,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _candidate_ranking_row(
    document: Mapping[str, Any],
    config: RankingConfig,
) -> RankedCandidate:
    candidate_id = document["candidate_ref"]["candidate_id"]
    analysis_result_id = document["analysis_result_id"]
    cost = cost_value(document, config.cost_field)
    if config.cost_threshold is not None:
        if cost is None:
            return _unrankable(document, config, "cost unavailable")
        if cost > config.cost_threshold:
            return _unrankable(document, config, "cost threshold not satisfied")
    components: dict[str, float] = {}
    for component in config.score_components:
        value = _component_value(document, component)
        if value is None:
            return _unrankable(document, config, f"missing component {component!r}")
        components[component] = value
    score = _score(components, config)
    if score is None:
        return _unrankable(document, config, "score could not be computed")
    return RankedCandidate(
        rank=None,
        candidate_id=candidate_id,
        analysis_result_id=analysis_result_id,
        score=score,
        component_values=components,
        component_weights=dict(config.score_components),
        cost_value=cost,
        status="rankable",
    )


def _component_value(document: Mapping[str, Any], component: str) -> float | None:
    if component.startswith("cost."):
        return cost_value(document, component.split(".", 1)[1])
    return metric_value(document, component)


def _score(
    components: Mapping[str, float],
    config: RankingConfig,
) -> float | None:
    if config.combination == "weighted_sum":
        return float(
            sum(
                components[name] * config.score_components[name]
                for name in config.score_components
            ),
        )
    score = 1.0
    for name, weight in config.score_components.items():
        value = components[name]
        if value < 0.0:
            return None
        score *= value ** weight
    return float(score)


def _unrankable(
    document: Mapping[str, Any],
    config: RankingConfig,
    reason: str,
) -> RankedCandidate:
    return RankedCandidate(
        rank=None,
        candidate_id=document["candidate_ref"]["candidate_id"],
        analysis_result_id=document["analysis_result_id"],
        score=None,
        component_values={},
        component_weights=dict(config.score_components),
        cost_value=cost_value(document, config.cost_field),
        status="unrankable",
        reason=reason,
    )


__all__ = [
    "RANKING_TRANSFORM_VERSION",
    "RankedCandidate",
    "RankingConfig",
    "RankingError",
    "RankingResult",
    "rank_analysis_results",
]

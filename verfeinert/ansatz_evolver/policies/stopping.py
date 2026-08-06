"""Stopping-condition records for evolution pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import require_mapping, require_non_negative_int


@dataclass(frozen=True)
class StoppingPolicy:
    """Configured stopping limits."""

    max_generations: int
    patience: int | None = None

    def __post_init__(self) -> None:
        if type(self.max_generations) is not int or self.max_generations < 1:
            raise ValueError("max_generations must be a positive integer.")
        if self.patience is not None and (type(self.patience) is not int or self.patience < 0):
            raise ValueError("patience must be a non-negative integer or None.")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe policy data."""
        return {"max_generations": self.max_generations, "patience": self.patience}


@dataclass(frozen=True)
class StoppingDecision:
    """Decision describing whether evolution should stop."""

    should_stop: bool
    reason: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.should_stop) is not bool:
            raise ValueError("should_stop must be a boolean.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string.")
        if self.status not in {"running", "completed", "failed", "cancelled"}:
            raise ValueError("status must be running, completed, failed, or cancelled.")
        object.__setattr__(self, "metadata", require_mapping(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe decision data."""
        return {
            "should_stop": self.should_stop,
            "reason": self.reason,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


def evaluate_stopping_conditions(
    *,
    generation_index: int,
    policy: StoppingPolicy,
    candidate_count: int,
    analysis_result_count: int,
    survivor_count: int,
    duplicate_only: bool = False,
    strict_improvement: bool = True,
    cancelled: bool = False,
    failed: bool = False,
) -> StoppingDecision:
    """Evaluate common stopping states without running evolution work."""
    generation = require_non_negative_int(generation_index, "generation_index")
    if failed:
        return StoppingDecision(True, "failure_reported", "failed")
    if cancelled:
        return StoppingDecision(True, "cancelled", "cancelled")
    if candidate_count <= 0:
        return StoppingDecision(True, "no_candidates", "completed")
    if analysis_result_count <= 0:
        return StoppingDecision(True, "no_analysis_results", "failed")
    if survivor_count <= 0:
        return StoppingDecision(True, "no_survivors", "completed")
    if duplicate_only:
        return StoppingDecision(True, "duplicate_only_generation", "completed")
    if not strict_improvement:
        return StoppingDecision(True, "no_strict_improvement", "completed")
    if generation >= policy.max_generations:
        return StoppingDecision(True, "max_generations_reached", "completed")
    return StoppingDecision(False, "continue", "running")


__all__ = ["StoppingDecision", "StoppingPolicy", "evaluate_stopping_conditions"]

"""Stopping-condition records for evolution pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..models import require_mapping, require_non_negative_int


@dataclass(frozen=True)
class StoppingPolicy:
    """Configured stopping limits.

    ``patience=None`` preserves the v0.3.x compatibility behavior: a reported
    no-improvement condition stops immediately. An explicit integer opts into
    governed patience. With ``patience=N``, exactly ``N`` consecutive
    non-improving generations are allowed and the next one stops the run;
    therefore ``patience=0`` stops on the first non-improving generation.
    """

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

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "StoppingPolicy":
        """Build a stopping policy from a JSON-safe mapping."""
        data = require_mapping(mapping, "stopping_policy")
        return cls(
            max_generations=data.get("max_generations"),  # type: ignore[arg-type]
            patience=data.get("patience"),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ThresholdPatienceState:
    """Independent patience state for one threshold trajectory."""

    threshold_id: str
    consecutive_no_improvement: int = 0
    last_improvement_generation: int | None = None
    exhausted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.threshold_id, str) or not self.threshold_id.strip():
            raise ValueError("threshold_id must be a non-empty string.")
        object.__setattr__(self, "threshold_id", self.threshold_id.strip())
        object.__setattr__(
            self,
            "consecutive_no_improvement",
            require_non_negative_int(
                self.consecutive_no_improvement,
                "consecutive_no_improvement",
            ),
        )
        if self.last_improvement_generation is not None:
            object.__setattr__(
                self,
                "last_improvement_generation",
                require_non_negative_int(
                    self.last_improvement_generation,
                    "last_improvement_generation",
                ),
            )
        if type(self.exhausted) is not bool:
            raise ValueError("exhausted must be a boolean.")

    @classmethod
    def from_mapping(
        cls,
        threshold_id: str,
        mapping: Mapping[str, Any],
    ) -> "ThresholdPatienceState":
        """Build threshold patience state from JSON-safe data."""
        data = require_mapping(mapping, f"threshold_states[{threshold_id!r}]")
        return cls(
            threshold_id=threshold_id,
            consecutive_no_improvement=data.get("consecutive_no_improvement", 0),  # type: ignore[arg-type]
            last_improvement_generation=data.get("last_improvement_generation"),  # type: ignore[arg-type]
            exhausted=data.get("exhausted", False),  # type: ignore[arg-type]
        )

    def update(
        self,
        *,
        generation_index: int,
        improved: bool,
        patience: int,
    ) -> "ThresholdPatienceState":
        """Return updated state after one trajectory decision."""
        generation = require_non_negative_int(generation_index, "generation_index")
        if improved:
            return ThresholdPatienceState(
                threshold_id=self.threshold_id,
                consecutive_no_improvement=0,
                last_improvement_generation=generation,
                exhausted=False,
            )
        consecutive = self.consecutive_no_improvement + 1
        return ThresholdPatienceState(
            threshold_id=self.threshold_id,
            consecutive_no_improvement=consecutive,
            last_improvement_generation=self.last_improvement_generation,
            exhausted=consecutive > patience,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe threshold patience state."""
        return {
            "threshold_id": self.threshold_id,
            "consecutive_no_improvement": self.consecutive_no_improvement,
            "last_improvement_generation": self.last_improvement_generation,
            "exhausted": self.exhausted,
        }


@dataclass(frozen=True)
class StoppingState:
    """State needed to make governed stopping decisions reproducible."""

    consecutive_no_improvement: int = 0
    last_improvement_generation: int | None = None
    patience_exhausted: bool = False
    threshold_states: dict[str, ThresholdPatienceState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "consecutive_no_improvement",
            require_non_negative_int(
                self.consecutive_no_improvement,
                "consecutive_no_improvement",
            ),
        )
        if self.last_improvement_generation is not None:
            object.__setattr__(
                self,
                "last_improvement_generation",
                require_non_negative_int(
                    self.last_improvement_generation,
                    "last_improvement_generation",
                ),
            )
        if type(self.patience_exhausted) is not bool:
            raise ValueError("patience_exhausted must be a boolean.")
        states: dict[str, ThresholdPatienceState] = {}
        for key, value in dict(self.threshold_states).items():
            threshold_id = str(key)
            if isinstance(value, ThresholdPatienceState):
                state = value
            else:
                state = ThresholdPatienceState.from_mapping(threshold_id, value)  # type: ignore[arg-type]
            states[threshold_id] = state
        object.__setattr__(self, "threshold_states", states)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | None) -> "StoppingState":
        """Build persisted stopping state from JSON-safe data."""
        if mapping is None:
            return cls()
        data = require_mapping(mapping, "stopping_state")
        threshold_payload = data.get("threshold_states", {})
        if not isinstance(threshold_payload, Mapping):
            raise ValueError("threshold_states must be a mapping.")
        return cls(
            consecutive_no_improvement=data.get("consecutive_no_improvement", 0),  # type: ignore[arg-type]
            last_improvement_generation=data.get("last_improvement_generation"),  # type: ignore[arg-type]
            patience_exhausted=data.get("patience_exhausted", False),  # type: ignore[arg-type]
            threshold_states={
                str(key): ThresholdPatienceState.from_mapping(str(key), value)
                for key, value in threshold_payload.items()
            },
        )

    def update(
        self,
        *,
        generation_index: int,
        improved: bool,
        patience: int,
        threshold_improvements: Mapping[str, bool] | None = None,
    ) -> "StoppingState":
        """Return updated global and threshold patience state."""
        generation = require_non_negative_int(generation_index, "generation_index")
        if improved:
            consecutive = 0
            last_improvement = generation
            exhausted = False
        else:
            consecutive = self.consecutive_no_improvement + 1
            last_improvement = self.last_improvement_generation
            exhausted = consecutive > patience

        threshold_states = dict(self.threshold_states)
        if threshold_improvements is not None:
            for threshold_id, threshold_improved in sorted(threshold_improvements.items()):
                previous = threshold_states.get(str(threshold_id)) or ThresholdPatienceState(str(threshold_id))
                threshold_states[str(threshold_id)] = previous.update(
                    generation_index=generation,
                    improved=bool(threshold_improved),
                    patience=patience,
                )

        return StoppingState(
            consecutive_no_improvement=consecutive,
            last_improvement_generation=last_improvement,
            patience_exhausted=exhausted,
            threshold_states=threshold_states,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe stopping state."""
        return {
            "consecutive_no_improvement": self.consecutive_no_improvement,
            "last_improvement_generation": self.last_improvement_generation,
            "patience_exhausted": self.patience_exhausted,
            "threshold_states": {
                key: state.to_dict()
                for key, state in sorted(self.threshold_states.items())
            },
        }


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
    patience_state: StoppingState | Mapping[str, Any] | None = None,
    threshold_improvements: Mapping[str, bool] | None = None,
    consume_patience: bool = True,
    execution_budget_exhausted: bool = False,
    cancelled: bool = False,
    failed: bool = False,
) -> StoppingDecision:
    """Evaluate common stopping states without running evolution work."""
    generation = require_non_negative_int(generation_index, "generation_index")
    state = (
        patience_state
        if isinstance(patience_state, StoppingState)
        else StoppingState.from_mapping(patience_state)
    )
    if failed:
        return _decision(True, "failure_reported", "failed", generation, policy, state)
    if cancelled:
        return _decision(True, "cancelled", "cancelled", generation, policy, state)
    if candidate_count <= 0:
        return _decision(True, "no_candidates", "completed", generation, policy, state)
    if analysis_result_count <= 0:
        return _decision(True, "no_analysis_results", "failed", generation, policy, state)
    if survivor_count <= 0:
        return _decision(True, "no_survivors", "completed", generation, policy, state)
    if duplicate_only:
        return _decision(True, "duplicate_only_generation", "completed", generation, policy, state)
    if execution_budget_exhausted:
        return _decision(True, "execution_budget_exhausted", "completed", generation, policy, state)
    if policy.patience is None and not strict_improvement:
        return _decision(
            True,
            "no_strict_improvement",
            "completed",
            generation,
            policy,
            state,
            metadata={"patience_enabled": False},
        )
    if generation >= policy.max_generations:
        return _decision(True, "max_generations_reached", "completed", generation, policy, state)

    if not consume_patience:
        threshold_states = dict(state.threshold_states)
        if threshold_improvements is not None:
            for threshold_id in sorted(threshold_improvements):
                threshold_states.setdefault(
                    str(threshold_id),
                    ThresholdPatienceState(str(threshold_id)),
                )
        initialized = StoppingState(
            consecutive_no_improvement=state.consecutive_no_improvement,
            last_improvement_generation=state.last_improvement_generation,
            patience_exhausted=state.patience_exhausted,
            threshold_states=threshold_states,
        )
        return _decision(
            False,
            "continue",
            "running",
            generation,
            policy,
            initialized,
            metadata={
                "patience_enabled": policy.patience is not None,
                "patience_consumed": False,
                "threshold_governed": threshold_improvements is not None,
                "exhausted_thresholds": [
                    threshold_id
                    for threshold_id, threshold_state in sorted(
                        initialized.threshold_states.items()
                    )
                    if threshold_state.exhausted
                ],
            },
        )

    if policy.patience is None:
        return _decision(
            False,
            "continue",
            "running",
            generation,
            policy,
            state,
            metadata={"patience_enabled": False},
        )

    updated = state.update(
        generation_index=generation,
        improved=bool(strict_improvement),
        patience=policy.patience,
        threshold_improvements=threshold_improvements,
    )
    exhausted_thresholds = tuple(
        threshold_id
        for threshold_id, threshold_state in sorted(updated.threshold_states.items())
        if threshold_state.exhausted
    )
    threshold_governed = threshold_improvements is not None
    patience_exhausted = (
        bool(updated.threshold_states)
        and len(exhausted_thresholds) == len(updated.threshold_states)
        if threshold_governed
        else updated.patience_exhausted
    )
    if patience_exhausted:
        return _decision(
            True,
            "patience_exhausted",
            "completed",
            generation,
            policy,
            updated,
            metadata={
                "patience_enabled": True,
                "threshold_governed": threshold_governed,
                "exhausted_thresholds": list(exhausted_thresholds),
            },
        )
    return _decision(
        False,
        "continue",
        "running",
        generation,
        policy,
        updated,
        metadata={
            "patience_enabled": True,
            "threshold_governed": threshold_governed,
            "exhausted_thresholds": list(exhausted_thresholds),
        },
    )


def _decision(
    should_stop: bool,
    reason: str,
    status: str,
    generation_index: int,
    policy: StoppingPolicy,
    state: StoppingState,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> StoppingDecision:
    payload = {
        "generation_index": generation_index,
        "stopping_policy": policy.to_dict(),
        "stopping_state": state.to_dict(),
        "patience_semantics": (
            "patience=None preserves immediate no-improvement stopping; "
            "with patience=N, exactly N consecutive non-improving generations "
            "are allowed and the next one stops the run."
        ),
        **dict(metadata or {}),
    }
    return StoppingDecision(should_stop, reason, status, payload)


__all__ = [
    "StoppingDecision",
    "StoppingPolicy",
    "StoppingState",
    "ThresholdPatienceState",
    "evaluate_stopping_conditions",
]

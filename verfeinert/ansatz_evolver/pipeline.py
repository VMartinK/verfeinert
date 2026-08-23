"""State-machine helpers for building EvolutionRun documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .config import EvolverConfig
from .evaluation import ingest_analysis_results
from .models import (
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    GenerationRecord,
    require_non_negative_int,
    require_supported,
    utc_now_iso,
)
from .policies import StoppingDecision


EVOLUTION_LIFECYCLE_STATES = (
    "initialized",
    "generation_planned",
    "candidates_generated",
    "analysis_pending",
    "analysis_complete",
    "selection_complete",
    "checkpointed",
    "completed",
    "failed",
    "cancelled",
)
TERMINAL_LIFECYCLE_STATES = ("completed", "failed", "cancelled")
PENDING_GENERATION_LIFECYCLE_STATES = (
    "generation_planned",
    "candidates_generated",
    "analysis_pending",
    "analysis_complete",
    "selection_complete",
)


class EvolutionStateMachineError(ValueError):
    """Raised when an evolution lifecycle transition is invalid."""


def evolution_execution_metadata(
    generations: Sequence[GenerationRecord],
) -> dict[str, Any]:
    """Return truthful execution metadata derived from generation records."""
    generation_tuple = tuple(generations)
    return {
        "analysis_requested": any(generation.analysis_result_refs for generation in generation_tuple),
        "analysis_results_ingested": any(generation.analysis_result_refs for generation in generation_tuple),
        "selection_executed": any(
            generation.survivor_refs or generation.rejected_refs
            for generation in generation_tuple
        ),
        "generation_count": len(generation_tuple),
    }


def build_analyzed_generation_record(
    *,
    generation_index: int,
    candidate_refs: Sequence[CandidateRef],
    analysis_result_documents: Sequence[Mapping[str, Any]],
    selection: Any,
    analysis_uris: Mapping[str, str] | None = None,
    parent_refs: Sequence[CandidateRef] = (),
    generation_configuration: Mapping[str, Any] | None = None,
    extra_events: Sequence[EvolutionEvent] = (),
    stopping_decision: StoppingDecision | None = None,
    analysis_event_type: str = "evolver_generation_analyzed",
    selection_event_type: str = "evolver_selection_completed",
    stopping_event_type: str = "evolver_stopping_decision",
) -> GenerationRecord:
    """Build one analyzed generation through the evolver-owned boundary."""
    candidate_tuple = tuple(candidate_refs)
    ingestion = ingest_analysis_results(
        candidate_tuple,
        analysis_result_documents,
        uri_by_analysis_result_id=analysis_uris or {},
    )
    if ingestion.missing_candidate_ids or ingestion.unexpected_candidate_ids:
        raise EvolutionStateMachineError(
            "analysis results do not match evolution candidates: "
            f"missing={list(ingestion.missing_candidate_ids)}, "
            f"unexpected={list(ingestion.unexpected_candidate_ids)}",
        )
    configuration = dict(generation_configuration or {})
    configuration.setdefault("selection", getattr(selection, "configuration", {}))
    events = [
        EvolutionEvent(
            event_type=analysis_event_type,
            status="completed",
            metadata={
                "candidate_count": len(candidate_tuple),
                "analysis_result_count": len(tuple(analysis_result_documents)),
            },
        ),
        EvolutionEvent(
            event_type=selection_event_type,
            policy_id=getattr(selection, "policy_id", None),
            status="completed",
        ),
        *tuple(extra_events),
    ]
    if stopping_decision is not None:
        configuration["stopping"] = stopping_decision.to_dict()
        events.append(
            EvolutionEvent(
                event_type=stopping_event_type,
                status=stopping_decision.status,
                reason=stopping_decision.reason,
                metadata=stopping_decision.to_dict(),
            ),
        )
    return GenerationRecord(
        generation_index=generation_index,
        candidate_refs=candidate_tuple,
        parent_refs=tuple(parent_refs),
        survivor_refs=tuple(getattr(selection, "survivor_refs", ())),
        rejected_refs=tuple(getattr(selection, "rejected_refs", ())),
        archive_refs=tuple(getattr(selection, "archive_refs", ())),
        analysis_result_refs=ingestion.analysis_result_refs,
        configuration=configuration,
        events=tuple(events),
    )


@dataclass(frozen=True)
class EvolutionStateMachine:
    """Own legal generation-state transitions for one EvolutionRun."""

    run_state: EvolutionRunState
    lifecycle_state: str = "initialized"
    pending_generation_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_state, EvolutionRunState):
            raise TypeError("run_state must be an EvolutionRunState.")
        lifecycle = require_supported(
            self.lifecycle_state,
            "lifecycle_state",
            EVOLUTION_LIFECYCLE_STATES,
        )
        object.__setattr__(self, "lifecycle_state", lifecycle)
        if self.pending_generation_index is not None:
            object.__setattr__(
                self,
                "pending_generation_index",
                require_non_negative_int(
                    self.pending_generation_index,
                    "pending_generation_index",
                ),
            )
        if (
            lifecycle not in PENDING_GENERATION_LIFECYCLE_STATES
            and self.pending_generation_index is not None
        ):
            raise EvolutionStateMachineError(
                "pending_generation_index is only valid while a generation is pending.",
            )
        if self.run_state.status in TERMINAL_LIFECYCLE_STATES and lifecycle != self.run_state.status:
            raise EvolutionStateMachineError(
                "terminal EvolutionRunState status must match lifecycle_state.",
            )

    @classmethod
    def start(
        cls,
        *,
        evolution_run_id: str,
        configuration: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
        created_at: str | None = None,
        git_commit: str | None = None,
    ) -> "EvolutionStateMachine":
        """Create a running state machine with no generations yet."""
        created = created_at or utc_now_iso()
        run_state = EvolutionRunState(
            evolution_run_id=evolution_run_id,
            status="running",
            configuration=dict(configuration),
            generations=(),
            provenance={
                "created_at": created,
                "source": "verfeinert.ansatz_evolver.state_machine",
                "input_hashes": {},
                **dict(provenance or {}),
            },
            metadata=dict(metadata or {}),
            created_at=created,
            git_commit=git_commit,
            execution_metadata=evolution_execution_metadata(()),
        )
        return cls(run_state=run_state, lifecycle_state="initialized")

    @classmethod
    def from_run_state(
        cls,
        state: EvolutionRunState,
        *,
        lifecycle_state: str = "checkpointed",
    ) -> "EvolutionStateMachine":
        """Resume a state machine from an existing run state."""
        if state.status in TERMINAL_LIFECYCLE_STATES and lifecycle_state == "checkpointed":
            lifecycle_state = state.status
        return cls(run_state=state, lifecycle_state=lifecycle_state)

    @property
    def expected_next_generation_index(self) -> int:
        """Return the only legal next generation index."""
        if not self.run_state.generations:
            return 0
        return self.run_state.generations[-1].generation_index + 1

    def plan_generation(self, generation_index: int | None = None) -> "EvolutionStateMachine":
        """Move to generation_planned for the expected next generation."""
        self._require_not_terminal()
        if self.lifecycle_state in PENDING_GENERATION_LIFECYCLE_STATES:
            raise EvolutionStateMachineError("a generation is already planned.")
        expected = self.expected_next_generation_index
        planned = expected if generation_index is None else require_non_negative_int(
            generation_index,
            "generation_index",
        )
        if planned != expected:
            raise EvolutionStateMachineError(
                f"generation_index must be {expected}; got {planned}.",
            )
        return EvolutionStateMachine(
            run_state=self.run_state,
            lifecycle_state="generation_planned",
            pending_generation_index=planned,
        )

    def record_candidates_generated(self) -> "EvolutionStateMachine":
        """Record that candidate refs/documents were produced for a plan."""
        return self._advance_pending_generation(
            from_state="generation_planned",
            to_state="candidates_generated",
        )

    def request_analysis(self) -> "EvolutionStateMachine":
        """Record that generated candidates are awaiting analysis."""
        return self._advance_pending_generation(
            from_state="candidates_generated",
            to_state="analysis_pending",
        )

    def record_analysis_complete(self) -> "EvolutionStateMachine":
        """Record that analysis refs are available for the pending generation."""
        return self._advance_pending_generation(
            from_state="analysis_pending",
            to_state="analysis_complete",
        )

    def record_selection_complete(self) -> "EvolutionStateMachine":
        """Record that survivor/archive decisions are available."""
        return self._advance_pending_generation(
            from_state="analysis_complete",
            to_state="selection_complete",
        )

    def append_generation(self, generation: GenerationRecord) -> "EvolutionStateMachine":
        """Append one completed generation and checkpoint the state."""
        self._require_not_terminal()
        if not isinstance(generation, GenerationRecord):
            raise TypeError("generation must be a GenerationRecord.")
        expected = self.expected_next_generation_index
        if generation.generation_index != expected:
            raise EvolutionStateMachineError(
                f"generation_index must be {expected}; got {generation.generation_index}.",
            )
        if (
            self.lifecycle_state in PENDING_GENERATION_LIFECYCLE_STATES
            and self.pending_generation_index != generation.generation_index
        ):
            raise EvolutionStateMachineError(
                "pending generation index does not match appended generation.",
            )
        generations = (*self.run_state.generations, generation)
        run_state = EvolutionRunState(
            evolution_run_id=self.run_state.evolution_run_id,
            status="running",
            configuration=self.run_state.configuration,
            generations=generations,
            provenance=self.run_state.provenance,
            metadata=self.run_state.metadata,
            created_at=self.run_state.created_at,
            software_version=self.run_state.software_version,
            git_commit=self.run_state.git_commit,
            execution_metadata=evolution_execution_metadata(generations),
        )
        return EvolutionStateMachine(run_state=run_state, lifecycle_state="checkpointed")

    def complete(self, *, metadata: Mapping[str, Any] | None = None) -> "EvolutionStateMachine":
        """Mark the run completed from a legal non-terminal boundary."""
        return self._terminal("completed", metadata=metadata)

    def fail(self, *, metadata: Mapping[str, Any] | None = None) -> "EvolutionStateMachine":
        """Mark the run failed from a legal non-terminal boundary."""
        return self._terminal("failed", metadata=metadata)

    def cancel(self, *, metadata: Mapping[str, Any] | None = None) -> "EvolutionStateMachine":
        """Mark the run cancelled from a legal non-terminal boundary."""
        return self._terminal("cancelled", metadata=metadata)

    def to_run_state(self) -> EvolutionRunState:
        """Return the current EvolutionRunState."""
        return self.run_state

    def _terminal(
        self,
        status: str,
        *,
        metadata: Mapping[str, Any] | None,
    ) -> "EvolutionStateMachine":
        self._require_not_terminal()
        if self.lifecycle_state in PENDING_GENERATION_LIFECYCLE_STATES:
            raise EvolutionStateMachineError("cannot finalize with a planned generation pending.")
        run_state = EvolutionRunState(
            evolution_run_id=self.run_state.evolution_run_id,
            status=status,  # type: ignore[arg-type]
            configuration=self.run_state.configuration,
            generations=self.run_state.generations,
            provenance=self.run_state.provenance,
            metadata=dict(self.run_state.metadata if metadata is None else metadata),
            created_at=self.run_state.created_at,
            software_version=self.run_state.software_version,
            git_commit=self.run_state.git_commit,
            execution_metadata=evolution_execution_metadata(self.run_state.generations),
        )
        return EvolutionStateMachine(run_state=run_state, lifecycle_state=status)

    def _require_not_terminal(self) -> None:
        if self.lifecycle_state in TERMINAL_LIFECYCLE_STATES:
            raise EvolutionStateMachineError(
                f"cannot transition from terminal state {self.lifecycle_state!r}.",
            )

    def _advance_pending_generation(
        self,
        *,
        from_state: str,
        to_state: str,
    ) -> "EvolutionStateMachine":
        self._require_not_terminal()
        if self.lifecycle_state != from_state:
            raise EvolutionStateMachineError(
                f"cannot transition from {self.lifecycle_state!r} to {to_state!r}.",
            )
        return EvolutionStateMachine(
            run_state=self.run_state,
            lifecycle_state=to_state,
            pending_generation_index=self.pending_generation_index,
        )


@dataclass(frozen=True)
class EvolutionPipelineState:
    """Append-only state wrapper around reference-based generation records."""

    config: EvolverConfig
    status: str = "planned"
    generations: tuple[GenerationRecord, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    events: tuple[EvolutionEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.config, EvolverConfig):
            raise TypeError("config must be an EvolverConfig.")
        generations = tuple(self.generations)
        if any(not isinstance(generation, GenerationRecord) for generation in generations):
            raise TypeError("generations must contain GenerationRecord objects.")
        object.__setattr__(self, "generations", generations)
        events = tuple(self.events)
        if any(not isinstance(event, EvolutionEvent) for event in events):
            raise TypeError("events must contain EvolutionEvent objects.")
        object.__setattr__(self, "events", events)

    def with_generation(self, generation: GenerationRecord) -> "EvolutionPipelineState":
        """Return a new state with one generation appended."""
        machine = EvolutionStateMachine.from_run_state(
            self.to_run_state(),
            lifecycle_state="checkpointed" if self.generations else "initialized",
        ).append_generation(generation)
        return EvolutionPipelineState(
            config=self.config,
            status=self.status,
            generations=machine.run_state.generations,
            metadata=dict(self.metadata),
            events=self.events,
        )

    def to_run_state(self) -> EvolutionRunState:
        """Return an EvolutionRunState ready for export."""
        return EvolutionRunState(
            evolution_run_id=self.config.run_id,
            status=self.status,  # type: ignore[arg-type]
            configuration=self.config.to_evolution_configuration(),
            generations=self.generations,
            provenance={
                "created_at": utc_now_iso(),
                "source": "verfeinert.ansatz_evolver.pipeline",
                "input_hashes": {},
            },
            metadata=dict(self.metadata),
            execution_metadata=evolution_execution_metadata(self.generations),
        )


__all__ = [
    "EVOLUTION_LIFECYCLE_STATES",
    "EvolutionPipelineState",
    "EvolutionStateMachine",
    "EvolutionStateMachineError",
    "build_analyzed_generation_record",
    "evolution_execution_metadata",
]

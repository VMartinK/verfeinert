"""Small state helpers for building EvolutionRun documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import EvolverConfig
from .models import EvolutionEvent, EvolutionRunState, GenerationRecord, utc_now_iso


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
        if not isinstance(generation, GenerationRecord):
            raise TypeError("generation must be a GenerationRecord.")
        return EvolutionPipelineState(
            config=self.config,
            status=self.status,
            generations=(*self.generations, generation),
            metadata=dict(self.metadata),
            events=self.events,
        )

    def to_run_state(self) -> EvolutionRunState:
        """Return an EvolutionRunState ready for export."""
        execution_metadata = {
            "analysis_requested": any(generation.analysis_result_refs for generation in self.generations),
            "analysis_results_ingested": any(generation.analysis_result_refs for generation in self.generations),
            "selection_executed": any(generation.survivor_refs or generation.rejected_refs for generation in self.generations),
        }
        return EvolutionRunState(
            evolution_run_id=self.config.run_id,
            status=self.status,
            configuration=self.config.to_evolution_configuration(),
            generations=self.generations,
            provenance={
                "created_at": utc_now_iso(),
                "source": "verfeinert.ansatz_evolver.pipeline",
                "input_hashes": {},
            },
            metadata=dict(self.metadata),
            execution_metadata=execution_metadata,
        )


__all__ = ["EvolutionPipelineState"]

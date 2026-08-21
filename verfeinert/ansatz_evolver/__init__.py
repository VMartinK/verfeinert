"""JSON-first ansatz evolution tools for Verfeinert."""

from .candidate_factory import CandidateFactory, produce_candidate_from_request
from .config import EvolverConfig, EvolverExecutionPermissions
from .io import (
    read_analysis_result_json,
    read_candidate_json,
    read_evolution_run_json,
    read_staged_package_json,
)
from .mutation import (
    MutationPolicy,
    MutationRecipe,
    MutationRequest,
    build_mutation_requests,
    expand_mutation_requests,
)
from .models import (
    AnalysisResultRef,
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    GenerationRecord,
)
from .policies import (
    StoppingDecision,
    StoppingPolicy,
    StoppingState,
    ThresholdPatienceState,
    evaluate_stopping_conditions,
)
from .pipeline import (
    EVOLUTION_LIFECYCLE_STATES,
    EvolutionPipelineState,
    EvolutionStateMachine,
    EvolutionStateMachineError,
    build_analyzed_generation_record,
    evolution_execution_metadata,
)
from .exporters import export_evolution_run_json, write_evolution_run_json
from .validation import (
    EvolverValidationError,
    validate_analysis_result_document,
    validate_candidate_document,
    validate_evolution_run_document,
    validate_staged_package_document,
)

__all__ = [
    "AnalysisResultRef",
    "CandidateFactory",
    "CandidateRef",
    "EVOLUTION_LIFECYCLE_STATES",
    "EvolutionEvent",
    "EvolutionRunState",
    "EvolutionPipelineState",
    "EvolutionStateMachine",
    "EvolutionStateMachineError",
    "EvolverConfig",
    "EvolverExecutionPermissions",
    "EvolverValidationError",
    "GenerationRecord",
    "MutationPolicy",
    "MutationRecipe",
    "MutationRequest",
    "StoppingDecision",
    "StoppingPolicy",
    "StoppingState",
    "ThresholdPatienceState",
    "build_mutation_requests",
    "build_analyzed_generation_record",
    "evaluate_stopping_conditions",
    "evolution_execution_metadata",
    "expand_mutation_requests",
    "export_evolution_run_json",
    "produce_candidate_from_request",
    "read_analysis_result_json",
    "read_candidate_json",
    "read_evolution_run_json",
    "read_staged_package_json",
    "validate_analysis_result_document",
    "validate_candidate_document",
    "validate_evolution_run_document",
    "validate_staged_package_document",
    "write_evolution_run_json",
]

"""Interactive (live) evolution engine, VQE validation and local web UI."""

from .engine import (
    LiveEngineError,
    LiveEvolutionEngine,
    LiveRunCancelled,
    LiveRunConfig,
    evaluate_candidate_document,
    run_live_evolution,
    template_catalog,
)
from .vqe import OPTIMIZER_SPECS, OPTIMIZERS, OptimizerSpec, VQECancelled, VQEConfig, optimizer_catalog, run_vqe

__all__ = [
    "OPTIMIZERS",
    "OPTIMIZER_SPECS",
    "LiveEngineError",
    "LiveEvolutionEngine",
    "LiveRunCancelled",
    "LiveRunConfig",
    "OptimizerSpec",
    "VQECancelled",
    "VQEConfig",
    "evaluate_candidate_document",
    "optimizer_catalog",
    "run_live_evolution",
    "run_vqe",
    "template_catalog",
]

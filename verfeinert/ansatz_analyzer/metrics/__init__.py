"""Analyzer metric implementations available in the foundation slice."""

from .expressibility import (
    BIN_STRATEGIES,
    ExpressibilityConfig,
    compute_expressibility_metric,
    haar_bin_edges,
    haar_bin_masses,
    kl_divergence,
)
from .hamiltonians import (
    DEFAULT_HAMILTONIAN_PARAMETERS,
    HAMILTONIAN_KINDS,
    HamiltonianError,
    HamiltonianSpec,
    hamiltonian_catalog,
    normalize_hamiltonian_kind,
)
from .protocol import (
    PAPER_COST_WEIGHTS,
    PAPER_VQE,
    PROTOCOL_NAMES,
    apply_protocol_to_workflow_mapping,
    protocol_metric_configs,
    protocol_pareto,
    protocol_ranking,
    protocol_structural_cost,
    protocol_summary,
)
from .structural_cost import (
    StructuralCostAnalysis,
    StructuralFeatures,
    compute_structural_cost,
    compute_structural_costs,
)
from .trainability import (
    TrainabilityConfig,
    compute_trainability_metric,
    energy_from_state,
    energy_from_state_local_x,
    make_local_x_hamiltonian_matrix,
    make_trainability_hamiltonian_matrix,
)

__all__ = [
    "BIN_STRATEGIES",
    "DEFAULT_HAMILTONIAN_PARAMETERS",
    "ExpressibilityConfig",
    "HAMILTONIAN_KINDS",
    "HamiltonianError",
    "HamiltonianSpec",
    "PAPER_COST_WEIGHTS",
    "PAPER_VQE",
    "PROTOCOL_NAMES",
    "StructuralCostAnalysis",
    "StructuralFeatures",
    "TrainabilityConfig",
    "apply_protocol_to_workflow_mapping",
    "compute_structural_cost",
    "compute_structural_costs",
    "compute_expressibility_metric",
    "compute_trainability_metric",
    "energy_from_state",
    "energy_from_state_local_x",
    "haar_bin_edges",
    "haar_bin_masses",
    "hamiltonian_catalog",
    "kl_divergence",
    "make_local_x_hamiltonian_matrix",
    "make_trainability_hamiltonian_matrix",
    "normalize_hamiltonian_kind",
    "protocol_metric_configs",
    "protocol_pareto",
    "protocol_ranking",
    "protocol_structural_cost",
    "protocol_summary",
]

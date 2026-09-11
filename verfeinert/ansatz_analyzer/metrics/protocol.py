"""Manuscript-aligned evaluation protocol presets.

The presets reproduce the sampling protocol of Sanz et al., *Efficiently
Architecting VQAs: Expressibility-Trainability-Resources Pareto-Optimality*:

* expressibility: ``N_pairs = 10000`` fidelity pairs, ``n_bins = 75`` equal-mass
  bins, ``Expr' = -log10(D_KL)``, repeated over independent trials
  (mean +- standard deviation);
* trainability: ``N_s = 3000`` uniformly sampled parameter vectors in
  ``[0, 2*pi)``, average per-parameter gradient variance (Eq. 10), repeated over
  independent trials;
* resource cost: ``alpha, beta, gamma = (0.0894, 0.1966, 0.7140)`` weights on the
  min-max normalized parameter count, depth and two-qubit gate count (IBM
  Kingston / Heron r2 linearized-fidelity model);
* composite score ``Expr x Train``;
* VQE validation: Adam, learning rate 0.05, 200 steps, 5 random restarts and
  the normalized energy error ``|(E - E0) / E0|``.

The ``fast`` preset keeps the same estimators with much smaller sample sizes
for interactive exploration and smoke tests.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .hamiltonians import HamiltonianSpec


PROTOCOL_NAMES = ("paper", "fast")
DEFAULT_PAPER_TRIALS = 5
PAPER_TRIAL_RANGE = (3, 5)

PAPER_EXPRESSIBILITY: dict[str, Any] = {
    "n_pairs": 10000,
    "n_bins": 75,
    "bin_strategy": "equal_mass",
    "parameter_low": 0.0,
    "parameter_high": 2.0 * math.pi,
    "n_trials": DEFAULT_PAPER_TRIALS,
}
PAPER_TRAINABILITY: dict[str, Any] = {
    "n_repeats": 3000,
    "parameter_low": 0.0,
    "parameter_high": 2.0 * math.pi,
    "average_over": "all",
    "n_trials": DEFAULT_PAPER_TRIALS,
}
FAST_EXPRESSIBILITY: dict[str, Any] = {
    "n_pairs": 1000,
    "n_bins": 30,
    "bin_strategy": "equal_mass",
    "parameter_low": 0.0,
    "parameter_high": 2.0 * math.pi,
    "n_trials": 3,
}
FAST_TRAINABILITY: dict[str, Any] = {
    "n_repeats": 300,
    "parameter_low": 0.0,
    "parameter_high": 2.0 * math.pi,
    "average_over": "all",
    "n_trials": 3,
}
PAPER_COST_WEIGHTS: dict[str, float] = {
    "parameter_count": 0.0894,
    "depth": 0.1966,
    "two_qubit_operation_count": 0.7140,
}
PAPER_HARDWARE_MODEL: dict[str, Any] = {
    "processor": "IBM Kingston (Heron r2, 156 qubits)",
    "p_error_1q": 2.464e-4,
    "p_error_2q": 1.969e-3,
    "t1_us": 256.57,
    "t2_star_us": 122.69,
    "layer_time_ns": 68.0,
}
PAPER_VQE: dict[str, Any] = {
    "optimizer": "adam",
    "learning_rate": 0.05,
    "steps": 200,
    "restarts": 5,
}
PAPER_COST_THRESHOLDS = (1.0, 0.2, 0.1)


def protocol_metric_configs(
    protocol: str = "paper",
    *,
    n_trials: int | None = None,
    hamiltonian: str | Mapping[str, Any] | HamiltonianSpec | None = "tfim",
    hamiltonian_parameters: Mapping[str, float] | None = None,
    rng_seed: int | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``analyzer.metric_configs`` for the requested protocol.

    ``n_trials`` defaults to the protocol value (5 for ``paper``); the
    manuscript uses 3-5 independent trials. ``hamiltonian`` selects the
    trainability cost function (``local_x``, ``tfim``/``ising`` or
    ``heisenberg``) and ``hamiltonian_parameters`` its couplings.
    """
    name = str(protocol).strip().lower()
    if name not in PROTOCOL_NAMES:
        raise ValueError(f"protocol must be one of {PROTOCOL_NAMES}.")
    expressibility = dict(PAPER_EXPRESSIBILITY if name == "paper" else FAST_EXPRESSIBILITY)
    trainability = dict(PAPER_TRAINABILITY if name == "paper" else FAST_TRAINABILITY)
    if n_trials is not None:
        if int(n_trials) <= 0:
            raise ValueError("n_trials must be positive.")
        expressibility["n_trials"] = int(n_trials)
        trainability["n_trials"] = int(n_trials)
    spec = HamiltonianSpec.from_mapping(hamiltonian if hamiltonian is not None else "local_x")
    if hamiltonian_parameters:
        spec = HamiltonianSpec(
            kind=spec.kind,
            parameters={**spec.parameters, **dict(hamiltonian_parameters)},
            boundary=spec.boundary,
        )
    trainability["hamiltonian"] = spec.kind
    trainability["hamiltonian_parameters"] = dict(spec.parameters)
    trainability["hamiltonian_boundary"] = spec.boundary
    if rng_seed is not None:
        expressibility["rng_seed"] = int(rng_seed)
        trainability["rng_seed"] = int(rng_seed)
    configs = {"expressibility": expressibility, "trainability": trainability}
    for metric_name, payload in dict(overrides or {}).items():
        if metric_name not in configs:
            raise ValueError(f"unknown metric override {metric_name!r}.")
        configs[metric_name].update(dict(payload))
    return configs


def protocol_structural_cost(reference_id: str = "paper-family") -> dict[str, Any]:
    """Return an ``analyzer.structural_cost`` mapping with manuscript weights.

    Reference bounds are intentionally left unset so that min-max
    normalization is derived from the analyzed family for any qubit count.
    """
    return {
        "reference_id": reference_id,
        "component_weights": dict(PAPER_COST_WEIGHTS),
        "allow_operation_count_as_depth_proxy": True,
    }


def protocol_ranking() -> dict[str, Any]:
    """Return the composite ``Expr x Train`` ranking configuration."""
    return {
        "score_components": {"expressibility": 1.0, "trainability": 1.0},
        "combination": "product",
        "ascending": False,
    }


def protocol_pareto(cost_thresholds=PAPER_COST_THRESHOLDS) -> dict[str, Any]:
    """Return the expressibility/trainability Pareto configuration."""
    return {
        "objectives": [
            {"metric_name": "expressibility", "direction": "maximize"},
            {"metric_name": "trainability", "direction": "maximize"},
        ],
        "cost_thresholds": list(cost_thresholds),
    }


def protocol_summary(protocol: str = "paper") -> dict[str, Any]:
    """Return a JSON-safe description of a protocol preset (for UIs/docs)."""
    configs = protocol_metric_configs(protocol)
    return {
        "protocol": protocol,
        "expressibility": configs["expressibility"],
        "trainability": {
            key: value
            for key, value in configs["trainability"].items()
            if not key.startswith("hamiltonian")
        },
        "cost_weights": dict(PAPER_COST_WEIGHTS),
        "hardware_model": dict(PAPER_HARDWARE_MODEL),
        "score": "expressibility * trainability",
        "vqe": dict(PAPER_VQE),
        "trial_range": list(PAPER_TRIAL_RANGE),
    }


def apply_protocol_to_workflow_mapping(
    mapping: Mapping[str, Any],
    *,
    protocol: str | None = None,
    n_qubits: int | None = None,
    n_trials: int | None = None,
    hamiltonian: str | None = None,
    hamiltonian_parameters: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return a workflow mapping with protocol/qubit/Hamiltonian overrides applied.

    Only the requested pieces are touched: ``generation.n_qubits`` when
    ``n_qubits`` is given, ``analyzer.metric_configs`` when a protocol, trial
    count or Hamiltonian is given, and the structural-cost weights, ranking and
    Pareto blocks only when a protocol preset is requested and the workflow does
    not already define them.
    """
    result = dict(mapping)
    if n_qubits is not None:
        generation = dict(result.get("generation", {}))
        generation["n_qubits"] = int(n_qubits)
        constraints = generation.get("constraints")
        if isinstance(constraints, Mapping) and isinstance(constraints.get("connectivity"), Mapping):
            connectivity = dict(constraints["connectivity"])
            connectivity["n_qubits"] = int(n_qubits)
            generation["constraints"] = {**dict(constraints), "connectivity": connectivity}
        result["generation"] = generation
    touches_metrics = any(item is not None for item in (protocol, n_trials, hamiltonian, hamiltonian_parameters))
    if not touches_metrics:
        return result
    analyzer = dict(result.get("analyzer", {}))
    existing = dict(analyzer.get("metric_configs", {}))
    existing_trainability = dict(existing.get("trainability", {}) or {})
    base_hamiltonian = hamiltonian or existing_trainability.get("hamiltonian") or existing_trainability.get("hamiltonian_kind") or "local_x"
    base_parameters = dict(existing_trainability.get("hamiltonian_parameters", {}) or {})
    if hamiltonian is not None and hamiltonian != existing_trainability.get("hamiltonian"):
        base_parameters = {}
    if hamiltonian_parameters:
        base_parameters.update(dict(hamiltonian_parameters))
    if protocol is not None:
        configs = protocol_metric_configs(
            protocol,
            n_trials=n_trials,
            hamiltonian=base_hamiltonian,
            hamiltonian_parameters=base_parameters,
            rng_seed=existing_trainability.get("rng_seed"),
        )
        for metric_name in ("expressibility", "trainability"):
            merged = dict(existing.get(metric_name, {}) or {})
            merged.pop("hamiltonian_kind", None)
            merged.pop("hamiltonian_scale", None)
            merged.update(configs[metric_name])
            existing[metric_name] = merged
        analyzer.setdefault("structural_cost", protocol_structural_cost())
        analyzer.setdefault("ranking", protocol_ranking())
        analyzer.setdefault("pareto", protocol_pareto())
        selected = list(analyzer.get("selected_metrics", ["structural_cost"]))
        for metric_name in ("structural_cost", "expressibility", "trainability"):
            if metric_name not in selected:
                selected.append(metric_name)
        analyzer["selected_metrics"] = selected
        permissions = dict(analyzer.get("permissions", {}))
        permissions.setdefault("allow_expensive_metrics", True)
        permissions.setdefault("allow_qnode_execution", True)
        analyzer["permissions"] = permissions
        materialization = dict(analyzer.get("materialization", {}))
        materialization.setdefault("enabled", True)
        analyzer["materialization"] = materialization
    else:
        expressibility = dict(existing.get("expressibility", {}) or {})
        trainability = dict(existing_trainability)
        if n_trials is not None:
            expressibility["n_trials"] = int(n_trials)
            trainability["n_trials"] = int(n_trials)
        if hamiltonian is not None or hamiltonian_parameters:
            spec = HamiltonianSpec(kind=base_hamiltonian, parameters=base_parameters)
            trainability.pop("hamiltonian_kind", None)
            trainability.pop("hamiltonian_scale", None)
            trainability["hamiltonian"] = spec.kind
            trainability["hamiltonian_parameters"] = dict(spec.parameters)
        existing["expressibility"] = expressibility
        existing["trainability"] = trainability
    analyzer["metric_configs"] = existing
    result["analyzer"] = analyzer
    return result


__all__ = [
    "DEFAULT_PAPER_TRIALS",
    "FAST_EXPRESSIBILITY",
    "FAST_TRAINABILITY",
    "PAPER_COST_THRESHOLDS",
    "PAPER_COST_WEIGHTS",
    "PAPER_EXPRESSIBILITY",
    "PAPER_HARDWARE_MODEL",
    "PAPER_TRAINABILITY",
    "PAPER_TRIAL_RANGE",
    "PAPER_VQE",
    "PROTOCOL_NAMES",
    "apply_protocol_to_workflow_mapping",
    "protocol_metric_configs",
    "protocol_pareto",
    "protocol_ranking",
    "protocol_structural_cost",
    "protocol_summary",
]

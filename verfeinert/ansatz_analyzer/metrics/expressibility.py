"""V1-aligned expressibility metric over state-vector callables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import time
from typing import Any

import numpy as np

from verfeinert.core.io.serialization import to_json_safe

from ..config import AnalyzerExecutionPermissions
from ..models import CandidateView, MetricRecord
from .runtime import (
    failed_metric,
    permission_denied_metric,
    permissions_allow_metric,
    stable_metric_seed,
)

RNG_POLICIES = ("per_circuit", "global_sequential")
BIN_STRATEGIES = ("equal_width", "equal_mass")
DEFAULT_MAX_BATCH_STATE_ELEMENTS = 2**22


@dataclass(frozen=True)
class ExpressibilityConfig:
    """Configuration for fidelity-sampling expressibility.

    ``n_trials`` repeats the full ``n_pairs`` estimate with independent random
    streams and reports the mean and sample standard deviation across trials,
    following the manuscript protocol (``n_pairs=10000``, ``n_bins=75``,
    ``bin_strategy="equal_mass"``, ``n_trials=5``). ``n_trials=1`` reproduces
    the historical single-estimate behaviour exactly.

    ``bin_strategy`` selects equal-width fidelity bins over ``[0, 1]`` or
    equal-Haar-mass bins (constant estimator bias as ``n_qubits`` grows).

    When the state callable supports parameter broadcasting (automatic
    materialization does), states are evaluated in batches of at most
    ``batch_size`` parameter vectors (auto-sized from
    ``max_batch_state_elements`` when ``None``).
    """

    n_qubits: int | None = None
    n_pairs: int = 5000
    n_bins: int = 75
    parameter_low: float = 0.0
    parameter_high: float = 2.0 * math.pi
    rng_seed: int = 42
    rng_policy: str = "per_circuit"
    dkl_floor: float = 1e-16
    histogram_epsilon: float = 1e-12
    max_total_state_calls: int | None = None
    max_total_qnode_calls: int | None = None
    backend_label: str = "state_callable"
    requires_qnode_execution: bool = False
    bin_strategy: str = "equal_width"
    n_trials: int = 1
    batch_size: int | None = None
    max_batch_state_elements: int = DEFAULT_MAX_BATCH_STATE_ELEMENTS

    def __post_init__(self) -> None:
        if self.n_qubits is not None and int(self.n_qubits) <= 0:
            raise ValueError("n_qubits must be None or a positive integer.")
        if int(self.n_pairs) <= 0:
            raise ValueError("n_pairs must be positive.")
        if int(self.n_bins) <= 1:
            raise ValueError("n_bins must be greater than one.")
        if self.bin_strategy not in BIN_STRATEGIES:
            raise ValueError(f"bin_strategy must be one of {BIN_STRATEGIES}.")
        if int(self.n_trials) <= 0:
            raise ValueError("n_trials must be positive.")
        if self.batch_size is not None and int(self.batch_size) <= 0:
            raise ValueError("batch_size must be None or positive.")
        if int(self.max_batch_state_elements) <= 0:
            raise ValueError("max_batch_state_elements must be positive.")
        if float(self.parameter_high) <= float(self.parameter_low):
            raise ValueError("parameter_high must be greater than parameter_low.")
        if self.rng_policy not in RNG_POLICIES:
            raise ValueError(f"rng_policy must be one of {RNG_POLICIES}.")
        if float(self.dkl_floor) <= 0.0:
            raise ValueError("dkl_floor must be positive.")
        if float(self.histogram_epsilon) <= 0.0:
            raise ValueError("histogram_epsilon must be positive.")
        if self.max_total_state_calls is not None and int(self.max_total_state_calls) <= 0:
            raise ValueError("max_total_state_calls must be None or positive.")
        if self.max_total_qnode_calls is not None and int(self.max_total_qnode_calls) <= 0:
            raise ValueError("max_total_qnode_calls must be None or positive.")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "ExpressibilityConfig":
        """Build config from a parsed mapping (``n_samples`` aliases ``n_pairs``)."""
        data = dict(mapping)
        if "n_samples" in data:
            samples = data.pop("n_samples")
            if "n_pairs" in data and int(data["n_pairs"]) != int(samples):
                raise ValueError("n_pairs and n_samples must match when both are provided.")
            data["n_pairs"] = samples
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe config data."""
        return to_json_safe(self.__dict__)


def compute_expressibility_metric(
    candidate: CandidateView,
    state_callable,
    *,
    config: ExpressibilityConfig | None = None,
    permissions: AnalyzerExecutionPermissions | None = None,
    rng: np.random.Generator | None = None,
    materialized: Any | None = None,
    should_cancel=None,
) -> MetricRecord:
    """Compute expressibility for one candidate using an explicit state callable.

    ``materialized`` may be a :class:`MaterializedCircuit`; when provided and it
    supports parameter broadcasting, states are evaluated in batches. Random
    parameters are always drawn pair by pair, so batched and sequential runs
    yield identical fidelities for the same seed.
    """
    if not isinstance(candidate, CandidateView):
        raise TypeError("candidate must be a CandidateView.")
    resolved = config or ExpressibilityConfig()
    allowed, reason = permissions_allow_metric(
        permissions or AnalyzerExecutionPermissions(),
        metric_name="expressibility",
        requires_qnode_execution=resolved.requires_qnode_execution,
    )
    if not allowed:
        return permission_denied_metric(
            metric_name="expressibility",
            candidate_id=candidate.candidate_id,
            reason=reason or "permission denied",
        )
    estimated_calls = int(2 * resolved.n_pairs * resolved.n_trials)
    call_limit = (
        resolved.max_total_state_calls
        if resolved.max_total_state_calls is not None
        else resolved.max_total_qnode_calls
    )
    if call_limit is not None and estimated_calls > int(call_limit):
        return failed_metric(
            metric_name="expressibility",
            candidate_id=candidate.candidate_id,
            error=(
                "Expressibility workload exceeds call limit: "
                f"estimated={estimated_calls}, limit={call_limit}"
            ),
            metadata={"estimated_state_calls": estimated_calls},
        )
    try:
        return _compute(
            candidate,
            state_callable,
            resolved,
            rng=rng,
            materialized=materialized,
            should_cancel=should_cancel,
        )
    except Exception as exc:
        return failed_metric(
            metric_name="expressibility",
            candidate_id=candidate.candidate_id,
            error=str(exc),
            metadata={"backend": resolved.backend_label},
        )


def haar_bin_edges(n_qubits: int, n_bins: int, *, strategy: str = "equal_width") -> np.ndarray:
    """Return fidelity bin edges over [0, 1] for the requested strategy.

    ``equal_width`` returns ``n_bins + 1`` linearly spaced edges. ``equal_mass``
    returns edges such that every bin carries the same Haar probability mass
    ``1 / n_bins``, using the Haar fidelity CDF ``1 - (1 - F)**(N - 1)``.
    """
    if int(n_qubits) <= 0:
        raise ValueError("n_qubits must be positive.")
    if int(n_bins) <= 1:
        raise ValueError("n_bins must be greater than one.")
    if strategy not in BIN_STRATEGIES:
        raise ValueError(f"strategy must be one of {BIN_STRATEGIES}.")
    if strategy == "equal_width":
        return np.linspace(0.0, 1.0, int(n_bins) + 1)
    dimension = 2 ** int(n_qubits)
    if dimension <= 2:
        return np.linspace(0.0, 1.0, int(n_bins) + 1)
    quantiles = np.linspace(0.0, 1.0, int(n_bins) + 1)
    edges = 1.0 - np.power(1.0 - quantiles, 1.0 / (dimension - 1))
    edges[0] = 0.0
    edges[-1] = 1.0
    return edges


def haar_bin_masses(n_qubits: int, n_bins: int, *, strategy: str = "equal_width") -> list[float]:
    """Return Haar fidelity probability masses for the bins over [0, 1]."""
    if int(n_qubits) <= 0:
        raise ValueError("n_qubits must be positive.")
    if int(n_bins) <= 1:
        raise ValueError("n_bins must be greater than one.")
    dimension = 2 ** int(n_qubits)
    edges = haar_bin_edges(n_qubits, n_bins, strategy=strategy)
    masses = np.array(
        [
            (1.0 - left) ** (dimension - 1)
            - (1.0 - right) ** (dimension - 1)
            for left, right in zip(edges[:-1], edges[1:], strict=True)
        ],
        dtype=float,
    )
    masses = np.clip(masses, 0.0, None)
    total = float(masses.sum())
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("Invalid Haar bin masses.")
    return (masses / total).tolist()


def kl_divergence(
    p_empirical: Sequence[float],
    p_reference: Sequence[float],
    epsilon: float = 1e-12,
) -> float:
    """Compute KL divergence after epsilon clipping and renormalization."""
    if float(epsilon) <= 0.0:
        raise ValueError("epsilon must be positive.")
    p = np.asarray(p_empirical, dtype=float).reshape(-1)
    q = np.asarray(p_reference, dtype=float).reshape(-1)
    if p.shape != q.shape:
        raise ValueError("p_empirical and p_reference must have the same shape.")
    p = np.clip(p, float(epsilon), None)
    q = np.clip(q, float(epsilon), None)
    p /= p.sum()
    q /= q.sum()
    return float(np.sum(p * np.log(p / q)))


def normalize_state_vector(state: Sequence[complex]) -> list[complex]:
    """Return a normalized state vector."""
    vector = np.asarray(state, dtype=complex).reshape(-1)
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 0.0:
        raise ValueError(f"Invalid state norm: {norm}")
    return (vector / norm).tolist()


def _compute(
    candidate: CandidateView,
    state_callable,
    config: ExpressibilityConfig,
    *,
    rng: np.random.Generator | None,
    materialized: Any | None = None,
    should_cancel=None,
) -> MetricRecord:
    n_qubits = int(config.n_qubits or candidate.n_qubits)
    parameter_count = candidate.parameter_count
    base_seed = (
        stable_metric_seed(config.rng_seed, "expressibility", candidate.candidate_id)
        if config.rng_policy == "per_circuit"
        else int(config.rng_seed)
    )
    bin_edges = haar_bin_edges(n_qubits, int(config.n_bins), strategy=config.bin_strategy)
    reference = np.asarray(
        haar_bin_masses(n_qubits, int(config.n_bins), strategy=config.bin_strategy),
        dtype=float,
    )
    batch_size = _resolve_batch_size(config, n_qubits, materialized)
    evaluate_states = _state_batch_evaluator(state_callable, n_qubits, batch_size, materialized)

    start = time.perf_counter()
    trials: list[dict[str, Any]] = []
    all_fidelities: list[np.ndarray] = []
    for trial_index in range(int(config.n_trials)):
        if should_cancel is not None and should_cancel():
            raise RuntimeError("expressibility computation cancelled.")
        if rng is not None:
            local_rng = rng
            trial_seed = None
        else:
            trial_seed = _trial_seed(base_seed, trial_index, config, candidate.candidate_id)
            local_rng = np.random.default_rng(trial_seed)
        thetas = np.empty((int(config.n_pairs), int(parameter_count)), dtype=float)
        phis = np.empty((int(config.n_pairs), int(parameter_count)), dtype=float)
        for pair_index in range(int(config.n_pairs)):
            thetas[pair_index] = _random_parameters(local_rng, parameter_count, config)
            phis[pair_index] = _random_parameters(local_rng, parameter_count, config)
        fidelities = _pair_fidelities(thetas, phis, evaluate_states, batch_size)
        counts, _ = np.histogram(fidelities, bins=bin_edges, density=False)
        empirical = counts.astype(float) / counts.sum()
        dkl = kl_divergence(empirical, reference, config.histogram_epsilon)
        expressibility = float(-math.log10(max(dkl, float(config.dkl_floor))))
        trials.append(
            {
                "trial_index": trial_index,
                "dkl": dkl,
                "expressibility": expressibility,
                "rng_seed_used": trial_seed,
                "fidelity_mean": float(np.mean(fidelities)),
                "fidelity_std": float(np.std(fidelities)),
            },
        )
        all_fidelities.append(fidelities)
    elapsed = time.perf_counter() - start

    dkl_values = np.array([trial["dkl"] for trial in trials], dtype=float)
    expr_values = np.array([trial["expressibility"] for trial in trials], dtype=float)
    ddof = 1 if len(trials) > 1 else 0
    fidelities = np.concatenate(all_fidelities)
    dkl_mean = float(np.mean(dkl_values))
    value = {
        "dkl": dkl_mean,
        "expressibility": float(np.mean(expr_values)),
        "expressibility_std": float(np.std(expr_values, ddof=ddof)),
        "dkl_std": float(np.std(dkl_values, ddof=ddof)),
        "n_trials": int(config.n_trials),
    }
    return MetricRecord(
        metric_id=f"metric-expressibility-{candidate.candidate_id}",
        name="expressibility",
        status="computed",
        value=value,
        metadata={
            "backend": config.backend_label,
            "configuration": config.to_dict(),
            "n_qubits": n_qubits,
            "parameter_count": parameter_count,
            "rng_backend": "numpy.random.default_rng",
            "rng_policy": config.rng_policy,
            "rng_seed_used": base_seed,
            "bin_strategy": config.bin_strategy,
            "n_trials": int(config.n_trials),
            "trials": trials,
            "trial_aggregation": {
                "expressibility_mean": value["expressibility"],
                "expressibility_std": value["expressibility_std"],
                "std_ddof": ddof,
            },
            "state_calls": int(2 * config.n_pairs * config.n_trials),
            "qnode_calls": int(2 * config.n_pairs * config.n_trials),
            "sample_pairs": int(config.n_pairs),
            "batch_size": int(batch_size),
            "batched_evaluation": bool(batch_size > 1),
            "fidelity_mean": float(np.mean(fidelities)),
            "fidelity_std": float(np.std(fidelities)),
            "fidelity_min": float(np.min(fidelities)),
            "fidelity_max": float(np.max(fidelities)),
            "elapsed_seconds": elapsed,
            "expensive_metric": True,
            "qnodes_executed": bool(config.requires_qnode_execution),
        },
    )


def _trial_seed(base_seed: int, trial_index: int, config: ExpressibilityConfig, candidate_id: str) -> int:
    if trial_index == 0:
        return int(base_seed)
    if config.rng_policy == "per_circuit":
        return stable_metric_seed(config.rng_seed, f"expressibility:trial{trial_index}", candidate_id)
    return stable_metric_seed(config.rng_seed, f"expressibility:trial{trial_index}", "global_sequential")


def _resolve_batch_size(config: ExpressibilityConfig, n_qubits: int, materialized: Any | None) -> int:
    supports = bool(getattr(materialized, "supports_parameter_broadcasting", False))
    if not supports:
        return 1
    if config.batch_size is not None:
        return max(1, int(config.batch_size))
    automatic = int(config.max_batch_state_elements) // (2 ** int(n_qubits))
    return max(1, min(automatic, int(config.n_pairs)))


def _state_batch_evaluator(state_callable, n_qubits: int, batch_size: int, materialized: Any | None):
    expected = 2 ** int(n_qubits)
    if batch_size <= 1:
        def evaluate(parameter_rows: np.ndarray) -> np.ndarray:
            return np.array(
                [_state_from_callable(state_callable, row, n_qubits) for row in parameter_rows],
                dtype=complex,
            )

        return evaluate

    callable_ = materialized.state_callable if materialized is not None else state_callable

    def evaluate_batched(parameter_rows: np.ndarray) -> np.ndarray:
        raw = np.asarray(callable_(np.asarray(parameter_rows, dtype=float)), dtype=complex)
        if raw.ndim == 1 and parameter_rows.shape[0] == 1:
            raw = raw.reshape(1, -1)
        if raw.ndim != 2 or raw.shape[0] != parameter_rows.shape[0] or raw.shape[1] != expected:
            raise ValueError(
                f"batched state callable returned shape {raw.shape}, expected "
                f"({parameter_rows.shape[0]}, {expected}).",
            )
        norms = np.linalg.norm(raw, axis=1)
        if not np.all(np.isfinite(norms)) or np.any(norms <= 0.0):
            raise ValueError("Invalid state norm in batched evaluation.")
        return raw / norms[:, None]

    return evaluate_batched


def _pair_fidelities(thetas: np.ndarray, phis: np.ndarray, evaluate_states, batch_size: int) -> np.ndarray:
    n_pairs = thetas.shape[0]
    fidelities = np.empty(n_pairs, dtype=float)
    step = max(1, int(batch_size))
    for begin in range(0, n_pairs, step):
        end = min(n_pairs, begin + step)
        states_a = evaluate_states(thetas[begin:end])
        states_b = evaluate_states(phis[begin:end])
        if step == 1:
            fidelities[begin] = _fidelity(states_a[0], states_b[0])
            continue
        overlaps = np.abs(np.einsum("ij,ij->i", np.conj(states_a), states_b)) ** 2
        fidelities[begin:end] = np.clip(overlaps, 0.0, 1.0)
    return fidelities


def _random_parameters(
    rng: np.random.Generator,
    parameter_count: int,
    config: ExpressibilityConfig,
) -> np.ndarray:
    return rng.uniform(
        float(config.parameter_low),
        float(config.parameter_high),
        size=int(parameter_count),
    )


def _state_from_callable(state_callable, parameters: Sequence[float], n_qubits: int) -> list[complex]:
    try:
        raw = state_callable(parameters)
    except TypeError:
        raw = state_callable(*parameters)
    state = normalize_state_vector(raw)
    expected = 2 ** int(n_qubits)
    if len(state) != expected:
        raise ValueError(f"State dimension {len(state)} != 2**n_qubits ({expected}).")
    return state


def _fidelity(state_a: Sequence[complex], state_b: Sequence[complex]) -> float:
    fidelity = float(abs(np.vdot(np.asarray(state_a), np.asarray(state_b))) ** 2)
    return float(np.clip(fidelity, 0.0, 1.0))


def shared_rng(config: ExpressibilityConfig) -> np.random.Generator:
    """Return a NumPy RNG for global-sequential expressibility runs."""
    return np.random.default_rng(int(config.rng_seed))


__all__ = [
    "BIN_STRATEGIES",
    "ExpressibilityConfig",
    "compute_expressibility_metric",
    "haar_bin_edges",
    "haar_bin_masses",
    "kl_divergence",
    "normalize_state_vector",
    "shared_rng",
]

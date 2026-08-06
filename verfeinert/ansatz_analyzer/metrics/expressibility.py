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


@dataclass(frozen=True)
class ExpressibilityConfig:
    """Configuration for fidelity-sampling expressibility."""

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

    def __post_init__(self) -> None:
        if self.n_qubits is not None and int(self.n_qubits) <= 0:
            raise ValueError("n_qubits must be None or a positive integer.")
        if int(self.n_pairs) <= 0:
            raise ValueError("n_pairs must be positive.")
        if int(self.n_bins) <= 1:
            raise ValueError("n_bins must be greater than one.")
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
        """Build config from a parsed mapping."""
        return cls(**dict(mapping))

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
) -> MetricRecord:
    """Compute expressibility for one candidate using an explicit state callable."""
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
    estimated_calls = int(2 * resolved.n_pairs)
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
        return _compute(candidate, state_callable, resolved, rng=rng)
    except Exception as exc:
        return failed_metric(
            metric_name="expressibility",
            candidate_id=candidate.candidate_id,
            error=str(exc),
            metadata={"backend": resolved.backend_label},
        )


def haar_bin_masses(n_qubits: int, n_bins: int) -> list[float]:
    """Return Haar fidelity probability masses for equal bins over [0, 1]."""
    if int(n_qubits) <= 0:
        raise ValueError("n_qubits must be positive.")
    if int(n_bins) <= 1:
        raise ValueError("n_bins must be greater than one.")
    dimension = 2 ** int(n_qubits)
    edges = np.linspace(0.0, 1.0, int(n_bins) + 1)
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
) -> MetricRecord:
    n_qubits = int(config.n_qubits or candidate.n_qubits)
    parameter_count = candidate.parameter_count
    rng_seed = (
        stable_metric_seed(config.rng_seed, "expressibility", candidate.candidate_id)
        if config.rng_policy == "per_circuit"
        else int(config.rng_seed)
    )
    local_rng = rng or np.random.default_rng(rng_seed)
    bin_edges = np.linspace(0.0, 1.0, int(config.n_bins) + 1)
    reference = np.asarray(haar_bin_masses(n_qubits, int(config.n_bins)), dtype=float)
    fidelities = np.empty(int(config.n_pairs), dtype=float)
    start = time.perf_counter()
    for pair_index in range(int(config.n_pairs)):
        theta = _random_parameters(local_rng, parameter_count, config)
        phi = _random_parameters(local_rng, parameter_count, config)
        state_a = _state_from_callable(state_callable, theta, n_qubits)
        state_b = _state_from_callable(state_callable, phi, n_qubits)
        fidelities[pair_index] = _fidelity(state_a, state_b)
    counts, _ = np.histogram(fidelities, bins=bin_edges, density=False)
    empirical = counts.astype(float) / counts.sum()
    dkl = kl_divergence(empirical, reference, config.histogram_epsilon)
    expressibility = float(-math.log10(max(dkl, float(config.dkl_floor))))
    elapsed = time.perf_counter() - start
    return MetricRecord(
        metric_id=f"metric-expressibility-{candidate.candidate_id}",
        name="expressibility",
        status="computed",
        value={
            "dkl": dkl,
            "expressibility": expressibility,
        },
        metadata={
            "backend": config.backend_label,
            "configuration": config.to_dict(),
            "n_qubits": n_qubits,
            "parameter_count": parameter_count,
            "rng_backend": "numpy.random.default_rng",
            "rng_policy": config.rng_policy,
            "rng_seed_used": rng_seed,
            "state_calls": int(2 * config.n_pairs),
            "qnode_calls": int(2 * config.n_pairs),
            "sample_pairs": int(config.n_pairs),
            "fidelity_mean": float(np.mean(fidelities)),
            "fidelity_std": float(np.std(fidelities)),
            "fidelity_min": float(np.min(fidelities)),
            "fidelity_max": float(np.max(fidelities)),
            "elapsed_seconds": elapsed,
            "expensive_metric": True,
            "qnodes_executed": bool(config.requires_qnode_execution),
        },
    )


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
    "ExpressibilityConfig",
    "compute_expressibility_metric",
    "haar_bin_masses",
    "kl_divergence",
    "normalize_state_vector",
    "shared_rng",
]

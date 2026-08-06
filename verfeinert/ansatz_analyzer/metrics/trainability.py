"""V1-aligned Local-X trainability metric over state-vector callables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import time
from typing import Any

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

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
HAMILTONIAN_KINDS = ("sum_x",)


@dataclass(frozen=True)
class TrainabilityConfig:
    """Configuration for Local-X empirical gradient trainability."""

    n_qubits: int | None = None
    n_repeats: int | None = None
    trainability_n_pairs: int | None = None
    parameter_low: float = -math.pi
    parameter_high: float = math.pi
    rng_seed: int = 42
    rng_policy: str = "per_circuit"
    active_grad_tol: float = 1e-10
    hamiltonian_kind: str = "sum_x"
    hamiltonian: str | None = None
    hamiltonian_scale: float = 1.0
    max_gradient_components: int | None = None
    max_parameters_per_circuit: int | None = None
    backend_label: str = "state_callable"
    requires_qnode_execution: bool = False

    def __post_init__(self) -> None:
        if self.n_qubits is not None and int(self.n_qubits) <= 0:
            raise ValueError("n_qubits must be None or a positive integer.")
        repeats = _resolve_trainability_repeats(self.n_repeats, self.trainability_n_pairs)
        object.__setattr__(self, "n_repeats", repeats)
        object.__setattr__(self, "trainability_n_pairs", repeats)
        if float(self.parameter_high) <= float(self.parameter_low):
            raise ValueError("parameter_high must be greater than parameter_low.")
        if self.rng_policy not in RNG_POLICIES:
            raise ValueError(f"rng_policy must be one of {RNG_POLICIES}.")
        if float(self.active_grad_tol) < 0.0:
            raise ValueError("active_grad_tol must be non-negative.")
        normalized_hamiltonian = _normalize_hamiltonian_kind(self.hamiltonian_kind, self.hamiltonian)
        object.__setattr__(self, "hamiltonian_kind", normalized_hamiltonian)
        object.__setattr__(self, "hamiltonian", "local_x")
        if not np.isfinite(float(self.hamiltonian_scale)):
            raise ValueError("hamiltonian_scale must be finite.")
        if self.max_gradient_components is not None and int(self.max_gradient_components) <= 0:
            raise ValueError("max_gradient_components must be None or positive.")
        if self.max_parameters_per_circuit is not None and int(self.max_parameters_per_circuit) <= 0:
            raise ValueError("max_parameters_per_circuit must be None or positive.")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TrainabilityConfig":
        """Build config from a parsed mapping."""
        data = dict(mapping)
        if "finite_difference_step" in data:
            raise ValueError(
                "finite_difference_step is not part of the reference trainability "
                "implementation; PennyLane autodiff is required.",
            )
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe config data."""
        return to_json_safe(self.__dict__)


def compute_trainability_metric(
    candidate: CandidateView,
    state_callable,
    *,
    config: TrainabilityConfig | None = None,
    permissions: AnalyzerExecutionPermissions | None = None,
    rng: np.random.Generator | None = None,
) -> MetricRecord:
    """Compute Local-X trainability for one candidate using a state callable."""
    if not isinstance(candidate, CandidateView):
        raise TypeError("candidate must be a CandidateView.")
    resolved = config or TrainabilityConfig()
    allowed, reason = permissions_allow_metric(
        permissions or AnalyzerExecutionPermissions(),
        metric_name="trainability",
        requires_qnode_execution=resolved.requires_qnode_execution,
    )
    if not allowed:
        return permission_denied_metric(
            metric_name="trainability",
            candidate_id=candidate.candidate_id,
            reason=reason or "permission denied",
        )
    parameter_indices = _parameter_indices(candidate.parameter_count, resolved)
    gradient_components = int(resolved.n_repeats) * len(parameter_indices)
    if (
        resolved.max_gradient_components is not None
        and gradient_components > int(resolved.max_gradient_components)
    ):
        return failed_metric(
            metric_name="trainability",
            candidate_id=candidate.candidate_id,
            error=(
                "Trainability workload exceeds max_gradient_components: "
                f"estimated={gradient_components}, limit={resolved.max_gradient_components}"
            ),
            metadata={"estimated_gradient_components": gradient_components},
        )
    try:
        return _compute(candidate, state_callable, resolved, parameter_indices, rng=rng)
    except Exception as exc:
        return failed_metric(
            metric_name="trainability",
            candidate_id=candidate.candidate_id,
            error=str(exc),
            metadata={"backend": resolved.backend_label},
        )


def make_trainability_hamiltonian_matrix(
    n_qubits: int,
    *,
    kind: str = "sum_x",
    scale: float = 1.0,
) -> np.ndarray:
    """Build the dense matrix for H = scale * sum_i X_i."""
    if int(n_qubits) <= 0:
        raise ValueError("n_qubits must be positive.")
    if kind != "sum_x":
        raise ValueError(f"Unsupported hamiltonian kind: {kind!r}.")
    identity = np.eye(2, dtype=complex)
    pauli_x = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
    dimension = 2 ** int(n_qubits)
    hamiltonian = np.zeros((dimension, dimension), dtype=complex)
    for active_wire in range(int(n_qubits)):
        factors = [
            pauli_x if wire == active_wire else identity
            for wire in range(int(n_qubits))
        ]
        term = factors[0]
        for factor in factors[1:]:
            term = np.kron(term, factor)
        hamiltonian += term
    return complex(scale) * hamiltonian


def make_local_x_hamiltonian_matrix(
    n_qubits: int,
    *,
    scale: float = 1.0,
) -> list[list[float]]:
    """Return the Local-X Hamiltonian as a JSON-friendly nested list."""
    matrix = make_trainability_hamiltonian_matrix(n_qubits, scale=scale)
    return matrix.real.astype(float).tolist()


def energy_from_state(state, hamiltonian_matrix) -> Any:
    """Compute the real normalized expectation value ``<psi|H|psi>``."""
    vector = qml.math.reshape(state, (-1,))
    matrix = pnp.array(hamiltonian_matrix, requires_grad=False)
    if int(qml.math.shape(vector)[0]) != int(matrix.shape[0]):
        raise ValueError(
            f"State dimension {qml.math.shape(vector)[0]} does not match "
            f"Hamiltonian dimension {matrix.shape[0]}."
        )
    norm_sq = qml.math.real(qml.math.sum(qml.math.conj(vector) * vector))
    _raise_if_invalid_plain_norm(norm_sq)
    norm = qml.math.sqrt(norm_sq)
    normalized = vector / norm
    h_state = qml.math.dot(matrix, normalized)
    return qml.math.real(qml.math.sum(qml.math.conj(normalized) * h_state))


def energy_from_state_local_x(
    state: Sequence[complex],
    *,
    n_qubits: int,
    scale: float = 1.0,
) -> float:
    """Compute the real expectation value of H = scale * sum_i X_i."""
    hamiltonian = make_trainability_hamiltonian_matrix(n_qubits, scale=scale)
    return float(energy_from_state(state, hamiltonian))


def _compute(
    candidate: CandidateView,
    state_callable,
    config: TrainabilityConfig,
    parameter_indices: tuple[int, ...],
    *,
    rng: np.random.Generator | None,
) -> MetricRecord:
    n_qubits = int(config.n_qubits or candidate.n_qubits)
    rng_seed = (
        stable_metric_seed(config.rng_seed, "trainability", candidate.candidate_id)
        if config.rng_policy == "per_circuit"
        else int(config.rng_seed)
    )
    local_rng = rng or np.random.default_rng(rng_seed)
    hamiltonian = make_trainability_hamiltonian_matrix(
        n_qubits,
        kind=config.hamiltonian_kind,
        scale=config.hamiltonian_scale,
    )
    energy_fn = _make_energy_function(state_callable, hamiltonian)
    gradients = np.empty((int(config.n_repeats), len(parameter_indices)), dtype=float)
    start = time.perf_counter()
    for repeat_index in range(int(config.n_repeats)):
        parameters = pnp.array(
            local_rng.uniform(
                float(config.parameter_low),
                float(config.parameter_high),
                size=int(candidate.parameter_count),
            ),
            requires_grad=True,
        )
        full_gradient = _compute_gradient_vector(
            energy_fn,
            parameters,
            parameter_count=int(candidate.parameter_count),
        )
        gradients[repeat_index, :] = full_gradient[list(parameter_indices)]

    active = ~np.all(
        np.isclose(gradients, 0.0, atol=float(config.active_grad_tol)),
        axis=0,
    )
    if active.any():
        active_gradients = gradients[:, active]
        score = float(np.mean(active_gradients ** 2))
        gradient_variance = float(np.mean(np.var(active_gradients, axis=0)))
        mean_abs_gradient = float(np.mean(np.abs(active_gradients)))
        gradient_mean = float(np.mean(active_gradients))
    else:
        score = 0.0
        gradient_variance = 0.0
        mean_abs_gradient = 0.0
        gradient_mean = 0.0
    elapsed = time.perf_counter() - start
    return MetricRecord(
        metric_id=f"metric-trainability-{candidate.candidate_id}",
        name="trainability",
        status="computed",
        value={
            "trainability": score,
            "holmes_metric": score,
            "mean_squared_gradient_active": score,
            "gradient_variance": gradient_variance,
            "mean_abs_gradient": mean_abs_gradient,
            "gradient_mean": gradient_mean,
        },
        metadata={
            "backend": config.backend_label,
            "configuration": config.to_dict(),
            "n_qubits": n_qubits,
            "parameter_count": candidate.parameter_count,
            "n_repeats": int(config.n_repeats),
            "sampled_parameter_indices": list(parameter_indices),
            "gradient_components": int(config.n_repeats) * len(parameter_indices),
            "active_parameter_count": int(active.sum()),
            "inactive_parameter_count": int((~active).sum()),
            "sampled_parameter_count": int(len(parameter_indices)),
            "mean_abs_gradient": mean_abs_gradient,
            "gradient_mean": gradient_mean,
            "gradient_variance": gradient_variance,
            "gradient_backend": "pennylane.qml.grad",
            "rng_backend": "numpy.random.default_rng",
            "rng_policy": config.rng_policy,
            "rng_seed_used": rng_seed,
            "hamiltonian": "local_x",
            "hamiltonian_kind": "sum_x",
            "hamiltonian_definition": "H = sum_i X_i",
            "hamiltonian_scale": float(config.hamiltonian_scale),
            "elapsed_seconds": elapsed,
            "expensive_metric": True,
            "qnodes_executed": bool(config.requires_qnode_execution),
        },
    )


def _resolve_trainability_repeats(
    n_repeats: int | None,
    trainability_n_pairs: int | None,
) -> int:
    if n_repeats is None and trainability_n_pairs is None:
        value = 5000
    elif n_repeats is None:
        value = int(trainability_n_pairs)
    elif trainability_n_pairs is None:
        value = int(n_repeats)
    else:
        if int(n_repeats) != int(trainability_n_pairs):
            raise ValueError("n_repeats and trainability_n_pairs must match when both are provided.")
        value = int(n_repeats)
    if value <= 0:
        raise ValueError("trainability_n_pairs/n_repeats must be positive.")
    return value


def _normalize_hamiltonian_kind(hamiltonian_kind: str, hamiltonian: str | None) -> str:
    if hamiltonian is not None:
        if hamiltonian == "local_x":
            hamiltonian_kind = "sum_x"
        else:
            raise ValueError("trainability hamiltonian must be 'local_x'.")
    if hamiltonian_kind not in HAMILTONIAN_KINDS:
        raise ValueError("hamiltonian_kind must be 'sum_x'.")
    return hamiltonian_kind


def _parameter_indices(parameter_count: int, config: TrainabilityConfig) -> tuple[int, ...]:
    if int(parameter_count) < 0:
        raise ValueError("parameter_count must be non-negative.")
    limit = (
        int(parameter_count)
        if config.max_parameters_per_circuit is None
        else min(int(parameter_count), int(config.max_parameters_per_circuit))
    )
    return tuple(range(limit))


def _make_energy_function(state_callable, hamiltonian_matrix):
    def energy(parameters):
        state = state_callable(parameters)
        return energy_from_state(state, hamiltonian_matrix)

    return energy


def _compute_gradient_vector(energy_fn, parameters, *, parameter_count: int) -> np.ndarray:
    gradient = qml.grad(energy_fn)(parameters)
    array = np.asarray(gradient, dtype=float).reshape(-1)
    if array.size == 0 and int(parameter_count) == 0:
        return np.empty((0,), dtype=float)
    if array.size != int(parameter_count):
        if array.size == 1 and int(parameter_count) > 1 and np.isclose(array[0], 0.0):
            return np.zeros((int(parameter_count),), dtype=float)
        raise RuntimeError(f"Gradient size {array.size} != parameter_count {parameter_count}.")
    return array


def _raise_if_invalid_plain_norm(norm_sq) -> None:
    try:
        norm_value = float(qml.math.toarray(norm_sq))
    except Exception:
        return
    if not np.isfinite(norm_value) or norm_value <= 0.0:
        raise ValueError(f"Invalid state norm: {math.sqrt(norm_value) if norm_value >= 0 else norm_value}")


def shared_rng(config: TrainabilityConfig) -> np.random.Generator:
    """Return a NumPy RNG for global-sequential trainability runs."""
    return np.random.default_rng(int(config.rng_seed))


__all__ = [
    "TrainabilityConfig",
    "compute_trainability_metric",
    "energy_from_state",
    "energy_from_state_local_x",
    "make_trainability_hamiltonian_matrix",
    "make_local_x_hamiltonian_matrix",
    "shared_rng",
]

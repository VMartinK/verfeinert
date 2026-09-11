"""Empirical gradient-variance trainability over state-vector callables.

The metric follows Algorithm 2 of the reference manuscript: sample ``n_repeats``
uniformly random parameter vectors, evaluate the gradient of
``E(theta) = <psi(theta)|H|psi(theta)>`` for every trainable parameter, and
report the average of the per-parameter mean squared gradients (an unbiased
estimator of ``Var[dE/dtheta_k]`` because the gradient mean vanishes).

Supported cost Hamiltonians are provided by
:mod:`verfeinert.ansatz_analyzer.metrics.hamiltonians`: ``local_x`` (default,
backwards compatible), ``tfim`` and ``heisenberg``, all with user-selectable
parameters and defined for any number of qubits.
"""

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
from .hamiltonians import HAMILTONIAN_KINDS, HamiltonianError, HamiltonianSpec, MAX_DENSE_QUBITS
from .runtime import (
    failed_metric,
    permission_denied_metric,
    permissions_allow_metric,
    stable_metric_seed,
)

RNG_POLICIES = ("per_circuit", "global_sequential")
HAMILTONIAN_KINDS_LEGACY = ("sum_x",)
AVERAGING_MODES = ("active", "all")
DEFAULT_MAX_BATCH_STATE_ELEMENTS = 2**18


@dataclass(frozen=True)
class TrainabilityConfig:
    """Configuration for empirical gradient-variance trainability.

    ``hamiltonian`` selects the cost function family (``local_x``, ``tfim``,
    ``heisenberg`` or an alias such as ``ising``) and
    ``hamiltonian_parameters`` its couplings (for example ``{"J": 1.0, "h": 1.0}``).
    ``hamiltonian_kind``/``hamiltonian_scale`` remain accepted as legacy Local-X
    fields. ``n_trials`` repeats the ``n_repeats`` estimate with independent
    random streams and reports mean and sample standard deviation.
    ``average_over`` chooses whether the average runs over the parameters with a
    non-zero gradient (``active``, historical default) or over every trainable
    parameter (``all``, exactly Eq. 10 of the manuscript).
    """

    n_qubits: int | None = None
    n_repeats: int | None = None
    trainability_n_pairs: int | None = None
    parameter_low: float = -math.pi
    parameter_high: float = math.pi
    rng_seed: int = 42
    rng_policy: str = "per_circuit"
    active_grad_tol: float = 1e-10
    hamiltonian_kind: str | None = None
    hamiltonian: str | None = None
    hamiltonian_scale: float = 1.0
    hamiltonian_parameters: Mapping[str, float] | None = None
    hamiltonian_boundary: str = "open"
    max_gradient_components: int | None = None
    max_parameters_per_circuit: int | None = None
    backend_label: str = "state_callable"
    requires_qnode_execution: bool = False
    n_trials: int = 1
    average_over: str = "active"
    batch_size: int | None = None
    max_batch_state_elements: int = DEFAULT_MAX_BATCH_STATE_ELEMENTS

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
        if not np.isfinite(float(self.hamiltonian_scale)):
            raise ValueError("hamiltonian_scale must be finite.")
        try:
            spec = HamiltonianSpec.resolve(
                hamiltonian=self.hamiltonian,
                hamiltonian_kind=self.hamiltonian_kind,
                hamiltonian_parameters=self.hamiltonian_parameters,
                hamiltonian_scale=float(self.hamiltonian_scale),
                boundary=self.hamiltonian_boundary,
            )
        except HamiltonianError as exc:
            raise ValueError(str(exc)) from exc
        object.__setattr__(self, "hamiltonian", spec.kind)
        object.__setattr__(self, "hamiltonian_kind", spec.legacy_kind)
        object.__setattr__(self, "hamiltonian_parameters", dict(spec.parameters))
        object.__setattr__(self, "hamiltonian_boundary", spec.boundary)
        if spec.kind == "local_x":
            object.__setattr__(self, "hamiltonian_scale", float(spec.parameters["h"]))
        if self.max_gradient_components is not None and int(self.max_gradient_components) <= 0:
            raise ValueError("max_gradient_components must be None or positive.")
        if self.max_parameters_per_circuit is not None and int(self.max_parameters_per_circuit) <= 0:
            raise ValueError("max_parameters_per_circuit must be None or positive.")
        if int(self.n_trials) <= 0:
            raise ValueError("n_trials must be positive.")
        if self.average_over not in AVERAGING_MODES:
            raise ValueError(f"average_over must be one of {AVERAGING_MODES}.")
        if self.batch_size is not None and int(self.batch_size) <= 0:
            raise ValueError("batch_size must be None or positive.")
        if int(self.max_batch_state_elements) <= 0:
            raise ValueError("max_batch_state_elements must be positive.")

    @property
    def hamiltonian_spec(self) -> HamiltonianSpec:
        """Return the resolved Hamiltonian specification."""
        return HamiltonianSpec(
            kind=str(self.hamiltonian),
            parameters=dict(self.hamiltonian_parameters or {}),
            boundary=self.hamiltonian_boundary,
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TrainabilityConfig":
        """Build config from a parsed mapping (``n_samples`` aliases ``n_repeats``)."""
        data = dict(mapping)
        if "finite_difference_step" in data:
            raise ValueError(
                "finite_difference_step is not part of the reference trainability "
                "implementation; PennyLane autodiff is required.",
            )
        if "n_samples" in data:
            samples = data.pop("n_samples")
            if "n_repeats" in data and int(data["n_repeats"]) != int(samples):
                raise ValueError("n_repeats and n_samples must match when both are provided.")
            data["n_repeats"] = samples
        hamiltonian = data.get("hamiltonian")
        if isinstance(hamiltonian, Mapping):
            spec = HamiltonianSpec.from_mapping(hamiltonian)
            data["hamiltonian"] = spec.kind
            data.setdefault("hamiltonian_parameters", dict(spec.parameters))
            data.setdefault("hamiltonian_boundary", spec.boundary)
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
    materialized: Any | None = None,
    should_cancel=None,
) -> MetricRecord:
    """Compute trainability for one candidate using a state callable.

    When ``materialized`` (a :class:`MaterializedCircuit`) is given, the energy
    is evaluated through a PennyLane ``expval`` QNode with parameter
    broadcasting, which avoids dense ``2**n x 2**n`` matrices and evaluates
    gradients for whole batches of parameter samples at once. Otherwise the
    energy is computed as ``<psi|H|psi>`` on the returned state vector with a
    dense Hamiltonian matrix (``n_qubits <= 12``).
    """
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
    gradient_components = int(resolved.n_repeats) * len(parameter_indices) * int(resolved.n_trials)
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
        return _compute(
            candidate,
            state_callable,
            resolved,
            parameter_indices,
            rng=rng,
            materialized=materialized,
            should_cancel=should_cancel,
        )
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
    parameters: Mapping[str, float] | None = None,
    boundary: str = "open",
) -> np.ndarray:
    """Build the dense matrix of a supported Hamiltonian family.

    ``kind="sum_x"`` (legacy) builds ``scale * sum_i X_i``; ``tfim`` and
    ``heisenberg`` use ``parameters`` (see :class:`HamiltonianSpec`).
    """
    if int(n_qubits) <= 0:
        raise ValueError("n_qubits must be positive.")
    try:
        spec = HamiltonianSpec.resolve(
            hamiltonian=kind,
            hamiltonian_parameters=parameters,
            hamiltonian_scale=scale,
            boundary=boundary,
        )
        return spec.to_dense(int(n_qubits), max_qubits=MAX_DENSE_QUBITS)
    except HamiltonianError as exc:
        raise ValueError(f"Unsupported hamiltonian kind: {kind!r} ({exc}).") from exc


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
    materialized: Any | None = None,
    should_cancel=None,
) -> MetricRecord:
    n_qubits = int(config.n_qubits or candidate.n_qubits)
    parameter_count = int(candidate.parameter_count)
    base_seed = (
        stable_metric_seed(config.rng_seed, "trainability", candidate.candidate_id)
        if config.rng_policy == "per_circuit"
        else int(config.rng_seed)
    )
    spec = config.hamiltonian_spec
    batch_size = _resolve_batch_size(config, n_qubits, materialized)
    gradient_evaluator, energy_backend = _gradient_evaluator(
        state_callable,
        spec,
        n_qubits=n_qubits,
        parameter_count=parameter_count,
        batch_size=batch_size,
        materialized=materialized,
    )
    start = time.perf_counter()
    trials: list[dict[str, Any]] = []
    all_gradients: list[np.ndarray] = []
    for trial_index in range(int(config.n_trials)):
        if should_cancel is not None and should_cancel():
            raise RuntimeError("trainability computation cancelled.")
        if rng is not None:
            local_rng = rng
            trial_seed = None
        else:
            trial_seed = _trial_seed(base_seed, trial_index, config, candidate.candidate_id)
            local_rng = np.random.default_rng(trial_seed)
        samples = np.empty((int(config.n_repeats), parameter_count), dtype=float)
        for repeat_index in range(int(config.n_repeats)):
            samples[repeat_index] = local_rng.uniform(
                float(config.parameter_low),
                float(config.parameter_high),
                size=parameter_count,
            )
        full_gradients = gradient_evaluator(samples)
        gradients = full_gradients[:, list(parameter_indices)]
        summary = _summarize_gradients(gradients, config)
        summary["trial_index"] = trial_index
        summary["rng_seed_used"] = trial_seed
        trials.append(summary)
        all_gradients.append(gradients)
    elapsed = time.perf_counter() - start

    ddof = 1 if len(trials) > 1 else 0
    scores = np.array([trial["trainability"] for trial in trials], dtype=float)
    scores_all = np.array([trial["trainability_all_parameters"] for trial in trials], dtype=float)
    score = float(np.mean(scores))
    pooled = np.concatenate(all_gradients, axis=0)
    pooled_summary = _summarize_gradients(pooled, config)
    value = {
        "trainability": score,
        "trainability_std": float(np.std(scores, ddof=ddof)),
        "holmes_metric": score,
        "mean_squared_gradient_active": float(np.mean([trial["mean_squared_gradient_active"] for trial in trials])),
        "trainability_all_parameters": float(np.mean(scores_all)),
        "trainability_all_parameters_std": float(np.std(scores_all, ddof=ddof)),
        "gradient_variance": pooled_summary["gradient_variance"],
        "mean_abs_gradient": pooled_summary["mean_abs_gradient"],
        "gradient_mean": pooled_summary["gradient_mean"],
        "n_trials": int(config.n_trials),
    }
    return MetricRecord(
        metric_id=f"metric-trainability-{candidate.candidate_id}",
        name="trainability",
        status="computed",
        value=value,
        metadata={
            "backend": config.backend_label,
            "configuration": config.to_dict(),
            "n_qubits": n_qubits,
            "parameter_count": candidate.parameter_count,
            "n_repeats": int(config.n_repeats),
            "n_trials": int(config.n_trials),
            "trials": trials,
            "trial_aggregation": {
                "trainability_mean": score,
                "trainability_std": value["trainability_std"],
                "std_ddof": ddof,
            },
            "average_over": config.average_over,
            "sampled_parameter_indices": list(parameter_indices),
            "gradient_components": int(config.n_repeats) * len(parameter_indices) * int(config.n_trials),
            "active_parameter_count": int(pooled_summary["active_parameter_count"]),
            "inactive_parameter_count": int(pooled_summary["inactive_parameter_count"]),
            "sampled_parameter_count": int(len(parameter_indices)),
            "mean_abs_gradient": value["mean_abs_gradient"],
            "gradient_mean": value["gradient_mean"],
            "gradient_variance": value["gradient_variance"],
            "gradient_backend": "pennylane.qml.grad",
            "energy_backend": energy_backend,
            "batch_size": int(batch_size),
            "batched_evaluation": bool(batch_size > 1),
            "rng_backend": "numpy.random.default_rng",
            "rng_policy": config.rng_policy,
            "rng_seed_used": base_seed,
            **spec.metric_metadata(),
            "hamiltonian_term_count": spec.term_count(n_qubits),
            "elapsed_seconds": elapsed,
            "expensive_metric": True,
            "qnodes_executed": bool(config.requires_qnode_execution),
        },
    )


def _summarize_gradients(gradients: np.ndarray, config: TrainabilityConfig) -> dict[str, Any]:
    if gradients.size == 0:
        return {
            "trainability": 0.0,
            "trainability_all_parameters": 0.0,
            "mean_squared_gradient_active": 0.0,
            "gradient_variance": 0.0,
            "mean_abs_gradient": 0.0,
            "gradient_mean": 0.0,
            "active_parameter_count": 0,
            "inactive_parameter_count": int(gradients.shape[1]) if gradients.ndim == 2 else 0,
        }
    active = ~np.all(np.isclose(gradients, 0.0, atol=float(config.active_grad_tol)), axis=0)
    all_parameters_score = float(np.mean(np.mean(gradients**2, axis=0)))
    if active.any():
        active_gradients = gradients[:, active]
        active_score = float(np.mean(active_gradients**2))
        gradient_variance = float(np.mean(np.var(active_gradients, axis=0)))
        mean_abs_gradient = float(np.mean(np.abs(active_gradients)))
        gradient_mean = float(np.mean(active_gradients))
    else:
        active_score = 0.0
        gradient_variance = 0.0
        mean_abs_gradient = 0.0
        gradient_mean = 0.0
    return {
        "trainability": all_parameters_score if config.average_over == "all" else active_score,
        "trainability_all_parameters": all_parameters_score,
        "mean_squared_gradient_active": active_score,
        "gradient_variance": gradient_variance,
        "mean_abs_gradient": mean_abs_gradient,
        "gradient_mean": gradient_mean,
        "active_parameter_count": int(active.sum()),
        "inactive_parameter_count": int((~active).sum()),
    }


def _trial_seed(base_seed: int, trial_index: int, config: TrainabilityConfig, candidate_id: str) -> int:
    if trial_index == 0:
        return int(base_seed)
    if config.rng_policy == "per_circuit":
        return stable_metric_seed(config.rng_seed, f"trainability:trial{trial_index}", candidate_id)
    return stable_metric_seed(config.rng_seed, f"trainability:trial{trial_index}", "global_sequential")


def _resolve_batch_size(config: TrainabilityConfig, n_qubits: int, materialized: Any | None) -> int:
    supports = bool(getattr(materialized, "supports_parameter_broadcasting", False))
    if not supports:
        return 1
    if config.batch_size is not None:
        return max(1, int(config.batch_size))
    automatic = int(config.max_batch_state_elements) // (2 ** int(n_qubits))
    return max(1, min(automatic, int(config.n_repeats)))


def _gradient_evaluator(
    state_callable,
    spec: HamiltonianSpec,
    *,
    n_qubits: int,
    parameter_count: int,
    batch_size: int,
    materialized: Any | None,
):
    """Return ``(evaluate(samples) -> gradients, backend_label)``."""
    if batch_size > 1 and materialized is not None:
        observable = spec.to_pennylane(n_qubits)
        energy_qnode = materialized.observable_qnode(observable)

        def batched_energy_sum(parameters):
            return qml.math.sum(energy_qnode(parameters))

        def evaluate_batched(samples: np.ndarray) -> np.ndarray:
            if parameter_count == 0:
                return np.zeros((samples.shape[0], 0), dtype=float)
            gradients = np.empty(samples.shape, dtype=float)
            for begin in range(0, samples.shape[0], batch_size):
                end = min(samples.shape[0], begin + batch_size)
                block = pnp.array(samples[begin:end], requires_grad=True)
                gradient = qml.grad(batched_energy_sum)(block)
                array = np.asarray(gradient, dtype=float)
                if array.shape != (end - begin, parameter_count):
                    if array.size == 0:
                        array = np.zeros((end - begin, parameter_count), dtype=float)
                    else:
                        raise RuntimeError(
                            f"Batched gradient shape {array.shape} != {(end - begin, parameter_count)}.",
                        )
                gradients[begin:end] = array
            return gradients

        return evaluate_batched, "pennylane.expval.broadcast"

    if n_qubits > MAX_DENSE_QUBITS:
        raise ValueError(
            f"dense-matrix trainability is limited to {MAX_DENSE_QUBITS} qubits; "
            "enable analyzer materialization for larger circuits.",
        )
    hamiltonian = spec.to_dense(n_qubits)
    energy_fn = _make_energy_function(state_callable, hamiltonian)

    def evaluate_sequential(samples: np.ndarray) -> np.ndarray:
        gradients = np.empty(samples.shape, dtype=float)
        for index in range(samples.shape[0]):
            parameters = pnp.array(samples[index], requires_grad=True)
            gradients[index] = _compute_gradient_vector(
                energy_fn,
                parameters,
                parameter_count=parameter_count,
            )
        return gradients

    return evaluate_sequential, "dense_matrix.state"


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
    "AVERAGING_MODES",
    "HAMILTONIAN_KINDS",
    "TrainabilityConfig",
    "compute_trainability_metric",
    "energy_from_state",
    "energy_from_state_local_x",
    "make_trainability_hamiltonian_matrix",
    "make_local_x_hamiltonian_matrix",
    "shared_rng",
]

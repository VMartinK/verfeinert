"""VQE validation of candidate ansaetze against a benchmark Hamiltonian.

The default optimizer settings follow the manuscript validation study: Adam
with learning rate 0.05, 200 steps and 5 independent random initializations,
with the final normalized energy error ``|(E - E0) / E0|`` as figure of merit
(``E0`` obtained by exact diagonalization).

Other optimizers commonly used for VQE can be selected through
:class:`VQEConfig` (see :data:`OPTIMIZER_SPECS`): PennyLane gradient
optimizers (Adam, gradient descent, Momentum, Nesterov, RMSProp, Adagrad),
the quantum natural gradient, SPSA, the analytic Rotosolve/Rotoselect
methods and the SciPy optimizers COBYLA, Nelder-Mead, Powell and L-BFGS-B.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from fractions import Fraction
import math
import time
from typing import Any

import numpy as np

from verfeinert.ansatz_analyzer.config import CircuitMaterializationConfig
from verfeinert.ansatz_analyzer.materialization import ROTATION_GATES, materialize_candidate
from verfeinert.ansatz_analyzer.metrics.hamiltonians import HamiltonianSpec
from verfeinert.ansatz_analyzer.metrics.protocol import PAPER_VQE
from verfeinert.ansatz_analyzer.models import CandidateView
from verfeinert.core.io.serialization import to_json_safe


class VQECancelled(RuntimeError):
    """Raised when a VQE run is cancelled by the caller."""


@dataclass(frozen=True)
class OptimizerSpec:
    """Description of one VQE optimizer exposed through the API and the live UI."""

    key: str
    label: str
    family: str
    uses_learning_rate: bool
    description: str
    default_learning_rate: float | None = None
    default_options: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_json_safe(
            {
                "key": self.key,
                "label": self.label,
                "family": self.family,
                "uses_learning_rate": self.uses_learning_rate,
                "description": self.description,
                "default_learning_rate": self.default_learning_rate,
                "default_options": dict(self.default_options),
            }
        )


OPTIMIZER_FAMILIES: dict[str, str] = {
    "gradient": "Gradient-based",
    "natural_gradient": "Natural gradient",
    "analytic": "Analytic (Rotosolve family)",
    "stochastic": "Stochastic",
    "scipy": "SciPy (gradient-free / quasi-Newton)",
}

OPTIMIZER_SPECS: tuple[OptimizerSpec, ...] = (
    OptimizerSpec(
        "adam", "Adam", "gradient", True,
        "Adam (Kingma & Ba 2015). Manuscript setting: learning rate 0.05, 200 steps.",
        0.05, {"beta1": 0.9, "beta2": 0.99, "eps": 1e-8},
    ),
    OptimizerSpec(
        "gradient_descent", "Gradient descent", "gradient", True,
        "Plain gradient descent with parameter-shift / autograd gradients.",
        0.05,
    ),
    OptimizerSpec(
        "momentum", "Momentum", "gradient", True,
        "Gradient descent with heavy-ball momentum (0.9).",
        0.05, {"momentum": 0.9},
    ),
    OptimizerSpec(
        "nesterov", "Nesterov momentum", "gradient", True,
        "Nesterov accelerated gradient descent (momentum 0.9).",
        0.05, {"momentum": 0.9},
    ),
    OptimizerSpec(
        "rmsprop", "RMSProp", "gradient", True,
        "RMSProp adaptive per-parameter step sizes.",
        0.01, {"decay": 0.9, "eps": 1e-8},
    ),
    OptimizerSpec(
        "adagrad", "Adagrad", "gradient", True,
        "Adagrad adaptive per-parameter step sizes.",
        0.05, {"eps": 1e-8},
    ),
    OptimizerSpec(
        "qng", "Quantum natural gradient", "natural_gradient", True,
        "Quantum natural gradient (Stokes et al. 2020) with the block-diagonal "
        "Fubini-Study metric and Tikhonov regularisation.",
        0.05, {"approx": "block-diag", "lam": 1e-3},
    ),
    OptimizerSpec(
        "spsa", "SPSA", "stochastic", False,
        "Simultaneous perturbation stochastic approximation (Spall 1998): two "
        "energy evaluations per step independent of the parameter count.",
        None, {"c": 0.2, "alpha": 0.602, "gamma": 0.101},
    ),
    OptimizerSpec(
        "rotosolve", "Rotosolve", "analytic", False,
        "Rotosolve (Ostaszewski et al. 2021): one step is a sweep over all "
        "parameters, each minimised exactly from its Fourier reconstruction "
        "(2R energy evaluations for a parameter with R frequencies).",
        None, {"grid_points": 2048},
    ),
    OptimizerSpec(
        "rotoselect", "Rotoselect", "analytic", False,
        "Rotoselect (Ostaszewski et al. 2021): Rotosolve plus per-parameter "
        "selection of the RX/RY/RZ generator of single-qubit rotations; the "
        "chosen generators are reported with the result.",
        None, {"grid_points": 2048},
    ),
    OptimizerSpec(
        "cobyla", "COBYLA", "scipy", False,
        "Constrained optimisation by linear approximation (SciPy), gradient-free; "
        "steps bound the number of energy evaluations.",
        None,
    ),
    OptimizerSpec(
        "nelder_mead", "Nelder-Mead", "scipy", False,
        "Nelder-Mead simplex (SciPy), gradient-free.",
        None,
    ),
    OptimizerSpec(
        "powell", "Powell", "scipy", False,
        "Powell conjugate-direction line searches (SciPy), gradient-free.",
        None,
    ),
    OptimizerSpec(
        "l_bfgs_b", "L-BFGS-B", "scipy", False,
        "Limited-memory BFGS (SciPy) driven by autograd gradients.",
        None,
    ),
)
OPTIMIZER_INDEX: dict[str, OptimizerSpec] = {spec.key: spec for spec in OPTIMIZER_SPECS}
OPTIMIZERS: tuple[str, ...] = tuple(OPTIMIZER_INDEX)
_OPTIMIZER_ALIASES: dict[str, str] = {
    "sgd": "gradient_descent",
    "gd": "gradient_descent",
    "natural_gradient": "qng",
    "quantum_natural_gradient": "qng",
    "lbfgs": "l_bfgs_b",
    "lbfgsb": "l_bfgs_b",
    "l_bfgs": "l_bfgs_b",
    "neldermead": "nelder_mead",
}
_PENNYLANE_GRADIENT_OPTIMIZERS = frozenset({"adam", "gradient_descent", "momentum", "nesterov", "rmsprop", "adagrad"})
_SCIPY_METHODS: dict[str, str] = {
    "cobyla": "COBYLA",
    "nelder_mead": "Nelder-Mead",
    "powell": "Powell",
    "l_bfgs_b": "L-BFGS-B",
}
# Eigenvalues of the generator of each parametrized gate (for Rotosolve spectra).
_GATE_GENERATOR_EIGENVALUES: dict[str, tuple[float, ...]] = {
    "rx": (-0.5, 0.5),
    "ry": (-0.5, 0.5),
    "rz": (-0.5, 0.5),
    "isingxx": (-0.5, 0.5),
    "isingyy": (-0.5, 0.5),
    "isingzz": (-0.5, 0.5),
    "crx": (0.0, -0.5, 0.5),
    "cry": (0.0, -0.5, 0.5),
    "crz": (0.0, -0.5, 0.5),
}


def normalize_optimizer_name(name: str) -> str:
    """Return the canonical optimizer key for ``name`` (case/separator insensitive)."""
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    key = _OPTIMIZER_ALIASES.get(key, key)
    if key not in OPTIMIZER_INDEX:
        raise ValueError(f"optimizer must be one of {OPTIMIZERS}, got {name!r}.")
    return key


def optimizer_catalog() -> list[dict[str, Any]]:
    """Return the JSON-safe optimizer catalog used by the live UI."""
    return [
        {**spec.to_dict(), "family_label": OPTIMIZER_FAMILIES[spec.family]}
        for spec in OPTIMIZER_SPECS
    ]


@dataclass(frozen=True)
class VQEConfig:
    """Optimizer settings for the VQE validation."""

    steps: int = int(PAPER_VQE["steps"])
    learning_rate: float = float(PAPER_VQE["learning_rate"])
    restarts: int = int(PAPER_VQE["restarts"])
    optimizer: str = str(PAPER_VQE["optimizer"])
    random_seed: int = 0
    record_every: int = 1
    diff_method: str = "best"
    optimizer_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if int(self.steps) < 1:
            raise ValueError("steps must be positive.")
        if float(self.learning_rate) <= 0.0:
            raise ValueError("learning_rate must be positive.")
        if int(self.restarts) < 1:
            raise ValueError("restarts must be positive.")
        object.__setattr__(self, "optimizer", normalize_optimizer_name(self.optimizer))
        if int(self.record_every) < 1:
            raise ValueError("record_every must be positive.")
        object.__setattr__(self, "optimizer_options", dict(self.optimizer_options or {}))

    @property
    def spec(self) -> OptimizerSpec:
        return OPTIMIZER_INDEX[self.optimizer]

    @property
    def resolved_options(self) -> dict[str, Any]:
        """Optimizer options with the per-optimizer defaults filled in."""
        return {**self.spec.default_options, **self.optimizer_options}

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | None) -> "VQEConfig":
        data = dict(mapping or {})
        learning_rate = data.get("learning_rate")
        optimizer = normalize_optimizer_name(data.get("optimizer", PAPER_VQE["optimizer"]))
        if learning_rate is None or learning_rate == "":
            spec = OPTIMIZER_INDEX[optimizer]
            learning_rate = spec.default_learning_rate if spec.default_learning_rate else PAPER_VQE["learning_rate"]
        return cls(
            steps=int(data.get("steps", PAPER_VQE["steps"])),
            learning_rate=float(learning_rate),
            restarts=int(data.get("restarts", PAPER_VQE["restarts"])),
            optimizer=optimizer,
            random_seed=int(data.get("random_seed", 0)),
            record_every=int(data.get("record_every", 1)),
            diff_method=str(data.get("diff_method", "best")),
            optimizer_options=dict(data.get("optimizer_options") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_json_safe({**self.__dict__, "optimizer_label": self.spec.label})


def run_vqe(
    document: Mapping[str, Any],
    hamiltonian: HamiltonianSpec | Mapping[str, Any] | str,
    *,
    config: VQEConfig | None = None,
    emit: Callable[[dict[str, Any]], Any] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Optimize the candidate's parameters for ``hamiltonian`` and report results."""
    import pennylane as qml
    from pennylane import numpy as pnp

    resolved = config or VQEConfig()
    spec = HamiltonianSpec.from_mapping(hamiltonian)
    view = CandidateView.from_document(dict(document))
    n_qubits = view.n_qubits
    started = time.perf_counter()
    rotation_overrides: dict[str, str] = {}
    materialized = materialize_candidate(
        view,
        config=CircuitMaterializationConfig(enabled=True, diff_method=resolved.diff_method),
        rotation_overrides=rotation_overrides,
    )
    observable = spec.to_pennylane(n_qubits)
    energy = materialized.observable_qnode(observable)
    exact_energy: float | None = None
    ground_state: np.ndarray | None = None
    if n_qubits <= 14:
        exact_energy, ground_state = spec.ground_state(n_qubits)
    rng = np.random.default_rng(resolved.random_seed)
    parameter_count = view.parameter_count

    def _emit(event_type: str, **payload: Any) -> None:
        if emit is not None:
            emit(to_json_safe({"event_type": event_type, "candidate_id": view.candidate_id, **payload}))

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise VQECancelled("VQE cancelled")

    evaluations = [0]

    def cost(parameters):
        evaluations[0] += 1
        _check_cancel()
        return energy(parameters)

    context = _RunContext(
        qml=qml,
        pnp=pnp,
        config=resolved,
        cost=cost,
        energy_qnode=energy,
        view=view,
        trainable_parameter_ids=materialized.trainable_parameter_ids,
        rotation_overrides=rotation_overrides,
        parameter_count=parameter_count,
        check_cancel=_check_cancel,
    )
    _emit(
        "vqe_started",
        n_qubits=n_qubits,
        parameter_count=parameter_count,
        exact_energy=exact_energy,
        config=resolved.to_dict(),
        hamiltonian=spec.to_dict(),
    )
    restarts: list[dict[str, Any]] = []
    for restart in range(resolved.restarts):
        _check_cancel()
        initial = rng.uniform(0.0, 2.0 * math.pi, size=parameter_count)
        evaluations[0] = 0
        rotation_overrides.clear()
        recorder = _RestartRecorder(
            restart=restart,
            steps=resolved.steps,
            record_every=resolved.record_every,
            exact_energy=exact_energy,
            emit=_emit,
            initial_parameters=initial,
            initial_energy=float(cost(initial)),
        )
        extra = _optimize_restart(context, initial, recorder)
        recorder.finish()
        final_energy = recorder.trajectory[-1]
        record = {
            "restart": restart,
            "final_energy": final_energy,
            "best_energy": recorder.best_energy,
            "trajectory": recorder.trajectory,
            "iterations": recorder.iterations,
            "evaluations": evaluations[0],
            "normalized_error": _normalized_error(final_energy, exact_energy),
            "best_normalized_error": _normalized_error(recorder.best_energy, exact_energy),
            "best_parameters": recorder.best_parameters.tolist(),
            **extra,
        }
        restarts.append(record)
        _emit(
            "vqe_restart_completed",
            restart=restart,
            final_energy=final_energy,
            best_energy=recorder.best_energy,
            normalized_error=record["normalized_error"],
            iterations=recorder.iterations,
            evaluations=evaluations[0],
        )
    best = min(restarts, key=lambda item: item["best_energy"])
    rotation_overrides.clear()
    rotation_overrides.update(best.get("rotation_overrides") or {})
    final_errors = [item["normalized_error"] for item in restarts if item["normalized_error"] is not None]
    state_summary = _state_summary(materialized, best["best_parameters"], ground_state, n_qubits)
    trajectories = np.array([item["trajectory"] for item in restarts], dtype=float)
    result = {
        "candidate_id": view.candidate_id,
        "n_qubits": n_qubits,
        "parameter_count": parameter_count,
        "hamiltonian": spec.to_dict(),
        "config": resolved.to_dict(),
        "optimizer": resolved.optimizer,
        "optimizer_label": resolved.spec.label,
        "exact_energy": exact_energy,
        "best_energy": best["best_energy"],
        "best_restart": best["restart"],
        "best_normalized_error": best["best_normalized_error"],
        "mean_final_energy": float(np.mean([item["final_energy"] for item in restarts])),
        "mean_normalized_error": (float(np.mean(final_errors)) if final_errors else None),
        "median_normalized_error": (float(np.median(final_errors)) if final_errors else None),
        "std_normalized_error": (float(np.std(final_errors, ddof=1)) if len(final_errors) > 1 else 0.0),
        "mean_iterations": float(np.mean([item["iterations"] for item in restarts])),
        "mean_evaluations": float(np.mean([item["evaluations"] for item in restarts])),
        "median_trajectory": np.median(trajectories, axis=0).tolist(),
        "restarts": restarts,
        "elapsed_seconds": time.perf_counter() - started,
        **state_summary,
    }
    if resolved.optimizer == "rotoselect":
        result["selected_generators"] = best.get("selected_generators", [])
        result["rotation_overrides"] = dict(best.get("rotation_overrides") or {})
        result["changed_generators"] = sum(
            1 for item in result["selected_generators"] if item["selected"] != item["original"]
        )
    _emit("vqe_completed", result={k: v for k, v in result.items() if k not in {"restarts"}})
    return to_json_safe(result)


@dataclass
class _RunContext:
    qml: Any
    pnp: Any
    config: VQEConfig
    cost: Callable[[Any], Any]
    energy_qnode: Any
    view: CandidateView
    trainable_parameter_ids: tuple[str, ...]
    rotation_overrides: dict[str, str]
    parameter_count: int
    check_cancel: Callable[[], None]


class _RestartRecorder:
    """Track the energy trajectory, best point and step events of one restart."""

    def __init__(
        self,
        *,
        restart: int,
        steps: int,
        record_every: int,
        exact_energy: float | None,
        emit: Callable[..., None],
        initial_parameters: np.ndarray,
        initial_energy: float,
    ) -> None:
        self.restart = restart
        self.steps = steps
        self.record_every = record_every
        self.exact_energy = exact_energy
        self.emit = emit
        self.trajectory: list[float] = [initial_energy]
        self.best_energy = initial_energy
        self.best_parameters = np.array(initial_parameters, dtype=float)
        self.last_parameters = np.array(initial_parameters, dtype=float)
        self.iterations = 0
        self._last_emitted = 0

    @property
    def exhausted(self) -> bool:
        return self.iterations >= self.steps

    def record(self, parameters, value: float) -> None:
        if self.exhausted:
            return
        value = float(value)
        self.iterations += 1
        self.trajectory.append(value)
        self.last_parameters = np.array(parameters, dtype=float).reshape(-1)
        if value < self.best_energy:
            self.best_energy = value
            self.best_parameters = self.last_parameters.copy()
        if self.iterations % self.record_every == 0 or self.iterations == self.steps:
            self._emit_step()

    def finish(self) -> None:
        if self.iterations and self._last_emitted != self.iterations:
            self._emit_step()
        while len(self.trajectory) < self.steps + 1:
            self.trajectory.append(self.trajectory[-1])

    def _emit_step(self) -> None:
        self._last_emitted = self.iterations
        self.emit(
            "vqe_step",
            restart=self.restart,
            step=self.iterations,
            energy=self.trajectory[-1],
            best_energy=self.best_energy,
            exact_energy=self.exact_energy,
        )


def _optimize_restart(ctx: _RunContext, initial: np.ndarray, recorder: _RestartRecorder) -> dict[str, Any]:
    key = ctx.config.optimizer
    if ctx.parameter_count == 0:
        for _ in range(ctx.config.steps):
            recorder.record(initial, recorder.trajectory[0])
        return {}
    if key in _PENNYLANE_GRADIENT_OPTIMIZERS or key in {"qng", "spsa"}:
        return _run_pennylane_stepper(ctx, initial, recorder)
    if key == "rotosolve":
        return _run_rotosolve(ctx, initial, recorder)
    if key == "rotoselect":
        return _run_rotoselect(ctx, initial, recorder)
    if key in _SCIPY_METHODS:
        return _run_scipy(ctx, initial, recorder)
    raise ValueError(f"unsupported optimizer {key!r}.")  # pragma: no cover - guarded by VQEConfig


def _build_pennylane_optimizer(ctx: _RunContext):
    qml = ctx.qml
    key = ctx.config.optimizer
    lr = float(ctx.config.learning_rate)
    options = ctx.config.resolved_options
    if key == "adam":
        return qml.AdamOptimizer(stepsize=lr, beta1=options["beta1"], beta2=options["beta2"], eps=options["eps"])
    if key == "gradient_descent":
        return qml.GradientDescentOptimizer(stepsize=lr)
    if key == "momentum":
        return qml.MomentumOptimizer(stepsize=lr, momentum=options["momentum"])
    if key == "nesterov":
        return qml.NesterovMomentumOptimizer(stepsize=lr, momentum=options["momentum"])
    if key == "rmsprop":
        return qml.RMSPropOptimizer(stepsize=lr, decay=options["decay"], eps=options["eps"])
    if key == "adagrad":
        return qml.AdagradOptimizer(stepsize=lr, eps=options["eps"])
    if key == "qng":
        return qml.QNGOptimizer(stepsize=lr, approx=options["approx"], lam=options["lam"])
    if key == "spsa":
        return qml.SPSAOptimizer(
            maxiter=int(ctx.config.steps),
            c=options["c"],
            alpha=options["alpha"],
            gamma=options["gamma"],
            A=options.get("A"),
            a=options.get("a"),
        )
    raise ValueError(f"unsupported PennyLane optimizer {key!r}.")  # pragma: no cover


def _run_pennylane_stepper(ctx: _RunContext, initial: np.ndarray, recorder: _RestartRecorder) -> dict[str, Any]:
    optimizer = _build_pennylane_optimizer(ctx)
    parameters = ctx.pnp.array(initial, requires_grad=True)
    step_kwargs: dict[str, Any] = {}
    if ctx.config.optimizer == "qng":
        step_kwargs["metric_tensor_fn"] = ctx.qml.metric_tensor(
            ctx.energy_qnode, approx=ctx.config.resolved_options["approx"]
        )
    for _ in range(ctx.config.steps):
        ctx.check_cancel()
        parameters, _ = optimizer.step_and_cost(ctx.cost, parameters, **step_kwargs)
        recorder.record(parameters, float(ctx.cost(parameters)))
    return {}


def _parameter_frequencies(view: CandidateView, trainable_parameter_ids: tuple[str, ...]) -> list[list[float]]:
    """Positive frequencies of the energy as a function of each trainable parameter.

    A parameter entering gates with generator eigenvalues ``E_1, ..., E_m``
    produces the frequencies ``|s - s'|`` for all sums ``s`` of one eigenvalue
    per gate (Schuld et al. 2021). Single-qubit and Ising rotations contribute
    ``{1}``, controlled rotations ``{1/2, 1}``.
    """
    index_of = {parameter_id: index for index, parameter_id in enumerate(trainable_parameter_ids)}
    eigen_sums: list[set[float]] = [{0.0} for _ in trainable_parameter_ids]
    for operation in view.operations:
        eigenvalues = _GATE_GENERATOR_EIGENVALUES.get(operation.gate_name)
        if eigenvalues is None:
            continue
        for parameter in operation.parameters:
            if parameter.get("kind") != "reference":
                continue
            index = index_of.get(str(parameter.get("parameter_id")))
            if index is None:
                continue
            eigen_sums[index] = {current + eig for current in eigen_sums[index] for eig in eigenvalues}
    frequencies: list[list[float]] = []
    for sums in eigen_sums:
        positive = sorted({round(abs(a - b), 10) for a in sums for b in sums} - {0.0})
        frequencies.append(positive or [1.0])
    return frequencies


def _base_frequency(frequencies: list[float]) -> float:
    """Largest frequency of which every entry is an integer multiple."""
    fractions = [Fraction(value).limit_denominator(10**6) for value in frequencies]
    base = fractions[0]
    for item in fractions[1:]:
        base = Fraction(
            math.gcd(base.numerator * item.denominator, item.numerator * base.denominator),
            base.denominator * item.denominator,
        )
    return float(base)


class _FourierSubstep:
    """Exact minimisation of the energy along one parameter (Rotosolve substep).

    The energy restricted to parameter ``d`` is a trigonometric polynomial
    ``f(t) = a0 + sum_k a_k cos(w_k t) + b_k sin(w_k t)`` with the known
    frequencies ``w_k``. It is reconstructed from ``2R`` additional energy
    evaluations at equidistant shifts over one period and minimised in closed
    form (``R = 1``) or on a dense grid refined by Newton steps (``R > 1``).
    """

    def __init__(self, cost: Callable[[np.ndarray], Any], frequencies: list[list[float]], grid_points: int) -> None:
        self.cost = cost
        self.frequencies = [np.asarray(item, dtype=float) for item in frequencies]
        self.periods = [2.0 * math.pi / _base_frequency(item) for item in frequencies]
        self.grid_points = max(int(grid_points), 16)

    def minimize(self, parameters: np.ndarray, index: int, f0: float) -> tuple[np.ndarray, float]:
        """Return updated parameters and the (exact) energy after the update."""
        omega = self.frequencies[index]
        period = self.periods[index]
        R = len(omega)
        shifts = period * np.arange(0, 2 * R + 1) / (2 * R + 1)
        values = np.empty(2 * R + 1)
        values[0] = f0
        for j in range(1, 2 * R + 1):
            shifted = np.array(parameters, dtype=float)
            shifted[index] += shifts[j]
            values[j] = float(self.cost(shifted))
        design = np.concatenate(
            [np.ones((2 * R + 1, 1)), np.cos(np.outer(shifts, omega)), np.sin(np.outer(shifts, omega))], axis=1
        )
        coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
        a0, a, b = coefficients[0], coefficients[1 : R + 1], coefficients[R + 1 :]
        if R == 1:
            phase = math.atan2(float(b[0]), float(a[0]))
            t_min = (phase + math.pi) / float(omega[0])
            y_min = float(a0 - math.hypot(float(a[0]), float(b[0])))
        else:
            t_min, y_min = self._grid_newton(a0, a, b, omega, period)
        updated = np.array(parameters, dtype=float)
        updated[index] = math.remainder(updated[index] + t_min, period)
        return updated, y_min

    def _grid_newton(self, a0, a, b, omega, period) -> tuple[float, float]:
        grid = np.linspace(0.0, period, self.grid_points, endpoint=False)
        cos = np.cos(np.outer(grid, omega))
        sin = np.sin(np.outer(grid, omega))
        values = a0 + cos @ a + sin @ b
        best = int(np.argmin(values))
        t_min, y_min = float(grid[best]), float(values[best])

        def f(t):
            return float(a0 + np.cos(omega * t) @ a + np.sin(omega * t) @ b)

        t = t_min
        for _ in range(12):
            first = float((-omega * a) @ np.sin(omega * t) + (omega * b) @ np.cos(omega * t))
            second = float((-(omega**2) * a) @ np.cos(omega * t) - ((omega**2) * b) @ np.sin(omega * t))
            if second <= 0.0 or not math.isfinite(second):
                break
            candidate = t - first / second
            value = f(candidate)
            if value >= y_min:
                break
            t, y_min = candidate, value
            if abs(first / second) < 1e-12:
                break
        return t, y_min


def _run_rotosolve(ctx: _RunContext, initial: np.ndarray, recorder: _RestartRecorder) -> dict[str, Any]:
    substep = _FourierSubstep(
        ctx.cost,
        _parameter_frequencies(ctx.view, ctx.trainable_parameter_ids),
        int(ctx.config.resolved_options["grid_points"]),
    )
    parameters = np.array(initial, dtype=float)
    current = recorder.trajectory[0]
    for _ in range(ctx.config.steps):
        ctx.check_cancel()
        for index in range(ctx.parameter_count):
            parameters, current = substep.minimize(parameters, index, current)
        recorder.record(parameters, current)
    return {}


def _rotation_operations(view: CandidateView, trainable_parameter_ids: tuple[str, ...]) -> dict[int, list[tuple[str, str]]]:
    """Map trainable parameter index -> [(operation_id, gate_name)] of the rotations it drives."""
    index_of = {parameter_id: index for index, parameter_id in enumerate(trainable_parameter_ids)}
    rotations: dict[int, list[tuple[str, str]]] = {}
    for operation in view.operations:
        if operation.gate_name not in ROTATION_GATES:
            continue
        for parameter in operation.parameters:
            if parameter.get("kind") != "reference":
                continue
            index = index_of.get(str(parameter.get("parameter_id")))
            if index is not None:
                rotations.setdefault(index, []).append((operation.operation_id, operation.gate_name))
    return rotations


def _run_rotoselect(ctx: _RunContext, initial: np.ndarray, recorder: _RestartRecorder) -> dict[str, Any]:
    """Rotoselect: Rotosolve sweep with per-parameter choice of the RX/RY/RZ generator.

    Swapping the generator of a single-qubit rotation does not change the
    parameter's frequency spectrum, so the Fourier substep stays exact for
    every generator choice.
    """
    rotations = _rotation_operations(ctx.view, ctx.trainable_parameter_ids)
    substep = _FourierSubstep(
        ctx.cost,
        _parameter_frequencies(ctx.view, ctx.trainable_parameter_ids),
        int(ctx.config.resolved_options["grid_points"]),
    )
    overrides = ctx.rotation_overrides
    selected = {index: operations[0][1] for index, operations in rotations.items()}

    def apply(index: int, gate: str) -> None:
        for operation_id, _ in rotations[index]:
            overrides[operation_id] = gate

    def apply_all(choice: Mapping[int, str]) -> None:
        for index, gate in choice.items():
            apply(index, gate)

    parameters = np.array(initial, dtype=float)
    current = recorder.trajectory[0]
    best_selected = dict(selected)
    for _ in range(ctx.config.steps):
        ctx.check_cancel()
        for index in range(ctx.parameter_count):
            if index not in rotations:
                parameters, current = substep.minimize(parameters, index, current)
                continue
            best_choice: tuple[float, str, np.ndarray] | None = None
            for gate in ROTATION_GATES:
                apply(index, gate)
                f0 = current if gate == selected[index] else float(ctx.cost(parameters))
                candidate, value = substep.minimize(parameters, index, f0)
                if best_choice is None or value < best_choice[0]:
                    best_choice = (value, gate, candidate)
            current, selected[index], parameters = best_choice
            apply(index, selected[index])
        previous_best = recorder.best_energy
        recorder.record(parameters, current)
        if recorder.best_energy < previous_best:
            best_selected = dict(selected)
    apply_all(best_selected)
    report = [
        {
            "parameter_index": index,
            "parameter_id": ctx.trainable_parameter_ids[index],
            "operation_ids": [operation_id for operation_id, _ in operations],
            "original": operations[0][1],
            "selected": best_selected[index],
        }
        for index, operations in sorted(rotations.items())
    ]
    return {"selected_generators": report, "rotation_overrides": dict(overrides)}


def _run_scipy(ctx: _RunContext, initial: np.ndarray, recorder: _RestartRecorder) -> dict[str, Any]:
    from scipy.optimize import minimize

    key = ctx.config.optimizer
    method = _SCIPY_METHODS[key]

    def fun(x) -> float:
        return float(ctx.cost(np.asarray(x, dtype=float)))

    jac = None
    if key == "l_bfgs_b":
        gradient = ctx.qml.grad(ctx.cost)

        def jac(x):
            return np.asarray(gradient(ctx.pnp.array(x, requires_grad=True)), dtype=float).reshape(-1)

    def callback(intermediate_result):
        x = getattr(intermediate_result, "x", intermediate_result)
        value = getattr(intermediate_result, "fun", None)
        recorder.record(x, fun(x) if value is None else float(value))

    options: dict[str, Any] = {"maxiter": int(ctx.config.steps)}
    options.update({k: v for k, v in ctx.config.resolved_options.items() if k not in {"maxiter"}})
    result = minimize(fun, np.array(initial, dtype=float), method=method, jac=jac, callback=callback, options=options)
    final = np.asarray(result.x, dtype=float).reshape(-1)
    if recorder.iterations == 0 or not np.allclose(final, recorder.last_parameters):
        recorder.record(final, fun(final))
    return {"scipy_message": str(result.message), "scipy_success": bool(result.success)}


def _normalized_error(value: float, exact: float | None) -> float | None:
    if exact is None:
        return None
    if abs(exact) < 1e-12:
        return abs(value - exact)
    return abs((value - exact) / exact)


def _state_summary(materialized, parameters, ground_state, n_qubits: int, top: int = 8) -> dict[str, Any]:
    state = np.asarray(materialized.state_callable(np.asarray(parameters, dtype=float)), dtype=complex).reshape(-1)
    state = state / np.linalg.norm(state)
    probabilities = np.abs(state) ** 2
    order = np.argsort(-probabilities)[:top]
    amplitudes = [
        {
            "basis": format(int(index), f"0{n_qubits}b"),
            "probability": float(probabilities[index]),
            "amplitude_real": float(np.real(state[index])),
            "amplitude_imag": float(np.imag(state[index])),
        }
        for index in order
    ]
    fidelity = None
    if ground_state is not None:
        fidelity = float(abs(np.vdot(ground_state, state)) ** 2)
    return {"top_amplitudes": amplitudes, "ground_state_fidelity": fidelity}


__all__ = [
    "OPTIMIZERS",
    "OPTIMIZER_FAMILIES",
    "OPTIMIZER_INDEX",
    "OPTIMIZER_SPECS",
    "OptimizerSpec",
    "VQECancelled",
    "VQEConfig",
    "normalize_optimizer_name",
    "optimizer_catalog",
    "run_vqe",
]

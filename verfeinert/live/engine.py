"""Interactive evolutionary ansatz search built on the public Verfeinert pieces.

The engine composes the canonical building blocks (Sanz19 templates, canonical
Candidate JSON export, analyzer materialization and metrics, the canonical
mutation factory) into a streaming loop that emits JSON-safe events while it
runs, so a UI can show new circuits as they are discovered.

Score follows the manuscript: ``expressibility x trainability`` with the
resource cost (manuscript hardware weights) reported and optionally used as a
feasibility constraint. Expressibility and trainability are estimated with the
manuscript protocol (independent trials, mean +- standard deviation).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
import hashlib
import json
import multiprocessing
import os
import time
import traceback
from typing import Any

import numpy as np

from verfeinert.ansatz_analyzer.config import (
    AnalyzerExecutionPermissions,
    CircuitMaterializationConfig,
    StructuralCostConfig,
)
from verfeinert.ansatz_analyzer.materialization import materialize_candidate
from verfeinert.ansatz_analyzer.metrics.expressibility import (
    ExpressibilityConfig,
    compute_expressibility_metric,
)
from verfeinert.ansatz_analyzer.metrics.hamiltonians import HamiltonianSpec
from verfeinert.ansatz_analyzer.metrics.protocol import (
    PAPER_COST_WEIGHTS,
    protocol_metric_configs,
    protocol_summary,
)
from verfeinert.ansatz_analyzer.metrics.structural_cost import compute_structural_costs
from verfeinert.ansatz_analyzer.metrics.trainability import (
    TrainabilityConfig,
    compute_trainability_metric,
)
from verfeinert.ansatz_analyzer.models import CandidateView
from verfeinert.ansatz_evolver.mutation.requests import MutationRequest
from verfeinert.ansatz_generator.exporters.candidate_json import (
    CandidateJsonExportConfig,
    export_candidate_json,
)
from verfeinert.ansatz_generator.factories import CanonicalMutationFactory
from verfeinert.ansatz_generator.templates.sanz19 import (
    SANZ19_TEMPLATE_IDS,
    build_sanz19_candidate_record,
    normalize_sanz19_template_id,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError
from verfeinert.core.io.serialization import to_json_safe


MUTATION_TYPES = ("insert", "replace", "remove", "swap")
DEFAULT_MUTATION_WEIGHTS = {"insert": 0.4, "replace": 0.3, "remove": 0.15, "swap": 0.15}
SINGLE_QUBIT_GATE_POOL = ("rx", "ry", "rz", "h")
TWO_QUBIT_GATE_POOL = ("cx", "cz", "crx", "cry", "crz")
PARAMETERIZED_GATES = {"rx", "ry", "rz", "crx", "cry", "crz", "isingxx", "isingyy", "isingzz"}
SANZ19_TEMPLATE_DESCRIPTIONS = {
    "A01": "RX-RZ rotations, no entanglement",
    "A02": "RX-RZ + CNOT chain (linear)",
    "A03": "RX-RZ + CRZ chain (linear)",
    "A04": "RX-RZ + CRX chain (linear)",
    "A05": "RX-RZ + all-to-all CRZ + RX-RZ",
    "A06": "RX-RZ + all-to-all CRX + RX-RZ",
    "A07": "RX-RZ + brick CRZ layers (linear)",
    "A08": "RX-RZ + brick CRX layers (linear)",
    "A09": "H + CZ chain + RX (linear)",
    "A10": "RY + CZ ring + RY (circular)",
    "A11": "RY-RZ + brick CNOT (linear)",
    "A12": "RY-RZ + brick CZ (linear)",
    "A13": "RY + CRZ ring + RY + inverse ring (circular)",
    "A14": "RY + CRX ring + RY + inverse ring (circular)",
    "A15": "RY + CNOT ring + RY + inverse ring (circular)",
    "A16": "RX-RZ + two CRZ brick layers (linear)",
    "A17": "RX-RZ + two CRX brick layers (linear)",
    "A18": "RX-RZ + CRZ ring (circular)",
    "A19": "RX-RZ + CRX ring (circular)",
}


class LiveEngineError(ValueError):
    """Raised when the live evolution configuration is invalid."""


class LiveRunCancelled(RuntimeError):
    """Raised internally when a run is cancelled."""


@dataclass(frozen=True)
class LiveRunConfig:
    """User-facing configuration of one interactive evolution run."""

    n_qubits: int = 4
    hamiltonian: HamiltonianSpec = field(default_factory=lambda: HamiltonianSpec("tfim"))
    n_trials: int = 3
    protocol: str = "paper"
    n_pairs: int | None = None
    n_bins: int | None = None
    n_samples: int | None = None
    template_ids: tuple[str, ...] = SANZ19_TEMPLATE_IDS
    layers: tuple[int, ...] = (1,)
    max_generations: int = 5
    elite_size: int = 4
    children_per_parent: int = 3
    cost_threshold: float | None = None
    cost_weights: Mapping[str, float] = field(default_factory=lambda: dict(PAPER_COST_WEIGHTS))
    random_seed: int = 12345
    workers: int = 1
    mutation_types: tuple[str, ...] = MUTATION_TYPES
    max_mutation_attempts: int = 30
    diff_method: str = "best"
    run_id: str = "live"

    def __post_init__(self) -> None:
        if int(self.n_qubits) < 2:
            raise LiveEngineError("n_qubits must be at least 2.")
        if int(self.n_qubits) > 20:
            raise LiveEngineError("n_qubits above 20 is not supported by the state-vector simulator.")
        object.__setattr__(self, "n_qubits", int(self.n_qubits))
        object.__setattr__(self, "hamiltonian", HamiltonianSpec.from_mapping(self.hamiltonian))
        if int(self.n_trials) < 1:
            raise LiveEngineError("n_trials must be positive.")
        object.__setattr__(self, "n_trials", int(self.n_trials))
        if self.protocol not in ("paper", "fast", "custom"):
            raise LiveEngineError("protocol must be paper, fast or custom.")
        for name in ("n_pairs", "n_bins", "n_samples"):
            value = getattr(self, name)
            if value is not None and int(value) < 2:
                raise LiveEngineError(f"{name} must be at least 2.")
        try:
            templates = tuple(normalize_sanz19_template_id(item) for item in self.template_ids)
        except (KeyError, TypeError) as exc:
            raise LiveEngineError(f"unknown Sanz19 template in template_ids: {exc}") from exc
        if not templates:
            raise LiveEngineError("template_ids must not be empty.")
        object.__setattr__(self, "template_ids", tuple(dict.fromkeys(templates)))
        layers = tuple(int(item) for item in self.layers)
        if not layers or any(layer < 1 for layer in layers):
            raise LiveEngineError("layers must contain positive integers.")
        object.__setattr__(self, "layers", tuple(dict.fromkeys(layers)))
        if int(self.max_generations) < 0:
            raise LiveEngineError("max_generations must be non-negative.")
        if int(self.elite_size) < 1:
            raise LiveEngineError("elite_size must be positive.")
        if int(self.children_per_parent) < 1:
            raise LiveEngineError("children_per_parent must be positive.")
        if self.cost_threshold is not None and float(self.cost_threshold) <= 0.0:
            raise LiveEngineError("cost_threshold must be positive when provided.")
        object.__setattr__(self, "cost_weights", {str(k): float(v) for k, v in dict(self.cost_weights).items()})
        object.__setattr__(self, "random_seed", int(self.random_seed))
        object.__setattr__(self, "workers", max(1, int(self.workers)))
        mutation_types = tuple(str(item) for item in self.mutation_types)
        unknown = sorted(set(mutation_types) - set(MUTATION_TYPES))
        if unknown:
            raise LiveEngineError(f"unsupported mutation types: {unknown}")
        if not mutation_types:
            raise LiveEngineError("mutation_types must not be empty.")
        object.__setattr__(self, "mutation_types", mutation_types)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "LiveRunConfig":
        """Build a config from a JSON payload (as sent by the UI)."""
        data = dict(mapping or {})
        hamiltonian = data.get("hamiltonian", "tfim")
        if isinstance(hamiltonian, str):
            hamiltonian = {"kind": hamiltonian, "parameters": data.get("hamiltonian_parameters") or {}}
        elif isinstance(hamiltonian, Mapping) and data.get("hamiltonian_parameters"):
            hamiltonian = {**dict(hamiltonian), "parameters": data.get("hamiltonian_parameters")}
        template_ids = data.get("template_ids") or SANZ19_TEMPLATE_IDS
        if isinstance(template_ids, str):
            template_ids = [item.strip() for item in template_ids.split(",") if item.strip()]
        layers = data.get("layers") or (1,)
        if isinstance(layers, (int, str)):
            layers = [int(item) for item in str(layers).split(",") if str(item).strip()]
        kwargs: dict[str, Any] = {
            "n_qubits": data.get("n_qubits", 4),
            "hamiltonian": HamiltonianSpec.from_mapping(hamiltonian),
            "n_trials": data.get("n_trials", 3),
            "protocol": data.get("protocol", "paper"),
            "n_pairs": data.get("n_pairs"),
            "n_bins": data.get("n_bins"),
            "n_samples": data.get("n_samples"),
            "template_ids": tuple(template_ids),
            "layers": tuple(int(item) for item in layers),
            "max_generations": data.get("max_generations", 5),
            "elite_size": data.get("elite_size", 4),
            "children_per_parent": data.get("children_per_parent", 3),
            "cost_threshold": data.get("cost_threshold"),
            "random_seed": data.get("random_seed", 12345),
            "workers": data.get("workers", 1),
            "run_id": str(data.get("run_id", "live")),
        }
        if data.get("cost_weights"):
            kwargs["cost_weights"] = dict(data["cost_weights"])
        if data.get("mutation_types"):
            kwargs["mutation_types"] = tuple(data["mutation_types"])
        if data.get("max_mutation_attempts"):
            kwargs["max_mutation_attempts"] = int(data["max_mutation_attempts"])
        if data.get("diff_method"):
            kwargs["diff_method"] = str(data["diff_method"])
        return cls(**kwargs)

    def metric_configs(self) -> dict[str, dict[str, Any]]:
        """Return expressibility/trainability configs for this run."""
        protocol = "fast" if self.protocol == "fast" else "paper"
        configs = protocol_metric_configs(
            protocol,
            n_trials=self.n_trials,
            hamiltonian=self.hamiltonian,
            rng_seed=self.random_seed,
        )
        if self.n_pairs is not None:
            configs["expressibility"]["n_pairs"] = int(self.n_pairs)
        if self.n_bins is not None:
            configs["expressibility"]["n_bins"] = int(self.n_bins)
        if self.n_samples is not None:
            configs["trainability"]["n_repeats"] = int(self.n_samples)
        return configs

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot."""
        return to_json_safe(
            {
                "n_qubits": self.n_qubits,
                "hamiltonian": self.hamiltonian.to_dict(),
                "n_trials": self.n_trials,
                "protocol": self.protocol,
                "metric_configs": self.metric_configs(),
                "template_ids": list(self.template_ids),
                "layers": list(self.layers),
                "max_generations": self.max_generations,
                "elite_size": self.elite_size,
                "children_per_parent": self.children_per_parent,
                "cost_threshold": self.cost_threshold,
                "cost_weights": dict(self.cost_weights),
                "random_seed": self.random_seed,
                "workers": self.workers,
                "mutation_types": list(self.mutation_types),
                "max_mutation_attempts": self.max_mutation_attempts,
                "diff_method": self.diff_method,
                "run_id": self.run_id,
            },
        )


# --------------------------------------------------------------------------- evaluation


def candidate_operations_summary(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return a compact gate list used by UIs to draw the circuit."""
    circuit = dict(document["circuit"])
    parameter_index = {
        str(parameter["parameter_id"]): index
        for index, parameter in enumerate(
            item for item in circuit.get("parameters", []) if str(item.get("kind")) == "trainable"
        )
    }
    summary = []
    for operation in circuit["operations"]:
        gate = operation.get("gate")
        name = gate.get("name") if isinstance(gate, Mapping) else str(gate)
        params = []
        for parameter in operation.get("parameters", ()):
            if parameter.get("kind") == "reference":
                params.append({"kind": "trainable", "index": parameter_index.get(str(parameter.get("parameter_id")))})
            else:
                params.append({"kind": "literal", "value": parameter.get("value")})
        summary.append({"gate": str(name).lower(), "qubits": [int(q) for q in operation["qubits"]], "parameters": params})
    return summary


def structural_dedupe_key(document: Mapping[str, Any]) -> str:
    """Return a hash of the gate sequence ignoring parameter identifiers."""
    payload = [
        (op["gate"], tuple(op["qubits"]), tuple((p["kind"], p.get("value")) for p in op["parameters"]))
        for op in candidate_operations_summary(document)
    ]
    blob = json.dumps([[gate, list(qubits), [list(p) for p in params]] for gate, qubits, params in payload])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evaluate_candidate_document(
    document: Mapping[str, Any],
    settings: Mapping[str, Any],
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Evaluate structural cost, expressibility and trainability for one candidate.

    ``settings`` carries JSON-safe ``expressibility``, ``trainability`` and
    ``structural_cost`` configuration mappings plus the materialization
    ``diff_method``. The function is importable (picklable) so that it can run
    inside worker processes.
    """
    started = time.perf_counter()
    view = CandidateView.from_document(dict(document))
    permissions = AnalyzerExecutionPermissions(allow_expensive_metrics=True, allow_qnode_execution=True)
    cost_config = StructuralCostConfig.from_mapping(dict(settings.get("structural_cost", {})))
    analysis = compute_structural_costs([view], config=cost_config)[0]
    result: dict[str, Any] = {
        "candidate_id": view.candidate_id,
        "n_qubits": view.n_qubits,
        "parameter_count": view.parameter_count,
        "depth": analysis.features.depth,
        "two_qubit_operation_count": analysis.features.two_qubit_operation_count,
        "operation_count": analysis.features.operation_count,
        "structural_cost": float(analysis.structural_cost),
        "structural_cost_clipped": float(analysis.clipped_structural_cost),
        "cost_components": to_json_safe(analysis.component_metadata),
        "operations": candidate_operations_summary(document),
        "status": "computed",
        "errors": [],
    }
    try:
        materialized = materialize_candidate(
            view,
            config=CircuitMaterializationConfig(enabled=True, diff_method=str(settings.get("diff_method", "best"))),
        )
    except Exception as exc:  # pragma: no cover - defensive, surfaced to the UI
        result["status"] = "failed"
        result["errors"].append(f"materialization: {exc}")
        result["elapsed_seconds"] = time.perf_counter() - started
        return result
    expressibility_config = ExpressibilityConfig.from_mapping(
        {**dict(settings.get("expressibility", {})), "backend_label": materialized.backend_label, "requires_qnode_execution": True},
    )
    trainability_config = TrainabilityConfig.from_mapping(
        {**dict(settings.get("trainability", {})), "backend_label": materialized.backend_label, "requires_qnode_execution": True},
    )
    expressibility = compute_expressibility_metric(
        view,
        materialized.state_callable,
        config=expressibility_config,
        permissions=permissions,
        materialized=materialized,
        should_cancel=should_cancel,
    )
    if should_cancel is not None and should_cancel():
        raise LiveRunCancelled("cancelled")
    trainability = compute_trainability_metric(
        view,
        materialized.state_callable,
        config=trainability_config,
        permissions=permissions,
        materialized=materialized,
        should_cancel=should_cancel,
    )
    result["metrics"] = {
        "structural_cost": analysis.metric.to_dict(),
        "expressibility": expressibility.to_dict(),
        "trainability": trainability.to_dict(),
    }
    if expressibility.status != "computed":
        result["status"] = "failed"
        result["errors"].append(f"expressibility: {expressibility.error}")
    if trainability.status != "computed":
        result["status"] = "failed"
        result["errors"].append(f"trainability: {trainability.error}")
    if result["status"] == "computed":
        expr_value = dict(expressibility.value)
        train_value = dict(trainability.value)
        result.update(
            {
                "expressibility": float(expr_value["expressibility"]),
                "expressibility_std": float(expr_value.get("expressibility_std", 0.0)),
                "expressibility_trials": [float(t["expressibility"]) for t in expressibility.metadata.get("trials", [])],
                "dkl": float(expr_value["dkl"]),
                "trainability": float(train_value["trainability"]),
                "trainability_std": float(train_value.get("trainability_std", 0.0)),
                "trainability_trials": [float(t["trainability"]) for t in trainability.metadata.get("trials", [])],
                "score": float(expr_value["expressibility"]) * float(train_value["trainability"]),
                "expressibility_seconds": float(expressibility.metadata.get("elapsed_seconds", 0.0)),
                "trainability_seconds": float(trainability.metadata.get("elapsed_seconds", 0.0)),
            },
        )
        # Score uncertainty by first-order error propagation of independent trials.
        e, de = result["expressibility"], result["expressibility_std"]
        t, dt = result["trainability"], result["trainability_std"]
        result["score_std"] = float(np.sqrt((t * de) ** 2 + (e * dt) ** 2))
    result["elapsed_seconds"] = time.perf_counter() - started
    return to_json_safe(result)


def _worker_evaluate(payload: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    document, settings = payload
    try:
        return evaluate_candidate_document(document, settings)
    except Exception as exc:  # pragma: no cover - surfaced through the event stream
        return {
            "candidate_id": document.get("candidate_id"),
            "status": "failed",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "traceback": traceback.format_exc(),
            "operations": candidate_operations_summary(document),
        }


# --------------------------------------------------------------------------- engine


@dataclass
class _CandidateState:
    document: dict[str, Any]
    generation: int
    parent_id: str | None
    label: str
    mutation: dict[str, Any] | None
    evaluation: dict[str, Any] | None = None

    @property
    def candidate_id(self) -> str:
        return str(self.document["candidate_id"])


class LiveEvolutionEngine:
    """Run an interactive evolution and stream JSON-safe events."""

    def __init__(
        self,
        config: LiveRunConfig,
        *,
        emit: Callable[[dict[str, Any]], Any] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config
        self._emit = emit or (lambda event: None)
        self._should_cancel = should_cancel or (lambda: False)
        self._rng = np.random.default_rng(config.random_seed)
        self._candidates: dict[str, _CandidateState] = {}
        self._seen_keys: set[str] = set()
        self._best_id: str | None = None
        self._factory = CanonicalMutationFactory(source_label="verfeinert.live.engine")
        self._settings: dict[str, Any] = {}
        self._started = time.perf_counter()
        self._child_counter = 0

    # ------------------------------------------------------------------ helpers
    def emit(self, event_type: str, **payload: Any) -> None:
        event = {"event_type": event_type, "elapsed_seconds": round(time.perf_counter() - self._started, 3), **payload}
        self._emit(to_json_safe(event))

    def _check_cancel(self) -> None:
        if self._should_cancel():
            raise LiveRunCancelled("run cancelled by user")

    @property
    def candidates(self) -> dict[str, _CandidateState]:
        return self._candidates

    def evaluated(self) -> list[dict[str, Any]]:
        """Return evaluation summaries of every computed candidate."""
        return [
            self._summary(state)
            for state in self._candidates.values()
            if state.evaluation is not None and state.evaluation.get("status") == "computed"
        ]

    def leaderboard(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return computed candidates sorted by descending score."""
        rows = sorted(self.evaluated(), key=lambda item: (-item["score"], item["candidate_id"]))
        return rows[:limit] if limit is not None else rows

    def document(self, candidate_id: str) -> dict[str, Any] | None:
        state = self._candidates.get(candidate_id)
        return None if state is None else dict(state.document)

    def _summary(self, state: _CandidateState) -> dict[str, Any]:
        evaluation = dict(state.evaluation or {})
        evaluation.pop("traceback", None)
        feasible = True
        if self.config.cost_threshold is not None and evaluation.get("structural_cost") is not None:
            feasible = float(evaluation["structural_cost"]) <= float(self.config.cost_threshold)
        return {
            **evaluation,
            "candidate_id": state.candidate_id,
            "generation": state.generation,
            "parent_id": state.parent_id,
            "label": state.label,
            "mutation": state.mutation,
            "feasible": feasible,
            "template_id": state.document.get("metadata", {}).get("template_id"),
            "layer": state.document.get("metadata", {}).get("layer"),
        }

    # ------------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        """Execute the full evolution and return the final leaderboard."""
        config = self.config
        try:
            self.emit(
                "run_started",
                config=config.to_dict(),
                hamiltonian=config.hamiltonian.to_dict(),
                protocol=protocol_summary("fast" if config.protocol == "fast" else "paper"),
                ground_state_energy=self._ground_state_energy(),
                cpu_count=os.cpu_count(),
            )
            initial = self._initial_population()
            self._settings = self._evaluation_settings(initial)
            self.emit(
                "population_initialized",
                generation=0,
                candidates=[self._summary(state) for state in initial],
                reference_bounds=self._settings["structural_cost"]["reference_bounds"],
            )
            self._evaluate_states(initial, generation=0)
            self._finish_generation(0)
            for generation in range(1, config.max_generations + 1):
                self._check_cancel()
                parents = self._select_parents()
                if not parents:
                    self.emit("log", level="warning", message="No feasible parents available; stopping.")
                    break
                self.emit(
                    "generation_planned",
                    generation=generation,
                    parent_ids=[state.candidate_id for state in parents],
                )
                children = self._make_children(parents, generation)
                if not children:
                    self.emit("log", level="warning", message=f"Generation {generation}: no new circuits could be produced.")
                    self._finish_generation(generation)
                    continue
                self.emit(
                    "children_generated",
                    generation=generation,
                    candidates=[self._summary(state) for state in children],
                )
                self._evaluate_states(children, generation=generation)
                self._finish_generation(generation)
            leaderboard = self.leaderboard()
            self.emit("run_completed", leaderboard=leaderboard[:25], evaluated_count=len(leaderboard))
            return {"status": "completed", "leaderboard": leaderboard}
        except LiveRunCancelled:
            leaderboard = self.leaderboard()
            self.emit("run_cancelled", leaderboard=leaderboard[:25], evaluated_count=len(leaderboard))
            return {"status": "cancelled", "leaderboard": leaderboard}
        except Exception as exc:
            self.emit("run_failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            return {"status": "failed", "error": str(exc), "leaderboard": self.leaderboard()}

    def _ground_state_energy(self) -> float | None:
        if self.config.n_qubits > 14:
            return None
        try:
            return float(self.config.hamiltonian.ground_state_energy(self.config.n_qubits))
        except Exception:  # pragma: no cover - defensive
            return None

    def _initial_population(self) -> list[_CandidateState]:
        config = self.config
        states: list[_CandidateState] = []
        export_config = CandidateJsonExportConfig(
            candidate_id_prefix=f"{config.run_id}-g0",
            n_qubits=config.n_qubits,
            source_label="verfeinert.live.engine",
            discover_git_commit=False,
            metadata={"live_run_id": config.run_id},
        )
        for template_id in config.template_ids:
            for layer in config.layers:
                try:
                    record = build_sanz19_candidate_record(template_id, layer, n_qubits=config.n_qubits)
                except ValueError as exc:
                    self.emit("log", level="warning", message=f"{template_id}-L{layer} skipped: {exc}")
                    continue
                document = export_candidate_json(record, config=export_config)
                key = structural_dedupe_key(document)
                if key in self._seen_keys:
                    continue
                self._seen_keys.add(key)
                state = _CandidateState(
                    document=document,
                    generation=0,
                    parent_id=None,
                    label=f"{template_id}-L{layer}",
                    mutation=None,
                )
                self._candidates[state.candidate_id] = state
                states.append(state)
        if not states:
            raise LiveEngineError("The initial population is empty.")
        return states

    def _evaluation_settings(self, initial: Sequence[_CandidateState]) -> dict[str, Any]:
        views = [CandidateView.from_document(state.document) for state in initial]
        base_cost = StructuralCostConfig(component_weights=dict(self.config.cost_weights), reference_id="live-generation-0")
        analyses = compute_structural_costs(views, config=base_cost)
        bounds = {
            component: dict(values)
            for component, values in analyses[0].reference_bounds.items()
        }
        for component, values in bounds.items():
            if values["max"] <= values["min"]:
                values["max"] = values["min"] + 1.0
        metric_configs = self.config.metric_configs()
        return to_json_safe(
            {
                "expressibility": metric_configs["expressibility"],
                "trainability": metric_configs["trainability"],
                "structural_cost": {
                    "reference_id": "live-generation-0",
                    "reference_bounds": bounds,
                    "component_weights": dict(self.config.cost_weights),
                    "allow_operation_count_as_depth_proxy": True,
                },
                "diff_method": self.config.diff_method,
            },
        )

    def _evaluate_states(self, states: Sequence[_CandidateState], *, generation: int) -> None:
        pending = [state for state in states if state.evaluation is None]
        if not pending:
            return
        if self.config.workers > 1 and len(pending) > 1:
            try:
                self._evaluate_parallel(pending, generation=generation)
                return
            except LiveRunCancelled:
                raise
            except Exception as exc:
                self.emit("log", level="warning", message=f"Parallel evaluation unavailable ({exc}); falling back to sequential.")
        for state in pending:
            if state.evaluation is not None:
                continue
            self._check_cancel()
            self.emit("candidate_evaluating", candidate_id=state.candidate_id, generation=generation, label=state.label)
            try:
                evaluation = evaluate_candidate_document(state.document, self._settings, should_cancel=self._should_cancel)
            except LiveRunCancelled:
                raise
            except Exception as exc:
                evaluation = {"candidate_id": state.candidate_id, "status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}
            self._record_evaluation(state, evaluation)

    def _evaluate_parallel(self, pending: Sequence[_CandidateState], *, generation: int) -> None:
        context = multiprocessing.get_context("spawn")
        by_id = {state.candidate_id: state for state in pending}
        with ProcessPoolExecutor(max_workers=min(self.config.workers, len(pending)), mp_context=context) as executor:
            futures = {
                executor.submit(_worker_evaluate, (state.document, self._settings)): state.candidate_id
                for state in pending
            }
            for state in pending:
                self.emit("candidate_evaluating", candidate_id=state.candidate_id, generation=generation, label=state.label)
            remaining = set(futures)
            while remaining:
                done, remaining = wait(remaining, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    candidate_id = futures[future]
                    self._record_evaluation(by_id[candidate_id], future.result())
                if self._should_cancel():
                    for future in remaining:
                        future.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise LiveRunCancelled("run cancelled by user")

    def _record_evaluation(self, state: _CandidateState, evaluation: Mapping[str, Any]) -> None:
        state.evaluation = dict(evaluation)
        summary = self._summary(state)
        self.emit("candidate_evaluated", candidate=summary)
        if summary.get("status") != "computed" or not summary.get("feasible", True):
            return
        current_best = self._candidates.get(self._best_id) if self._best_id else None
        best_score = current_best.evaluation["score"] if current_best and current_best.evaluation else None
        if best_score is None or summary["score"] > best_score:
            previous = self._best_id
            self._best_id = state.candidate_id
            self.emit(
                "new_best",
                candidate=summary,
                previous_best_id=previous,
                previous_best_score=best_score,
                improvement=(None if best_score is None else summary["score"] - best_score),
            )

    def _finish_generation(self, generation: int) -> None:
        rows = self.leaderboard()
        members = [row for row in rows if row["generation"] == generation]
        self.emit(
            "generation_completed",
            generation=generation,
            evaluated_count=len(rows),
            generation_size=len(members),
            best=(rows[0] if rows else None),
            generation_best=(max(members, key=lambda item: item["score"]) if members else None),
            leaderboard=rows[:15],
            pareto_ids=self._pareto_ids(rows),
        )

    def _pareto_ids(self, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        feasible = [row for row in rows if row.get("feasible", True)]
        pareto = []
        for row in feasible:
            dominated = any(
                (other["expressibility"] >= row["expressibility"] and other["trainability"] >= row["trainability"])
                and (other["expressibility"] > row["expressibility"] or other["trainability"] > row["trainability"])
                for other in feasible
                if other is not row
            )
            if not dominated:
                pareto.append(row["candidate_id"])
        return pareto

    def _select_parents(self) -> list[_CandidateState]:
        rows = [row for row in self.leaderboard() if row.get("feasible", True)]
        return [self._candidates[row["candidate_id"]] for row in rows[: self.config.elite_size]]

    # ------------------------------------------------------------------ mutation
    def _make_children(self, parents: Sequence[_CandidateState], generation: int) -> list[_CandidateState]:
        children: list[_CandidateState] = []
        for parent_index, parent in enumerate(parents):
            produced = 0
            attempts = 0
            variant = 0
            while produced < self.config.children_per_parent and attempts < self.config.max_mutation_attempts:
                attempts += 1
                self._check_cancel()
                request = self._random_request(parent, generation=generation, variant=variant)
                variant += 1
                if request is None:
                    continue
                try:
                    child = self._factory(request, parent.document)
                except GeneratorValidationError as exc:
                    self.emit("log", level="debug", message=f"mutation rejected ({request.mutation_type}): {exc}")
                    continue
                except Exception as exc:
                    self.emit("log", level="debug", message=f"mutation failed ({request.mutation_type}): {type(exc).__name__}: {exc}")
                    continue
                metadata = dict(child.get("metadata", {}))
                if metadata.get("mutation_status") == "skipped_noop":
                    continue
                key = structural_dedupe_key(child)
                if key in self._seen_keys:
                    continue
                if not child["circuit"]["operations"]:
                    continue
                self._seen_keys.add(key)
                mutation = {
                    "type": request.mutation_type,
                    "parameters": dict(request.parameters),
                    "operation": metadata.get("mutation_operation"),
                }
                state = _CandidateState(
                    document=child,
                    generation=generation,
                    parent_id=parent.candidate_id,
                    label=f"{parent.label} > {_mutation_label(request)}",
                    mutation=mutation,
                )
                self._candidates[state.candidate_id] = state
                children.append(state)
                produced += 1
        return children

    def _random_request(self, parent: _CandidateState, *, generation: int, variant: int) -> MutationRequest | None:
        rng = self._rng
        operations = list(parent.document["circuit"]["operations"])
        n_ops = len(operations)
        n_qubits = self.config.n_qubits
        allowed = [item for item in self.config.mutation_types if item != "remove" or n_ops > 1]
        if not allowed:
            return None
        weights = np.array([DEFAULT_MUTATION_WEIGHTS[item] for item in allowed], dtype=float)
        mutation_type = str(rng.choice(allowed, p=weights / weights.sum()))
        self._child_counter += 1
        parameters: dict[str, Any] = {
            "candidate_id_template": f"{self.config.run_id}-g{generation}-c{self._child_counter:03d}-{{recipe_id}}",
        }
        recipe = mutation_type
        if mutation_type == "insert":
            two_qubit = bool(rng.random() < 0.5) and n_qubits >= 2
            if two_qubit:
                gate = str(rng.choice(TWO_QUBIT_GATE_POOL))
                control = int(rng.integers(n_qubits))
                if rng.random() < 0.7:
                    neighbours = [q for q in (control - 1, control + 1) if 0 <= q < n_qubits]
                    target = int(rng.choice(neighbours))
                else:
                    target = int(rng.choice([q for q in range(n_qubits) if q != control]))
                parameters.update({"gate": gate, "edge": [control, target]})
            else:
                gate = str(rng.choice(SINGLE_QUBIT_GATE_POOL))
                parameters.update({"gate": gate, "qubits": [int(rng.integers(n_qubits))]})
            parameters["insertion_index"] = int(rng.integers(n_ops + 1))
            recipe = f"ins-{gate}"
        elif mutation_type == "replace":
            target_index = int(rng.integers(n_ops))
            target = operations[target_index]
            arity = len(target["qubits"])
            current = str(target["gate"]["name"]).lower()
            pool = [g for g in (SINGLE_QUBIT_GATE_POOL if arity == 1 else TWO_QUBIT_GATE_POOL) if g != current]
            if not pool:
                return None
            gate = str(rng.choice(pool))
            parameters.update({"target_index": target_index, "gate": gate})
            recipe = f"rep-{gate}"
        elif mutation_type == "remove":
            parameters["target_index"] = int(rng.integers(n_ops))
            recipe = "rem"
        else:  # swap
            if n_ops < 2:
                return None
            first, second = (int(v) for v in rng.choice(n_ops, size=2, replace=False))
            parameters.update({"target_index": first, "swap_with_index": second})
            recipe = "swp"
        return MutationRequest(
            request_id=f"{parent.candidate_id}-g{generation}-v{variant}",
            parent_candidate_id=parent.candidate_id,
            generation_index=generation,
            mutation_type=mutation_type,
            policy_id="live-random-search",
            recipe_id=recipe,
            variant_index=variant,
            root_candidate_id=str(parent.document.get("lineage", {}).get("root_candidate_id") or parent.candidate_id),
            parameters=parameters,
            metadata={"parent_index": 0},
        )


def _mutation_label(request: MutationRequest) -> str:
    params = request.parameters
    if request.mutation_type == "insert":
        where = params.get("edge") or params.get("qubits")
        return f"insert {params.get('gate')} on {list(where)} @ {params.get('insertion_index')}"
    if request.mutation_type == "replace":
        return f"replace op {params.get('target_index')} with {params.get('gate')}"
    if request.mutation_type == "remove":
        return f"remove op {params.get('target_index')}"
    return f"swap ops {params.get('target_index')} and {params.get('swap_with_index')}"


def template_catalog() -> list[dict[str, Any]]:
    """Return the Sanz19 template catalog for UIs."""
    return [
        {"template_id": template_id, "description": SANZ19_TEMPLATE_DESCRIPTIONS.get(template_id, "")}
        for template_id in SANZ19_TEMPLATE_IDS
    ]


def run_live_evolution(
    config: LiveRunConfig | Mapping[str, Any],
    *,
    emit: Callable[[dict[str, Any]], Any] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[LiveEvolutionEngine, dict[str, Any]]:
    """Run an interactive evolution and return ``(engine, result)``."""
    resolved = config if isinstance(config, LiveRunConfig) else LiveRunConfig.from_mapping(config)
    engine = LiveEvolutionEngine(resolved, emit=emit, should_cancel=should_cancel)
    return engine, engine.run()


__all__ = [
    "LiveEngineError",
    "LiveEvolutionEngine",
    "LiveRunCancelled",
    "LiveRunConfig",
    "MUTATION_TYPES",
    "SANZ19_TEMPLATE_DESCRIPTIONS",
    "candidate_operations_summary",
    "evaluate_candidate_document",
    "run_live_evolution",
    "structural_dedupe_key",
    "template_catalog",
]

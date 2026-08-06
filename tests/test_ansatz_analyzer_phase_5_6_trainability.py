"""Phase 5.6 tests for optional Local-X trainability execution."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalyzerConfig,
    AnalyzerExecutionPermissions,
    StructuralCostConfig,
    load_candidate_views,
    validate_analysis_result_document,
)
from verfeinert.ansatz_analyzer.collections import metric_value
from verfeinert.ansatz_analyzer.metrics.trainability import (
    TrainabilityConfig,
    compute_trainability_metric,
    energy_from_state_local_x,
    make_local_x_hamiltonian_matrix,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}


def _state_callable(params):
    from pennylane import numpy as pnp

    angle = params[0] + params[1]
    return pnp.array([pnp.cos(angle), pnp.sin(angle), 0.0, 0.0], dtype=complex)


def _constant_state(_params):
    from pennylane import numpy as pnp

    return pnp.array([1.0, 0.0, 0.0, 0.0], dtype=complex)


def _candidate_view():
    return load_candidate_views(CANDIDATE_EXAMPLE)[0]


def _config(tmp_path: Path) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    output_root = tmp_path / "outputs"
    input_root.mkdir()
    return AnalyzerConfig(
        run_id="phase56-run",
        input_roots=(input_root,),
        output_root=output_root,
        selected_metrics=("structural_cost", "trainability"),
        permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        structural_cost=StructuralCostConfig(reference_bounds=EXPLICIT_REFERENCE_BOUNDS),
        metric_configs={
            "trainability": {
                "n_repeats": 3,
                "rng_seed": 123,
                "hamiltonian": "local_x",
            },
        },
    )


class AnalyzerPhase56TrainabilityTests(unittest.TestCase):
    def test_local_x_hamiltonian_matrix_is_explicit(self) -> None:
        one_qubit = make_local_x_hamiltonian_matrix(1, scale=2.0)
        two_qubit = make_local_x_hamiltonian_matrix(2)

        self.assertEqual(one_qubit, [[0.0, 2.0], [2.0, 0.0]])
        self.assertEqual(len(two_qubit), 4)
        self.assertEqual(len(two_qubit[0]), 4)

    def test_local_x_energy_matches_simple_states(self) -> None:
        zero = [1.0, 0.0]
        plus = [1.0 / math.sqrt(2.0), 1.0 / math.sqrt(2.0)]

        self.assertAlmostEqual(energy_from_state_local_x(zero, n_qubits=1), 0.0)
        self.assertAlmostEqual(energy_from_state_local_x(plus, n_qubits=1), 1.0)

    def test_trainability_config_rejects_tfim(self) -> None:
        with self.assertRaises(ValueError):
            TrainabilityConfig(hamiltonian="tfim")

    def test_direct_trainability_metric_is_deterministic(self) -> None:
        view = _candidate_view()
        permissions = AnalyzerExecutionPermissions(allow_expensive_metrics=True)
        config = TrainabilityConfig(n_repeats=3, rng_seed=999)

        first = compute_trainability_metric(
            view,
            _state_callable,
            config=config,
            permissions=permissions,
        )
        second = compute_trainability_metric(
            view,
            _state_callable,
            config=config,
            permissions=permissions,
        )

        self.assertEqual(first.status, "computed")
        self.assertEqual(first.value, second.value)
        self.assertGreaterEqual(first.value["trainability"], 0.0)
        self.assertEqual(first.metadata["hamiltonian"], "local_x")
        self.assertEqual(first.metadata["hamiltonian_kind"], "sum_x")
        self.assertEqual(first.metadata["hamiltonian_definition"], "H = sum_i X_i")
        self.assertEqual(first.metadata["gradient_backend"], "pennylane.qml.grad")
        self.assertEqual(first.metadata["rng_backend"], "numpy.random.default_rng")
        self.assertFalse(first.metadata["qnodes_executed"])

    def test_trainability_config_rejects_finite_difference_reference_path(self) -> None:
        with self.assertRaises(ValueError):
            TrainabilityConfig.from_mapping({"finite_difference_step": 1e-5})

    def test_inactive_gradients_produce_zero_trainability(self) -> None:
        metric = compute_trainability_metric(
            _candidate_view(),
            _constant_state,
            config=TrainabilityConfig(n_repeats=2, rng_seed=7),
            permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        )

        self.assertEqual(metric.status, "computed")
        self.assertEqual(metric.value["trainability"], 0.0)
        self.assertEqual(metric.metadata["active_parameter_count"], 0)

    def test_gradient_budget_guard_returns_failed_metric(self) -> None:
        metric = compute_trainability_metric(
            _candidate_view(),
            _state_callable,
            config=TrainabilityConfig(n_repeats=3, max_gradient_components=2),
            permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        )

        self.assertEqual(metric.status, "failed")
        self.assertIn("max_gradient_components", metric.error)

    def test_pipeline_integrates_computed_trainability_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp))
            record = AnalysisPipeline(config).run(
                CANDIDATE_EXAMPLE,
                metric_callables={
                    "trainability": {
                        "reference-a02-l1-parent": _state_callable,
                    },
                },
            )[0]
            payload = validate_analysis_result_document(record.to_dict())

        metrics = {metric["name"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics["trainability"]["status"], "computed")
        self.assertEqual(metrics["trainability"]["metadata"]["hamiltonian"], "local_x")
        self.assertIsInstance(metric_value(payload, "trainability"), float)
        self.assertFalse(payload["provenance"]["execution"]["qnodes_executed"])
        self.assertTrue(payload["provenance"]["execution"]["expensive_metrics_executed"])

    def test_pipeline_records_skipped_trainability_when_callable_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp))
            payload = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0].to_dict()

        metrics = {metric["name"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics["trainability"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()

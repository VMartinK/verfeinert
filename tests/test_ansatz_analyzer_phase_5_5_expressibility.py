"""Phase 5.5 tests for optional expressibility execution."""

from __future__ import annotations

import json
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
from verfeinert.ansatz_analyzer.config import AnalyzerConfigError
from verfeinert.ansatz_analyzer.metrics.expressibility import (
    ExpressibilityConfig,
    compute_expressibility_metric,
    haar_bin_masses,
    kl_divergence,
    normalize_state_vector,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}


def _state_callable(params):
    angle = sum(float(item) for item in params)
    return [math.cos(angle), math.sin(angle), 0.0, 0.0]


def _candidate_view():
    return load_candidate_views(CANDIDATE_EXAMPLE)[0]


def _config(tmp_path: Path, *, selected_metrics=("structural_cost", "expressibility")) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    output_root = tmp_path / "outputs"
    input_root.mkdir()
    return AnalyzerConfig(
        run_id="phase55-run",
        input_roots=(input_root,),
        output_root=output_root,
        selected_metrics=selected_metrics,
        permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        structural_cost=StructuralCostConfig(reference_bounds=EXPLICIT_REFERENCE_BOUNDS),
        metric_configs={
            "expressibility": {
                "n_pairs": 6,
                "n_bins": 5,
                "rng_seed": 123,
            },
        },
    )


class AnalyzerPhase55ExpressibilityTests(unittest.TestCase):
    def test_haar_bins_and_kl_divergence_are_valid(self) -> None:
        masses = haar_bin_masses(n_qubits=2, n_bins=5)

        self.assertAlmostEqual(sum(masses), 1.0)
        self.assertGreaterEqual(min(masses), 0.0)
        self.assertAlmostEqual(kl_divergence(masses, masses), 0.0)

    def test_state_vector_normalization_rejects_zero_state(self) -> None:
        normalized = normalize_state_vector([3.0, 4.0])

        self.assertAlmostEqual(sum(abs(item) ** 2 for item in normalized), 1.0)
        with self.assertRaises(ValueError):
            normalize_state_vector([0.0, 0.0])

    def test_direct_expressibility_metric_is_deterministic(self) -> None:
        view = _candidate_view()
        permissions = AnalyzerExecutionPermissions(allow_expensive_metrics=True)
        config = ExpressibilityConfig(n_pairs=6, n_bins=5, rng_seed=999)

        first = compute_expressibility_metric(
            view,
            _state_callable,
            config=config,
            permissions=permissions,
        )
        second = compute_expressibility_metric(
            view,
            _state_callable,
            config=config,
            permissions=permissions,
        )

        self.assertEqual(first.status, "computed")
        self.assertEqual(first.value, second.value)
        self.assertGreaterEqual(first.value["dkl"], 0.0)
        self.assertTrue(math.isfinite(first.value["expressibility"]))
        self.assertEqual(first.metadata["state_calls"], 12)
        self.assertEqual(first.metadata["qnode_calls"], 12)
        self.assertEqual(first.metadata["rng_backend"], "numpy.random.default_rng")
        self.assertEqual(first.metadata["rng_policy"], "per_circuit")
        self.assertFalse(first.metadata["qnodes_executed"])

    def test_expressibility_permission_denial_is_skipped(self) -> None:
        metric = compute_expressibility_metric(
            _candidate_view(),
            _state_callable,
            config=ExpressibilityConfig(n_pairs=2, n_bins=3),
            permissions=AnalyzerExecutionPermissions(),
        )

        self.assertEqual(metric.status, "skipped")
        self.assertIn("allow_expensive_metrics", metric.metadata["reason"])

    def test_expressibility_budget_guard_returns_failed_metric(self) -> None:
        metric = compute_expressibility_metric(
            _candidate_view(),
            _state_callable,
            config=ExpressibilityConfig(n_pairs=6, n_bins=5, max_total_state_calls=4),
            permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        )

        self.assertEqual(metric.status, "failed")
        self.assertIn("call limit", metric.error)

    def test_config_rejects_expensive_metric_without_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            with self.assertRaises(AnalyzerConfigError):
                AnalyzerConfig(
                    run_id="permission-test",
                    input_roots=(input_root,),
                    output_root=tmp_path / "outputs",
                    selected_metrics=("expressibility",),
                )

    def test_pipeline_integrates_computed_expressibility_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp))
            record = AnalysisPipeline(config).run(
                CANDIDATE_EXAMPLE,
                metric_callables={
                    "expressibility": {
                        "reference-a02-l1-parent": _state_callable,
                    },
                },
            )[0]
            payload = validate_analysis_result_document(record.to_dict())

        metrics = {metric["name"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics["expressibility"]["status"], "computed")
        self.assertIsInstance(metric_value(payload, "expressibility"), float)
        self.assertFalse(payload["provenance"]["execution"]["qnodes_executed"])
        self.assertTrue(payload["provenance"]["execution"]["expensive_metrics_executed"])
        json.dumps(payload, sort_keys=True)

    def test_pipeline_records_skipped_metric_when_callable_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp), selected_metrics=("expressibility",))
            payload = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0].to_dict()

        self.assertEqual(payload["metrics"][0]["name"], "expressibility")
        self.assertEqual(payload["metrics"][0]["status"], "skipped")
        self.assertFalse(payload["provenance"]["execution"]["expensive_metrics_executed"])


if __name__ == "__main__":
    unittest.main()

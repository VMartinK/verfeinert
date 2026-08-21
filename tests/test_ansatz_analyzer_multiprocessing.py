"""Tests for analyzer candidate-level multiprocessing execution."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisPipelineExecutionError,
    AnalyzerConfig,
    AnalyzerConfigError,
    AnalyzerExecutionPermissions,
    CircuitMaterializationConfig,
    StructuralCostConfig,
)
from verfeinert.core.config import ExecutionConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}


class ExplodingMetricCallables(dict):
    """Picklable mapping that fails inside worker callable resolution."""

    def get(self, key, default=None):
        raise RuntimeError("callable lookup exploded")


def _basis_state(_parameters):
    return np.array([1.0, 0.0, 0.0, 0.0], dtype=complex)


def _candidate(candidate_id: str) -> dict:
    candidate = json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))
    candidate["candidate_id"] = candidate_id
    candidate["lineage"]["root_candidate_id"] = candidate_id
    candidate["lineage"]["parent_candidate_id"] = None
    return candidate


def _staged_package(*candidate_ids: str) -> dict:
    candidates = [_candidate(candidate_id) for candidate_id in candidate_ids]
    return {
        "schema_version": "verfeinert.staged_package.v1",
        "package_id": "parallel-package-001",
        "manifest": {
            "package_kind": "candidate_package",
            "created_at": "2026-08-21T00:00:00Z",
            "producer": "analyzer-multiprocessing-test",
            "candidate_count": len(candidates),
            "schema_versions": {"candidate": "verfeinert.candidate.v1"},
            "execution_flags": {
                "qnodes_executed": False,
                "scientific_metrics_executed": False,
                "generated_callables_imported": False,
            },
        },
        "candidates": candidates,
        "artifacts": [],
        "provenance": {
            "created_at": "2026-08-21T00:00:00Z",
            "source": "analyzer-multiprocessing-test",
            "software_version": "test",
            "git_commit": None,
            "input_hashes": {},
        },
    }


def _config(
    tmp_path: Path,
    *,
    execution: ExecutionConfig,
    selected_metrics=("structural_cost",),
    metric_configs: dict | None = None,
) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    input_root.mkdir(parents=True, exist_ok=True)
    return AnalyzerConfig(
        run_id="parallel-run",
        input_roots=(input_root,),
        output_root=tmp_path / "outputs",
        selected_metrics=selected_metrics,
        execution=execution,
        permissions=AnalyzerExecutionPermissions(
            allow_expensive_metrics=True,
            allow_qnode_execution=False,
        ),
        structural_cost=StructuralCostConfig(reference_bounds=EXPLICIT_REFERENCE_BOUNDS),
        materialization=CircuitMaterializationConfig(enabled=False),
        metric_configs=metric_configs or {},
    )


def _semantic_payload(record) -> dict:
    payload = copy.deepcopy(record.to_dict())
    payload["provenance"]["created_at"] = "<runtime>"
    execution = payload["provenance"]["execution"]
    execution["execution_mode"] = "<mode>"
    execution["worker_count"] = "<workers>"
    execution["config"] = "<config>"
    for metric in payload["metrics"]:
        metric.get("metadata", {}).pop("elapsed_seconds", None)
    return payload


class AnalyzerMultiprocessingTests(unittest.TestCase):
    def test_parallel_structural_analysis_preserves_order_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(
                Path(tmp),
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
            )

            records = AnalysisPipeline(config).run(_staged_package("parallel-a", "parallel-b"))

        self.assertEqual(
            [record.candidate_ref["candidate_id"] for record in records],
            ["parallel-a", "parallel-b"],
        )
        for record in records:
            execution = record.to_dict()["provenance"]["execution"]
            self.assertEqual(execution["execution_mode"], "multiprocessing")
            self.assertEqual(execution["worker_count"], 2)

    def test_parallel_and_sequential_outputs_match_for_per_circuit_rng(self) -> None:
        package = _staged_package("parallel-a", "parallel-b")
        metric_callables = {
            "parallel-a": _basis_state,
            "parallel-b": _basis_state,
        }
        metric_configs = {
            "expressibility": {
                "n_pairs": 4,
                "n_bins": 3,
                "rng_seed": 77,
                "max_total_state_calls": 8,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sequential = _config(
                root / "sequential",
                execution=ExecutionConfig(),
                selected_metrics=("structural_cost", "expressibility"),
                metric_configs=metric_configs,
            )
            parallel = _config(
                root / "parallel",
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
                selected_metrics=("structural_cost", "expressibility"),
                metric_configs=metric_configs,
            )

            sequential_records = AnalysisPipeline(sequential).run(
                package,
                metric_callables=metric_callables,
            )
            parallel_records = AnalysisPipeline(parallel).run(
                package,
                metric_callables=metric_callables,
            )

        self.assertEqual(
            [_semantic_payload(record) for record in parallel_records],
            [_semantic_payload(record) for record in sequential_records],
        )
        for record in parallel_records:
            expressibility = next(metric for metric in record.metrics if metric.name == "expressibility")
            self.assertEqual(expressibility.metadata["rng_policy"], "per_circuit")

    def test_global_sequential_rng_policy_is_rejected_before_parallel_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(
                Path(tmp),
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
                selected_metrics=("expressibility",),
                metric_configs={"expressibility": {"rng_policy": "global_sequential"}},
            )

            with self.assertRaisesRegex(AnalyzerConfigError, "global_sequential"):
                AnalysisPipeline(config).run(_staged_package("parallel-a"))

    def test_unpicklable_explicit_callable_fails_without_sequential_fallback(self) -> None:
        def local_state_callable(_parameters):
            return np.array([1.0, 0.0, 0.0, 0.0], dtype=complex)

        with tempfile.TemporaryDirectory() as tmp:
            config = _config(
                Path(tmp),
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
                selected_metrics=("expressibility",),
                metric_configs={"expressibility": {"n_pairs": 1, "n_bins": 2}},
            )

            with self.assertRaises(AnalysisPipelineExecutionError) as raised:
                AnalysisPipeline(config).run(
                    _staged_package("parallel-a"),
                    metric_callables={"parallel-a": local_state_callable},
                )

        self.assertEqual(raised.exception.reason, "multiprocessing_execution_failed")
        self.assertIn("pickle", str(raised.exception).lower())

    def test_worker_failure_reports_candidate_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(
                Path(tmp),
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
                selected_metrics=("expressibility",),
                metric_configs={"expressibility": {"n_pairs": 1, "n_bins": 2}},
            )

            with self.assertRaises(AnalysisPipelineExecutionError) as raised:
                AnalysisPipeline(config).run(
                    _staged_package("parallel-a", "parallel-b"),
                    metric_callables=ExplodingMetricCallables(),
                )

        self.assertEqual(raised.exception.reason, "candidate_worker_failed")
        self.assertEqual(raised.exception.failures[0]["candidate_id"], "parallel-a")
        self.assertEqual(raised.exception.failures[0]["error_type"], "RuntimeError")
        self.assertIn("callable lookup exploded", raised.exception.failures[0]["error_message"])


if __name__ == "__main__":
    unittest.main()

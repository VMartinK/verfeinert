"""Phase 10.4 tests for comparison, compatibility, and tabular exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    ComparisonCompatibilityError,
    ComparisonConfig,
    ComparisonError,
    ComparisonSource,
    RankingConfig,
    compare_analysis_collections,
    read_comparison_result_json,
    validate_comparison_result_document,
)
from verfeinert.ansatz_analyzer.comparison import compatibility_report
from verfeinert.ansatz_analyzer.tables import write_comparison_csv, write_comparison_json


TRAINABILITY_CONFIG = {
    "n_qubits": 4,
    "n_repeats": 3,
    "trainability_n_pairs": 3,
    "parameter_low": -3.141592653589793,
    "parameter_high": 3.141592653589793,
    "rng_seed": 42,
    "rng_policy": "per_circuit",
    "active_grad_tol": 1e-10,
    "hamiltonian_kind": "sum_x",
    "hamiltonian": "local_x",
    "hamiltonian_scale": 1.0,
}
EXPRESSIBILITY_CONFIG = {
    "n_qubits": 4,
    "n_pairs": 3,
    "n_bins": 4,
    "parameter_low": 0.0,
    "parameter_high": 6.283185307179586,
    "rng_seed": 42,
    "rng_policy": "per_circuit",
    "dkl_floor": 1e-16,
    "histogram_epsilon": 1e-12,
}
COST_METADATA = {
    "cost_model": "reference_normalized_structural_cost",
    "definition": (
        "weighted average of reference-normalized parameter_count, depth, "
        "and two_qubit_operation_count"
    ),
    "reference_id": "shared-reference",
    "reference_bounds": {
        "parameter_count": {"min": 0.0, "max": 10.0},
        "depth": {"min": 0.0, "max": 20.0},
        "two_qubit_operation_count": {"min": 0.0, "max": 8.0},
    },
    "component_weights": {
        "parameter_count": 1.0,
        "depth": 1.0,
        "two_qubit_operation_count": 1.0,
    },
    "depth_source": "metadata.structural.depth",
}


def _result(
    candidate_id: str,
    *,
    expressibility: float,
    trainability: float,
    cost: float,
    source: str = "source-a",
    generation: int = 0,
    hamiltonian_kind: str = "sum_x",
    cost_reference_id: str = "shared-reference",
    output_path: str = "/tmp/ignored-a",
    display_label: str | None = None,
) -> dict:
    train_config = dict(TRAINABILITY_CONFIG)
    train_config["hamiltonian_kind"] = hamiltonian_kind
    train_config["hamiltonian"] = "local_x" if hamiltonian_kind == "sum_x" else hamiltonian_kind
    cost_metadata = dict(COST_METADATA)
    cost_metadata["reference_id"] = cost_reference_id
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {
            "candidate_id": candidate_id,
            "structural_hash": "1" * 64,
        },
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": {"expressibility": expressibility, "dkl": 10 ** -expressibility},
                "metadata": {"configuration": dict(EXPRESSIBILITY_CONFIG)},
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": {
                    "trainability": trainability,
                    "holmes_metric": trainability,
                    "mean_squared_gradient_active": trainability,
                },
                "metadata": {
                    "configuration": train_config,
                    "hamiltonian": train_config["hamiltonian"],
                    "hamiltonian_kind": hamiltonian_kind,
                    "hamiltonian_definition": "H = sum_i X_i" if hamiltonian_kind == "sum_x" else "H = sum_i Z_i",
                    "hamiltonian_scale": 1.0,
                },
            },
        ],
        "cost": {
            "structural_cost": cost,
            "parameter_count": 3,
            "operation_count": 5,
            "two_qubit_operation_count": 2,
            "metadata": cost_metadata,
        },
        "classifications": [],
        "provenance": {
            "created_at": "2026-08-13T00:00:00Z",
            "analyzer": "phase-10-4-test",
            "execution": {
                "qnodes_executed": False,
                "expensive_metrics_executed": False,
                "config": {"output_root": output_path},
            },
        },
        "metadata": {
            "display_label": display_label,
            "candidate_semantics": {
                "lineage": {
                    "generation": generation,
                    "root_candidate_id": f"root-{source}",
                    "parent_candidate_id": None if generation == 0 else f"parent-{source}",
                },
                "source_context": {
                    "layer": generation + 1,
                    "workflow_run_id": source,
                },
            },
        },
    }


def _source(source_id: str, rows: list[dict], *, role: str = "source") -> ComparisonSource:
    return ComparisonSource(
        source_id=source_id,
        role=role,
        collection=AnalysisResultCollection.from_records(
            rows,
            collection_id=f"{source_id}:analysis",
        ),
    )


class AnalyzerPhase104ComparisonTests(unittest.TestCase):
    def test_compatible_sources_produce_structured_comparison_and_exports(self) -> None:
        source_a = _source(
            "run-a",
            [
                _result("a-balanced", expressibility=2.0, trainability=2.0, cost=0.9, source="run-a"),
                _result("a-high-score-dominated", expressibility=9.0, trainability=1.0, cost=0.2, source="run-a"),
            ],
            role="reference",
        )
        source_b = _source(
            "run-b",
            [
                _result("b-frontier", expressibility=10.0, trainability=2.0, cost=0.7, source="run-b", generation=1),
                _result("b-costly", expressibility=4.0, trainability=8.0, cost=1.2, source="run-b", generation=1),
            ],
        )

        result = compare_analysis_collections(
            (source_a, source_b),
            config=ComparisonConfig(
                comparison_id="compatible",
                cost_thresholds=(1.0,),
                display_aliases={"b-frontier": "Frontier B"},
            ),
        )

        payload = validate_comparison_result_document(result.to_dict())
        self.assertEqual(payload["schema_version"], "verfeinert.comparison_result.v1")
        self.assertEqual(payload["sources"][0]["source_id"], "run-a")
        self.assertEqual(payload["sources"][0]["role"], "reference")
        self.assertTrue(payload["compatibility"]["compatible"])
        self.assertIn("b-frontier", result.global_frontier_candidate_ids)
        rows = {row.candidate_id: row for row in result.rows}
        self.assertFalse(rows["a-high-score-dominated"].is_global_pareto)
        self.assertGreater(rows["a-high-score-dominated"].score, rows["a-balanced"].score)
        self.assertEqual(rows["b-frontier"].display_label, "Frontier B")
        self.assertEqual(rows["b-frontier"].candidate_id, "b-frontier")
        self.assertEqual(rows["b-frontier"].lineage["generation"], 1)
        self.assertTrue(rows["b-costly"].is_global_pareto)
        self.assertFalse(rows["b-costly"].cost_eligibility["1p0"])

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            json_artifact = write_comparison_json(
                result,
                output_root=tmp_path / "outputs",
                run_id="phase104",
                input_roots=(input_root,),
            )
            csv_artifact = write_comparison_csv(
                result,
                output_root=tmp_path / "outputs",
                run_id="phase104",
                input_roots=(input_root,),
            )

            persisted = read_comparison_result_json(json_artifact.path)
            self.assertEqual(persisted.candidate_ids, result.candidate_ids)
            self.assertEqual(persisted.to_dict(), json.loads(json_artifact.path.read_text(encoding="utf-8")))
            with csv_artifact.path.open("r", encoding="utf-8", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(csv_rows[0]["comparison_id"], "compatible")
            self.assertIn("objective_trainability", csv_rows[0])
            self.assertIn("cost_eligible_1p0", csv_rows[0])
            self.assertEqual(len(json_artifact.sha256), 64)

    def test_comparison_result_schema_validation_rejects_invalid_payload(self) -> None:
        result = compare_analysis_collections(
            (
                _source("run-a", [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)]),
                _source("run-b", [_result("b", expressibility=3.0, trainability=2.0, cost=0.2)]),
            ),
            config=ComparisonConfig(comparison_id="schema-validation"),
        )

        bad_version = json.loads(json.dumps(result.to_dict()))
        bad_version["schema_version"] = "verfeinert.comparison_result.v0"
        with self.assertRaisesRegex(ComparisonError, "schema_version"):
            validate_comparison_result_document(bad_version)

        missing_row_identity = json.loads(json.dumps(result.to_dict()))
        del missing_row_identity["rows"][0]["candidate_id"]
        with self.assertRaisesRegex(ComparisonError, "candidate_id"):
            validate_comparison_result_document(missing_row_identity)

    def test_incompatible_hamiltonian_fails_clearly(self) -> None:
        source_a = _source(
            "run-a",
            [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)],
        )
        source_b = _source(
            "run-b",
            [_result("b", expressibility=2.0, trainability=1.0, cost=0.1, hamiltonian_kind="sum_z")],
        )

        with self.assertRaisesRegex(ComparisonCompatibilityError, "Hamiltonian"):
            compare_analysis_collections((source_a, source_b), config=ComparisonConfig())

        report = compatibility_report((source_a, source_b), config=ComparisonConfig())
        self.assertFalse(report.compatible)
        self.assertIn("incompatible_hamiltonian", [issue.code for issue in report.issues])

    def test_incompatible_cost_normalization_fails_clearly(self) -> None:
        source_a = _source(
            "run-a",
            [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)],
        )
        source_b = _source(
            "run-b",
            [_result("b", expressibility=2.0, trainability=1.0, cost=0.1, cost_reference_id="other-reference")],
        )

        with self.assertRaisesRegex(ComparisonCompatibilityError, "cost"):
            compare_analysis_collections((source_a, source_b), config=ComparisonConfig())

    def test_irrelevant_paths_and_presentation_do_not_invalidate_comparison(self) -> None:
        source_a = _source(
            "run-a",
            [_result("a", expressibility=2.0, trainability=1.0, cost=0.1, output_path="/tmp/a", display_label="Alpha")],
        )
        source_b = _source(
            "run-b",
            [_result("b", expressibility=3.0, trainability=1.5, cost=0.2, output_path="/tmp/b", display_label="Beta")],
        )

        report = compatibility_report((source_a, source_b), config=ComparisonConfig())

        self.assertTrue(report.compatible)
        self.assertIn("output_paths", report.ignored_differences)
        result = compare_analysis_collections((source_a, source_b), config=ComparisonConfig())
        self.assertEqual([row.display_label for row in result.rows], ["a", "b"])

    def test_multiple_comparisons_are_independent_objects(self) -> None:
        source_a = _source("run-a", [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)])
        source_b = _source("run-b", [_result("b", expressibility=3.0, trainability=1.5, cost=0.2)])
        source_c = _source("run-c", [_result("c", expressibility=1.0, trainability=3.0, cost=0.3)])

        first = compare_analysis_collections(
            (source_a, source_b),
            config=ComparisonConfig(comparison_id="a-vs-b"),
        )
        second = compare_analysis_collections(
            (source_b, source_c),
            config=ComparisonConfig(comparison_id="b-vs-c"),
        )

        self.assertEqual(first.comparison_id, "a-vs-b")
        self.assertEqual(second.comparison_id, "b-vs-c")
        self.assertEqual(first.candidate_ids, ("a", "b"))
        self.assertEqual(second.candidate_ids, ("b", "c"))

    def test_objective_directions_are_respected_in_global_pareto(self) -> None:
        source_a = _source("run-a", [_result("a", expressibility=1.0, trainability=1.0, cost=0.1)])
        source_b = _source("run-b", [_result("b", expressibility=2.0, trainability=2.0, cost=0.2)])

        maximize = compare_analysis_collections(
            (source_a, source_b),
            config=ComparisonConfig(comparison_id="maximize"),
        )
        mixed = compare_analysis_collections(
            (source_a, source_b),
            config=ComparisonConfig(
                comparison_id="mixed-directions",
                objectives=(
                    {"metric_name": "trainability", "direction": "minimize"},
                    {"metric_name": "expressibility", "direction": "maximize"},
                ),
            ),
        )

        self.assertEqual(maximize.global_frontier_candidate_ids, ("b",))
        self.assertEqual(set(mixed.global_frontier_candidate_ids), {"a", "b"})

    def test_comparison_does_not_invoke_analyzer_or_qnode_execution(self) -> None:
        source_a = _source("run-a", [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)])
        source_b = _source("run-b", [_result("b", expressibility=3.0, trainability=1.5, cost=0.2)])

        with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("must not run")):
            result = compare_analysis_collections((source_a, source_b), config=ComparisonConfig())

        self.assertTrue(result.compatibility.compatible)
        self.assertTrue(all(row.candidate_id in {"a", "b"} for row in result.rows))

    def test_nonvisual_comparison_and_csv_do_not_require_matplotlib(self) -> None:
        source_a = _source("run-a", [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)])
        source_b = _source("run-b", [_result("b", expressibility=3.0, trainability=1.5, cost=0.2)])

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("importlib.util.find_spec", return_value=None):
                result = compare_analysis_collections((source_a, source_b), config=ComparisonConfig())
                artifact = write_comparison_csv(
                    result,
                    output_root=Path(tmp) / "outputs",
                    run_id="no-matplotlib",
                )
                self.assertTrue(artifact.path.is_file())

    def test_payload_is_json_serializable(self) -> None:
        source_a = _source("run-a", [_result("a", expressibility=2.0, trainability=1.0, cost=0.1)])
        source_b = _source("run-b", [_result("b", expressibility=3.0, trainability=1.5, cost=0.2)])

        payload = compare_analysis_collections(
            (source_a, source_b),
            config=ComparisonConfig(
                comparison_id="serializable",
                ranking=RankingConfig(score_components={"expressibility": 1.0, "trainability": 1.0}),
            ),
        ).to_dict()

        json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["schema_version"], "verfeinert.comparison_result.v1")


if __name__ == "__main__":
    unittest.main()

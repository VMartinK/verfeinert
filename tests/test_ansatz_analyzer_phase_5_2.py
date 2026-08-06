"""Phase 5.2 tests for analyzer collections and classification primitives."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    AnalysisResultCollectionError,
    AnalyzerConfig,
    StructuralCostConfig,
    validate_analysis_result_document,
    write_analysis_result_json,
)
from verfeinert.ansatz_analyzer.classification import (
    ThresholdRule,
    classify_cost_eligibility,
    classify_invalid,
    classify_threshold,
)
from verfeinert.ansatz_analyzer.collections import cost_value, metric_value


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"

EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}


def _candidate_example() -> dict:
    return json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))


def _second_candidate() -> dict:
    candidate = copy.deepcopy(_candidate_example())
    candidate["candidate_id"] = "reference-a02-l1-second"
    candidate["identity"]["structural_hash"] = (
        "1111111111111111111111111111111111111111111111111111111111111111"
    )
    candidate["identity"]["lineage_hash"] = (
        "2222222222222222222222222222222222222222222222222222222222222222"
    )
    candidate["lineage"]["root_candidate_id"] = candidate["candidate_id"]
    candidate["metadata"]["structural"] = {"depth": 5}
    return candidate


def _staged_package() -> dict:
    return {
        "schema_version": "verfeinert.staged_package.v1",
        "package_id": "phase52-package-001",
        "manifest": {
            "package_kind": "candidate_package",
            "created_at": "2026-08-06T00:00:00Z",
            "producer": "phase-5-2-test",
            "candidate_count": 2,
            "execution_flags": {
                "qnodes_executed": False,
                "scientific_metrics_executed": False,
                "generated_callables_imported": False,
            },
        },
        "candidates": [_candidate_example(), _second_candidate()],
        "artifacts": [],
        "provenance": {
            "created_at": "2026-08-06T00:00:00Z",
            "source": "phase-5-2-test",
        },
    }


def _config(tmp_path: Path) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    output_root = tmp_path / "outputs"
    input_root.mkdir()
    return AnalyzerConfig(
        run_id="phase52-run",
        input_roots=(input_root,),
        output_root=output_root,
        structural_cost=StructuralCostConfig(
            reference_bounds=EXPLICIT_REFERENCE_BOUNDS,
            component_weights={
                "parameter_count": 2.0,
                "depth": 1.0,
                "two_qubit_operation_count": 1.0,
            },
        ),
    )


def _analysis_documents(tmp_path: Path) -> list[dict]:
    records = AnalysisPipeline(_config(tmp_path)).run(_staged_package())
    return [validate_analysis_result_document(record.to_dict()) for record in records]


class AnalyzerPhase52Tests(unittest.TestCase):
    def test_analysis_result_collection_is_ordered_and_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            documents = _analysis_documents(Path(tmp))
            collection = AnalysisResultCollection.from_records(documents)

        self.assertEqual(len(collection), 2)
        self.assertEqual(
            collection.candidate_ids,
            ("reference-a02-l1-parent", "reference-a02-l1-second"),
        )
        first = collection.get_by_candidate_id("reference-a02-l1-parent")
        self.assertAlmostEqual(cost_value(first, "structural_cost"), 0.5)
        self.assertAlmostEqual(metric_value(first, "structural_cost"), 0.5)
        self.assertEqual(
            list(collection.iter_with_metric("structural_cost"))[1]["candidate_ref"]["candidate_id"],
            "reference-a02-l1-second",
        )

    def test_analysis_result_collection_loads_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _config(tmp_path)
            records = AnalysisPipeline(config).run(_staged_package())
            for record in records:
                write_analysis_result_json(record, config)

            collection = AnalysisResultCollection.from_sources([tmp_path / "outputs" / "phase52-run"])

        self.assertEqual(collection.analysis_result_ids[0], "analysis-phase52-run-reference-a02-l1-parent")
        self.assertEqual(collection.analysis_result_ids[1], "analysis-phase52-run-reference-a02-l1-second")

    def test_analysis_result_collection_rejects_duplicate_candidate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            documents = _analysis_documents(Path(tmp))
            duplicate = copy.deepcopy(documents[1])
            duplicate["candidate_ref"]["candidate_id"] = documents[0]["candidate_ref"]["candidate_id"]

            with self.assertRaises(AnalysisResultCollectionError):
                AnalysisResultCollection.from_records([documents[0], duplicate])

    def test_threshold_and_cost_classification_records_are_schema_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            document = _analysis_documents(Path(tmp))[0]

        eligible = classify_cost_eligibility(document, threshold=0.6)
        ineligible = classify_cost_eligibility(document, threshold=0.4)
        metric_rule = ThresholdRule(
            classification_id="structural-cost-pass",
            name="structural_cost_threshold",
            field="metric.structural_cost",
            threshold=0.6,
            operator="le",
            pass_label="pass",
            fail_label="fail",
        )
        metric_classification = classify_threshold(document, metric_rule)

        self.assertEqual(eligible.label, "eligible")
        self.assertEqual(ineligible.label, "ineligible")
        self.assertEqual(metric_classification.label, "pass")
        enriched = copy.deepcopy(document)
        enriched["classifications"] = [eligible.to_dict(), metric_classification.to_dict()]
        validate_analysis_result_document(enriched)
        collection = AnalysisResultCollection.from_records([enriched])
        self.assertEqual(len(collection.filter_by_classification(label="eligible")), 1)
        self.assertEqual(len(collection.filter_by_classification(label="missing")), 0)

    def test_invalid_classification_records_rejected_state(self) -> None:
        invalid = classify_invalid(
            candidate_id="candidate-a",
            reason="schema validation failed",
        )

        self.assertEqual(invalid.name, "validity")
        self.assertEqual(invalid.label, "rejected")
        self.assertEqual(invalid.metadata["reason"], "schema validation failed")

    def test_weighted_structural_cost_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            first = _analysis_documents(Path(tmp_a))[0]
            second = _analysis_documents(Path(tmp_b))[0]

        self.assertEqual(first["cost"]["metadata"]["component_weights"]["parameter_count"], 2.0)
        self.assertEqual(first["cost"]["structural_cost"], second["cost"]["structural_cost"])


if __name__ == "__main__":
    unittest.main()

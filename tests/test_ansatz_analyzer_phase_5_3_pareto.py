"""Phase 5.3 tests for pure Pareto classification."""

from __future__ import annotations

import unittest

from verfeinert.ansatz_analyzer import AnalysisResultCollection, validate_analysis_result_document
from verfeinert.ansatz_analyzer.pareto import (
    ParetoConfig,
    compute_pareto_classifications,
    dominates,
    with_pareto_classifications,
)


def _result(
    candidate_id: str,
    *,
    expressibility: float,
    trainability: float,
    cost: float,
) -> dict:
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id},
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": expressibility,
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": trainability,
            },
        ],
        "cost": {
            "structural_cost": cost,
            "metadata": {"cost_model": "test"},
        },
        "classifications": [],
        "provenance": {
            "created_at": "2026-08-06T00:00:00Z",
            "analyzer": "phase-5-3-test",
            "execution": {
                "qnodes_executed": False,
                "expensive_metrics_executed": False,
            },
        },
    }


class AnalyzerPhase53ParetoTests(unittest.TestCase):
    def test_dominance_relation_uses_configured_objective_directions(self) -> None:
        self.assertTrue(
            dominates(
                {"expressibility": 2.0, "trainability": 0.9},
                {"expressibility": 1.0, "trainability": 0.5},
            ),
        )
        self.assertFalse(
            dominates(
                {"expressibility": 2.0, "trainability": 0.4},
                {"expressibility": 1.0, "trainability": 0.5},
            ),
        )

    def test_synthetic_collection_produces_expected_frontier(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", expressibility=1.0, trainability=0.5, cost=0.2),
                _result("candidate-b", expressibility=2.0, trainability=0.6, cost=0.5),
                _result("candidate-c", expressibility=1.5, trainability=0.7, cost=0.8),
            ],
        )

        result = compute_pareto_classifications(collection)

        self.assertEqual(result.frontier_candidate_ids, ("candidate-b", "candidate-c"))
        self.assertEqual(result.dominated_candidate_ids, ("candidate-a",))
        candidate_a = result.classifications_by_candidate_id["candidate-a"][0]
        candidate_b = result.classifications_by_candidate_id["candidate-b"][0]
        self.assertEqual(candidate_a.label, "dominated")
        self.assertEqual(candidate_b.label, "frontier")
        self.assertIn("candidate-c", candidate_a.metadata["dominated_by"])

    def test_cost_threshold_frontier_treats_cost_as_external_filter(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", expressibility=1.0, trainability=0.5, cost=0.2),
                _result("candidate-b", expressibility=2.0, trainability=0.6, cost=0.5),
                _result("candidate-c", expressibility=1.5, trainability=0.7, cost=0.8),
            ],
        )
        config = ParetoConfig(cost_thresholds=(0.6,))

        result = compute_pareto_classifications(collection, config=config)

        self.assertEqual(result.frontiers_by_cost_threshold[0.6], ("candidate-b",))
        labels = {
            item.candidate_id: result.classifications_by_candidate_id[item.candidate_id][1].label
            for item in result.candidates
        }
        self.assertEqual(labels["candidate-b"], "frontier")
        self.assertEqual(labels["candidate-a"], "eligible_dominated")
        self.assertEqual(labels["candidate-c"], "ineligible")
        self.assertFalse(result.config.to_dict()["cost_is_pareto_objective"])

    def test_reference_collection_comparison_is_recorded(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", expressibility=1.0, trainability=0.5, cost=0.2),
                _result("candidate-c", expressibility=1.5, trainability=0.7, cost=0.8),
            ],
        )
        reference = AnalysisResultCollection.from_records(
            [_result("reference-a", expressibility=1.2, trainability=0.6, cost=0.1)],
        )

        result = compute_pareto_classifications(
            collection,
            reference_collection=reference,
        )
        candidate_a = result.classifications_by_candidate_id["candidate-a"][0]
        candidate_c = result.classifications_by_candidate_id["candidate-c"][0]

        self.assertTrue(candidate_a.metadata["dominated_by_reference"])
        self.assertTrue(candidate_c.metadata["dominates_reference"])

    def test_pareto_classifications_can_be_appended_to_analysis_results(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [
                _result("candidate-a", expressibility=1.0, trainability=0.5, cost=0.2),
                _result("candidate-b", expressibility=2.0, trainability=0.4, cost=0.5),
            ],
        )
        pareto = compute_pareto_classifications(collection)
        enriched = with_pareto_classifications(collection, pareto)

        for document in enriched:
            payload = validate_analysis_result_document(document)
            self.assertEqual(payload["classifications"][0]["name"], "pareto_front")

    def test_missing_metric_becomes_unrankable_without_breaking_collection(self) -> None:
        broken = _result("candidate-missing", expressibility=1.0, trainability=0.5, cost=0.2)
        broken["metrics"] = broken["metrics"][:1]
        collection = AnalysisResultCollection.from_records([broken])

        result = compute_pareto_classifications(collection)

        self.assertEqual(result.frontier_candidate_ids, ())
        self.assertEqual(
            result.classifications_by_candidate_id["candidate-missing"][0].label,
            "unrankable",
        )
        self.assertIn("missing computed objective", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()

"""Phase 5.4 tests for ranking and derived analytical exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer.ranking import RankingConfig, rank_analysis_results
from verfeinert.ansatz_analyzer.tables import write_ranking_csv, write_ranking_json
from verfeinert.core.io import read_json


def _result(
    candidate_id: str,
    *,
    expressibility: float | None,
    trainability: float | None,
    cost: float,
) -> dict:
    metrics = []
    if expressibility is not None:
        metrics.append(
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": expressibility,
            },
        )
    if trainability is not None:
        metrics.append(
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": trainability,
            },
        )
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id},
        "metrics": metrics,
        "cost": {"structural_cost": cost},
        "classifications": [],
        "provenance": {
            "created_at": "2026-08-06T00:00:00Z",
            "analyzer": "phase-5-4-test",
        },
    }


def _collection() -> AnalysisResultCollection:
    return AnalysisResultCollection.from_records(
        [
            _result("candidate-a", expressibility=1.0, trainability=0.5, cost=0.2),
            _result("candidate-b", expressibility=2.0, trainability=0.6, cost=0.5),
            _result("candidate-c", expressibility=1.5, trainability=0.7, cost=0.8),
        ],
    )


class AnalyzerPhase54RankingTests(unittest.TestCase):
    def test_default_product_ranking_is_deterministic(self) -> None:
        result = rank_analysis_results(_collection())

        self.assertEqual(result.ranked_candidate_ids, ("candidate-b", "candidate-c", "candidate-a"))
        rows = result.to_rows()
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["analysis_result_id"], "analysis-candidate-b")
        self.assertEqual(result.to_dict()["source_analysis_result_ids"][0], "analysis-candidate-a")

    def test_weight_configuration_changes_traceable_score(self) -> None:
        result = rank_analysis_results(
            _collection(),
            config=RankingConfig(
                score_components={"expressibility": 1.0, "trainability": 3.0},
            ),
        )

        self.assertEqual(result.ranked_candidate_ids[0], "candidate-c")
        top = result.ranked_candidates[0]
        self.assertEqual(top.component_weights["trainability"], 3.0)
        self.assertAlmostEqual(top.score, 1.5 * (0.7 ** 3))

    def test_cost_threshold_filters_without_becoming_score_component(self) -> None:
        result = rank_analysis_results(
            _collection(),
            config=RankingConfig(cost_threshold=0.6),
        )

        self.assertEqual(result.ranked_candidate_ids, ("candidate-b", "candidate-a"))
        self.assertNotIn("candidate-c", result.ranked_candidate_ids)
        self.assertEqual(result.config.to_dict()["cost_field"], "structural_cost")

    def test_missing_score_component_can_be_recorded_as_unrankable(self) -> None:
        collection = AnalysisResultCollection.from_records(
            [_result("candidate-missing", expressibility=1.0, trainability=None, cost=0.1)],
        )

        result = rank_analysis_results(
            collection,
            config=RankingConfig(include_unrankable=True),
        )

        self.assertEqual(result.ranked_candidates[0].status, "unrankable")
        self.assertIn("missing component", result.ranked_candidates[0].reason)

    def test_ranking_json_and_csv_exports_are_guarded_and_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            output_root = tmp_path / "outputs"
            result = rank_analysis_results(_collection())

            json_artifact = write_ranking_json(
                result,
                output_root=output_root,
                run_id="phase54-run",
                input_roots=(input_root,),
            )
            csv_artifact = write_ranking_csv(
                result,
                output_root=output_root,
                run_id="phase54-run",
                input_roots=(input_root,),
            )

            self.assertTrue(json_artifact.path.is_file())
            self.assertTrue(csv_artifact.path.is_file())
            self.assertEqual(json_artifact.path.parent, output_root / "phase54-run" / "derived")
            self.assertEqual(len(json_artifact.sha256), 64)
            payload = read_json(json_artifact.path)
            self.assertEqual(payload["transform"], "ranking")
            self.assertEqual(payload["source_analysis_result_ids"], list(_collection().analysis_result_ids))
            with csv_artifact.path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["candidate_id"], "candidate-b")
            self.assertEqual(rows[0]["transform_version"], "1")

    def test_ranking_payload_is_json_serializable(self) -> None:
        payload = rank_analysis_results(_collection()).to_dict()

        json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["schema_version"], "verfeinert.ranking_result.v1")


if __name__ == "__main__":
    unittest.main()

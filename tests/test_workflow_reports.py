"""Workflow deterministic report tests."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.core.hashing import stable_hash
from verfeinert.workflow import (
    WORKFLOW_REPORT_SCHEMA_VERSION,
    WorkflowConfig,
    WorkflowRunner,
)


CREATED_AT = "2026-08-21T00:00:00Z"


def _analysis_result(
    candidate_id: str,
    *,
    expressibility: float | None = 1.0,
    trainability: float | None = 1.0,
    cost: float = 0.1,
) -> dict:
    metrics = [
        {
            "metric_id": f"metric-structural-cost-{candidate_id}",
            "name": "structural_cost",
            "status": "computed",
            "value": cost,
        },
    ]
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
        "candidate_ref": {"candidate_id": candidate_id, "structural_hash": "7" * 64},
        "metrics": metrics,
        "cost": {"structural_cost": cost},
        "classifications": [],
        "metadata": {"candidate_semantics": {"lineage": {"generation": 0}}},
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "workflow-report-test",
            "execution": {"qnodes_executed": False},
        },
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _workflow_mapping(
    output_root: Path,
    *,
    run_id: str,
    scientific_execution=(),
    postprocessing=("report",),
    artifacts: dict | None = None,
) -> dict:
    return {
        "run": {"run_id": run_id, "created_at": CREATED_AT, "random_seed": 41},
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": list(scientific_execution),
            "postprocessing": list(postprocessing),
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "report",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost", "expressibility", "trainability"],
            "structural_cost": {
                "reference_bounds": {
                    "parameter_count": {"min": 0, "max": 8},
                    "depth": {"min": 0, "max": 20},
                    "two_qubit_operation_count": {"min": 0, "max": 6},
                },
            },
            "ranking": {
                "score_components": {"expressibility": 1.0, "trainability": 1.0},
                "combination": "product",
                "ascending": False,
            },
            "pareto": {
                "objectives": [
                    {"metric_name": "trainability", "direction": "maximize"},
                    {"metric_name": "expressibility", "direction": "maximize"},
                ],
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "report-selection",
            "metric_name": "structural_cost",
            "keep": 1,
            "direction": "minimize",
            "max_generations": 1,
        },
        "artifacts": artifacts or {},
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class WorkflowReportTests(unittest.TestCase):
    def test_report_summarizes_analysis_ranking_and_pareto_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = _write(root / "inputs" / "alpha.json", _analysis_result("alpha", expressibility=2.0, trainability=0.6, cost=0.2))
            beta = _write(root / "inputs" / "beta.json", _analysis_result("beta", expressibility=1.5, trainability=0.9, cost=0.3))
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="report-derived",
                        postprocessing=("ranking", "pareto", "report"),
                        artifacts={"analysis_results": [str(alpha), str(beta)]},
                    ),
                ),
            ).run()

            self.assertTrue(result.report_json_path.is_file())
            self.assertTrue(result.report_markdown_path.is_file())
            report = _read_json(result.report_json_path)

            self.assertEqual(report["schema_version"], WORKFLOW_REPORT_SCHEMA_VERSION)
            self.assertEqual(report["summary"]["completed_operations"], ["ranking", "pareto", "report"])
            self.assertEqual(report["summary"]["candidate_count"], 2)
            self.assertEqual(report["summary"]["analysis_result_count"], 2)
            self.assertEqual(report["config"]["hash"], stable_hash(result.provenance["config"]))
            self.assertEqual(report["ranking"]["ranked_count"], 2)
            self.assertEqual(report["ranking"]["top_ranked_candidate_id"], "beta")
            self.assertEqual(report["pareto"]["frontier_count"], 2)
            self.assertEqual(report["analysis"]["rows"][0]["candidate_id"], "alpha")
            self.assertEqual(report["analysis"]["rows"][0]["metrics"]["expressibility"]["status"], "computed")
            markdown = result.report_markdown_path.read_text(encoding="utf-8")
            self.assertIn("# Workflow Report: report-derived", markdown)
            self.assertIn("- Top ranked candidate: beta", markdown)

    def test_report_preserves_missing_metrics_without_fabricating_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write(
                root / "inputs" / "structural.json",
                _analysis_result("structural", expressibility=None, trainability=None),
            )
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="report-missing",
                        artifacts={"analysis_results": [str(source)]},
                    ),
                ),
            ).run()

            row = _read_json(result.report_json_path)["analysis"]["rows"][0]
            self.assertEqual(row["candidate_id"], "structural")
            self.assertEqual(row["missing_configured_metrics"], ["expressibility", "trainability"])
            self.assertNotIn("expressibility", row["metrics"])
            self.assertNotIn("trainability", row["metrics"])

    def test_evolutionary_report_records_final_stopping_reason(self) -> None:
        with TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(
                Path(tmp) / "out",
                run_id="report-evolution",
                scientific_execution=("generate", "analyze", "evolve"),
                postprocessing=("report",),
            )
            mapping["workflow"]["campaign_type"] = "evolutionary"
            mapping["analyzer"]["selected_metrics"] = ["structural_cost"]

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()
            report = _read_json(result.report_json_path)

            self.assertEqual(result.executed_operations, ("generate", "analyze", "evolve", "report"))
            self.assertEqual(report["evolution"]["generation_count"], 1)
            self.assertEqual(report["evolution"]["latest_generation"], 0)
            self.assertEqual(report["evolution"]["final_stopping_reason"], "max_generations_reached")
            self.assertEqual(report["summary"]["final_stopping_reason"], "max_generations_reached")

    def test_report_is_deterministic_for_repeat_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write(root / "inputs" / "alpha.json", _analysis_result("alpha"))
            config = WorkflowConfig.from_mapping(
                _workflow_mapping(
                    root / "out",
                    run_id="report-repeat",
                    artifacts={"analysis_results": [str(source)]},
                ),
            )

            first = WorkflowRunner(config).run()
            first_report = _read_json(first.report_json_path)
            second = WorkflowRunner(config).run()
            second_report = _read_json(second.report_json_path)

            self.assertEqual(first_report, second_report)


if __name__ == "__main__":
    unittest.main()

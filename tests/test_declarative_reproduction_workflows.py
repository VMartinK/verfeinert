"""Declarative full-lite reproduction workflow tests."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_analyzer import validate_analysis_result_document
from verfeinert.ansatz_evolver import validate_evolution_run_document
from verfeinert.cli import main as cli_main
from verfeinert.workflow import WorkflowConfig
from verfeinert.core import read_yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CX01_CONFIG = PROJECT_ROOT / "examples" / "CX01_reproduction" / "config" / "cx01_full_lite_workflow.yaml"
MIXT5G_CONFIG = PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "config" / "mixt5g_full_lite_workflow.yaml"


def _run_cli_config(config_path: Path, output_root: Path) -> dict:
    stdout = io.StringIO()
    stderr = io.StringIO()
    os.environ["MPLCONFIGDIR"] = str(output_root / "matplotlib")
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli_main(["run", str(config_path), "--output-root", str(output_root)])
    if exit_code != 0:
        raise AssertionError(f"CLI failed with {exit_code}: {stderr.getvalue()}")
    return json.loads(stdout.getvalue())


def _analysis_documents(run_root: Path) -> list[dict]:
    documents = []
    for path in sorted((run_root / "analysis").glob("**/*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") == "verfeinert.analysis_result.v1":
            documents.append(validate_analysis_result_document(document))
    return documents


def _assert_materialized_metrics_computed(testcase: unittest.TestCase, documents: list[dict]) -> None:
    testcase.assertTrue(documents)
    for document in documents:
        metrics = {metric["name"]: metric for metric in document.get("metrics", ())}
        for name in ("expressibility", "trainability"):
            testcase.assertIn(name, metrics)
            testcase.assertEqual(metrics[name]["status"], "computed")
            testcase.assertNotIn("no state callable provided", json.dumps(metrics[name]).lower())
            testcase.assertTrue(metrics[name]["metadata"]["qnodes_executed"])


def _assert_run_artifacts(testcase: unittest.TestCase, payload: dict) -> None:
    testcase.assertTrue(Path(payload["manifest_path"]).is_file())
    testcase.assertTrue(Path(payload["traceability_csv_path"]).is_file())
    testcase.assertTrue(Path(payload["checkpoint_path"]).is_file())
    testcase.assertTrue(Path(payload["event_log_path"]).is_file())
    testcase.assertTrue(Path(payload["report_json_path"]).is_file())
    testcase.assertTrue(Path(payload["report_markdown_path"]).is_file())
    testcase.assertTrue(payload["visualization_paths"])
    for path in payload["visualization_paths"]:
        testcase.assertTrue(Path(path).is_file())


class DeclarativeReproductionWorkflowTests(unittest.TestCase):
    def test_cx01_full_lite_runs_from_config_without_evolution(self) -> None:
        config = WorkflowConfig.from_mapping(read_yaml(CX01_CONFIG))
        self.assertEqual(config.campaign_type, "individual")
        self.assertEqual(config.scientific_execution, ("generate", "analyze"))
        self.assertNotIn("evolve", config.scientific_execution)

        with TemporaryDirectory() as tmp:
            payload = _run_cli_config(CX01_CONFIG, Path(tmp) / "outputs")
            run_root = Path(payload["run_root"])

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["evolution_run_path"], None)
            self.assertEqual(
                payload["executed_operations"],
                ["generate", "analyze", "ranking", "pareto", "export_csv", "visualization", "report"],
            )
            self.assertEqual(payload["candidate_ids"], ["cx01lite-a02-l1", "cx01lite-a09-l1"])
            _assert_materialized_metrics_computed(self, _analysis_documents(run_root))
            _assert_run_artifacts(self, payload)
            self.assertEqual(len(payload["visualization_paths"]), 3)

    def test_mixt5g_full_lite_runs_multi_generation_from_config(self) -> None:
        config = WorkflowConfig.from_mapping(read_yaml(MIXT5G_CONFIG))
        self.assertEqual(config.campaign_type, "evolutionary")
        self.assertEqual(config.scientific_execution, ("generate", "analyze", "evolve"))
        self.assertTrue(config.evolver.mutation_policy)

        with TemporaryDirectory() as tmp:
            payload = _run_cli_config(MIXT5G_CONFIG, Path(tmp) / "outputs")
            run_root = Path(payload["run_root"])

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(
                payload["executed_operations"],
                ["generate", "analyze", "evolve", "ranking", "pareto", "export_csv", "visualization", "report"],
            )
            _assert_materialized_metrics_computed(self, _analysis_documents(run_root))
            _assert_run_artifacts(self, payload)
            evolution = validate_evolution_run_document(
                json.loads(Path(payload["evolution_run_path"]).read_text(encoding="utf-8")),
            )
            self.assertEqual([item["generation_index"] for item in evolution["generations"]], [0, 1, 2])
            self.assertIn("_g001-crx_insert", evolution["generations"][1]["candidate_refs"][0]["candidate_id"])
            self.assertIn("_g002-crz_insert", evolution["generations"][2]["candidate_refs"][0]["candidate_id"])
            self.assertGreaterEqual(len(payload["visualization_paths"]), 2)


if __name__ == "__main__":
    unittest.main()

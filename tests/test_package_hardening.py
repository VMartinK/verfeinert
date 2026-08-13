"""Phase 8.1 package-hardening tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verfeinert.core import load_schema, read_schema_text, schema_filename, schema_names


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_SCHEMAS = PROJECT_ROOT / "schemas"
FRAMEWORK_ROOT = PROJECT_ROOT / "verfeinert"


class PackageHardeningTests(unittest.TestCase):
    def test_packaged_schema_resources_match_root_schemas(self) -> None:
        for name in schema_names():
            with self.subTest(schema=name):
                root_text = (ROOT_SCHEMAS / schema_filename(name)).read_text(encoding="utf-8")
                self.assertEqual(read_schema_text(name), root_text)
                self.assertEqual(load_schema(name), json.loads(root_text))

    def test_public_imports_and_schema_loading_work_from_external_cwd(self) -> None:
        code = """
import json
from verfeinert.core import load_schema, schema_names
from verfeinert.ansatz_generator import build_sanz19_candidate_record, export_candidate_json
from verfeinert.ansatz_analyzer import validate_candidate_document
from verfeinert.ansatz_evolver import CandidateRef
from verfeinert.workflow import WorkflowConfig

record = build_sanz19_candidate_record("A02", 1, n_qubits=2)
candidate = export_candidate_json(
    record,
    config=None,
    candidate_id="external-style-candidate",
)
validate_candidate_document(candidate)
CandidateRef(candidate_id=candidate["candidate_id"])
WorkflowConfig.from_mapping({
    "run_id": "external-style-import",
    "output_root": "outputs",
})
print(json.dumps({
    "schema_count": len(schema_names()),
    "candidate_schema": load_schema("candidate")["$id"],
    "candidate_id": candidate["candidate_id"],
}, sort_keys=True))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-verfeinert")
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=tmp,
                env=env,
                check=True,
                text=True,
                capture_output=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema_count"], 6)
        self.assertEqual(payload["candidate_id"], "external-style-candidate")
        self.assertTrue(payload["candidate_schema"].endswith("/candidate.schema.json"))

    def test_nonvisual_public_paths_work_when_matplotlib_unavailable(self) -> None:
        code = r"""
import contextlib
import importlib.abc
import io
import json
import tempfile
import textwrap
from pathlib import Path


class BlockMatplotlib(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "matplotlib" or fullname.startswith("matplotlib."):
            raise ModuleNotFoundError(f"blocked optional dependency: {fullname}")
        return None


def analysis_result(candidate_id, *, expressibility, trainability, cost, source):
    trainability_config = {
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
    cost_metadata = {
        "cost_model": "reference_normalized_structural_cost",
        "definition": "weighted average of reference-normalized structural features",
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
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id},
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": {"expressibility": expressibility, "dkl": 10 ** -expressibility},
                "metadata": {
                    "configuration": {
                        "n_qubits": 4,
                        "n_pairs": 3,
                        "n_bins": 4,
                        "parameter_low": 0.0,
                        "parameter_high": 6.283185307179586,
                        "rng_seed": 42,
                        "rng_policy": "per_circuit",
                        "dkl_floor": 1e-16,
                        "histogram_epsilon": 1e-12,
                    },
                },
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
                    "configuration": trainability_config,
                    "hamiltonian": "local_x",
                    "hamiltonian_kind": "sum_x",
                    "hamiltonian_definition": "H = sum_i X_i",
                    "hamiltonian_scale": 1.0,
                },
            },
        ],
        "cost": {"structural_cost": cost, "metadata": cost_metadata},
        "classifications": [],
        "provenance": {
            "created_at": "2026-08-13T00:00:00Z",
            "analyzer": "nonvisual-boundary-test",
            "execution": {"qnodes_executed": False},
        },
        "metadata": {
            "candidate_semantics": {
                "lineage": {"generation": 0, "root_candidate_id": candidate_id},
                "source_context": {"workflow_run_id": source},
            },
        },
    }


import sys
sys.meta_path.insert(0, BlockMatplotlib())

import verfeinert
import verfeinert.workflow
from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_analyzer import compute_pareto_classifications
from verfeinert.ansatz_analyzer.comparison import ComparisonConfig, ComparisonSource, compare_analysis_collections
from verfeinert.ansatz_analyzer.tables import write_comparison_csv
from verfeinert.ansatz_analyzer.visualization import VisualizationDependencyError, plot_pareto_front
from verfeinert.cli import main as cli_main

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    config_path = root / "workflow.yaml"
    config_path.write_text(
        textwrap.dedent(
            f'''
            run:
              run_id: no-matplotlib-cli
              created_at: "2026-08-13T00:00:00Z"
            paths:
              output_root: {root / "outputs"}
            workflow:
              campaign_type: individual
              scientific_execution: [generate, analyze]
              postprocessing: [ranking, export_csv]
            generation:
              family: sanz19
              template_ids: [A02]
              layers: [1]
              n_qubits: 4
              candidate_id_prefix: nompl
            analyzer:
              selected_metrics: [structural_cost]
              structural_cost:
                reference_bounds:
                  parameter_count: {{min: 0, max: 32}}
                  depth: {{min: 0, max: 64}}
                  two_qubit_operation_count: {{min: 0, max: 16}}
              ranking:
                score_components: {{cost.structural_cost: 1.0}}
                combination: weighted_sum
                ascending: true
            '''
        ),
        encoding="utf-8",
    )
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = cli_main(["run", str(config_path)])
    workflow_payload = json.loads(stdout.getvalue())

    comparison_collection = AnalysisResultCollection.from_records([
        analysis_result("candidate-a", expressibility=2.0, trainability=1.0, cost=0.2, source="run-a"),
        analysis_result("candidate-b", expressibility=3.0, trainability=1.5, cost=0.3, source="run-b"),
    ])
    pareto = compute_pareto_classifications(comparison_collection)
    source_a = ComparisonSource(
        "run-a",
        AnalysisResultCollection.from_records([comparison_collection.documents[0]]),
    )
    source_b = ComparisonSource(
        "run-b",
        AnalysisResultCollection.from_records([comparison_collection.documents[1]]),
    )
    comparison = compare_analysis_collections((source_a, source_b), config=ComparisonConfig())
    comparison_csv = write_comparison_csv(comparison, output_root=root / "comparison", run_id="comparison")
    comparison_csv_exists = comparison_csv.path.is_file()
    try:
        plot_pareto_front(source_a.collection)
    except VisualizationDependencyError as exc:
        visualization_error = str(exc)
    else:
        raise AssertionError("plotting should require the visualization extra")

print(json.dumps({
    "version": verfeinert.__version__,
    "exit_code": exit_code,
    "executed_operations": workflow_payload["executed_operations"],
    "ranking_csv": workflow_payload["ranking_csv_path"] is not None,
    "pareto_frontier_count": len(pareto.frontier_candidate_ids),
    "comparison_csv": comparison_csv_exists,
    "visualization_error": visualization_error,
}, sort_keys=True))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-verfeinert")
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=tmp,
                env=env,
                check=True,
                text=True,
                capture_output=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["executed_operations"], ["generate", "analyze", "ranking", "export_csv"])
        self.assertTrue(payload["ranking_csv"])
        self.assertGreaterEqual(payload["pareto_frontier_count"], 1)
        self.assertTrue(payload["comparison_csv"])
        self.assertIn("Install the 'visualization' extra", payload["visualization_error"])

    def test_framework_schema_validation_uses_package_resources(self) -> None:
        forbidden_tokens = (
            'PROJECT_ROOT = Path(__file__).resolve().parents[2]',
            'SCHEMAS_ROOT = PROJECT_ROOT / "schemas"',
            'parents[3] / "schemas"',
        )
        checked = [
            FRAMEWORK_ROOT / "ansatz_generator" / "exporters" / "candidate_json.py",
            FRAMEWORK_ROOT / "ansatz_analyzer" / "validation.py",
            FRAMEWORK_ROOT / "ansatz_evolver" / "validation.py",
        ]
        violations = []
        for path in checked:
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token!r}")
        self.assertEqual(violations, [])

    def test_reproduction_scripts_do_not_bootstrap_package_root(self) -> None:
        scripts = [
            PROJECT_ROOT / "examples" / "CX01_reproduction" / "scripts" / "run_cx01_reproduction.py",
            PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "scripts" / "run_mixt5g_reproduction.py",
        ]
        violations = []
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            if "sys.path.insert" in text or "PROJECT_ROOT = Path(__file__).resolve().parents[3]" in text:
                violations.append(str(script.relative_to(PROJECT_ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

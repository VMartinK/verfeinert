"""Phase 10.3 public reproducibility surface tests."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tomllib
from tempfile import TemporaryDirectory
import textwrap
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import AnalysisPipeline, validate_analysis_result_document
from verfeinert.ansatz_evolver import (
    MutationPolicy,
    MutationRecipe,
    validate_evolution_run_document,
)
from verfeinert.ansatz_generator import (
    InsertGateMutationFactory,
    build_sanz19_candidate_records,
)
from verfeinert.cli import main as cli_main
from verfeinert.workflow import WorkflowConfig, WorkflowRunner, run_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIXT_SCRIPT_PATH = PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "scripts" / "run_mixt5g_reproduction.py"


def _load_mixt_script():
    spec = importlib.util.spec_from_file_location("mixt5g_reproduction_script_phase103", MIXT_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load MIXT-5G reproduction script.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bounds() -> dict:
    return {
        "parameter_count": {"min": 0, "max": 32},
        "depth": {"min": 0, "max": 64},
        "two_qubit_operation_count": {"min": 0, "max": 16},
    }


def _third_campaign_mapping(output_root: Path) -> dict:
    return {
        "run": {
            "run_id": "third-portability",
            "created_at": "2026-08-06T00:00:00Z",
            "random_seed": 31,
        },
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "evolutionary",
            "scientific_execution": ["generate", "analyze", "evolve"],
            "postprocessing": ["ranking"],
        },
        "generation": {
            "family": "provided",
            "candidate_id_prefix": "thirdlab",
            "source_label": "third_campaign_fixture",
            "n_qubits": 4,
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {"reference_bounds": _bounds()},
            "ranking": {
                "score_components": {"cost.structural_cost": 1},
                "combination": "weighted_sum",
                "ascending": True,
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "third-fixture-selection",
            "metric_name": "structural_cost",
            "keep": 1,
            "direction": "minimize",
            "max_generations": 2,
            "mutation_policy": {
                "policy_id": "third-fixture-insert",
                "variants_per_parent": 1,
                "recipes": [
                    {
                        "recipe_id": "cz_insert",
                        "mutation_type": "insert",
                        "parameters": {
                            "gate": "cz",
                            "edge": [2, 0],
                            "insertion_strategy": "append",
                            "candidate_id_template": "{root_candidate_id}_g{generation:03d}-{recipe_id}-v{variant_ordinal:03d}",
                        },
                    },
                ],
            },
        },
    }


class PublicReproducibilityPhase103Tests(unittest.TestCase):
    def test_documented_public_imports_cover_normal_workflow_execution(self) -> None:
        self.assertIsNotNone(WorkflowConfig)
        self.assertIsNotNone(WorkflowRunner)
        self.assertIsNotNone(run_workflow)
        self.assertIsNotNone(InsertGateMutationFactory)
        self.assertIsNotNone(MutationPolicy)
        self.assertIsNotNone(MutationRecipe)

    def test_third_campaign_runs_without_name_specific_core_changes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            records = build_sanz19_candidate_records(("A02",), (1,), n_qubits=4)
            result = run_workflow(
                WorkflowConfig.from_mapping(_third_campaign_mapping(Path(temp_dir) / "outputs")),
                candidate_records=records,
                candidate_factory=InsertGateMutationFactory(),
            )

            self.assertEqual(result.executed_operations, ("generate", "analyze", "evolve", "ranking"))
            self.assertTrue(Path(result.evolution_run_path).is_file())
            evolution = validate_evolution_run_document(json.loads(Path(result.evolution_run_path).read_text(encoding="utf-8")))
            self.assertEqual([generation["generation_index"] for generation in evolution["generations"]], [0, 1])
            self.assertEqual(
                evolution["generations"][1]["candidate_refs"][0]["candidate_id"],
                "thirdlab-a02-l1_g001-cz_insert-v001",
            )
            self.assertEqual(evolution["generations"][1]["parent_refs"][0]["candidate_id"], "thirdlab-a02-l1")

        package_text = "\n".join(path.read_text(encoding="utf-8") for path in (PROJECT_ROOT / "verfeinert").rglob("*.py"))
        self.assertNotIn("third-portability", package_text)

    def test_mixt5g_resume_does_not_recompute_historical_generation_or_analysis(self) -> None:
        module = _load_mixt_script()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            initial = module.run_reproduction(
                output_root_override=root / "initial",
                profile="smoke",
            )
            calls: list[Path] = []
            original_run_and_write = AnalysisPipeline.run_and_write

            def recording_run_and_write(pipeline, source, *args, **kwargs):
                calls.append(Path(source))
                return original_run_and_write(pipeline, source, *args, **kwargs)

            with mock.patch.object(module, "build_initial_records", side_effect=AssertionError("G0 generation must not repeat")):
                with mock.patch.object(AnalysisPipeline, "run_and_write", new=recording_run_and_write):
                    resumed = module.resume_reproduction(
                        initial.evolution_run_path,
                        output_root_override=root / "resumed",
                        profile="smoke",
                        total_generations=4,
                    )

            evolution = validate_evolution_run_document(json.loads(Path(resumed.evolution_run_path).read_text(encoding="utf-8")))
            self.assertEqual([generation["generation_index"] for generation in evolution["generations"]], [0, 1, 2, 3])
            self.assertEqual(len(calls), 1)
            self.assertIn("g003-candidate-package", str(calls[0]))
            self.assertEqual(evolution["metadata"]["workflow"]["relationship"]["type"], "continuation")

    def test_cli_run_invokes_public_workflow_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "workflow.yaml"
            config_path.write_text(
                textwrap.dedent(
                    f"""
                    run:
                      run_id: cli-smoke
                      created_at: "2026-08-06T00:00:00Z"
                    paths:
                      output_root: {root / "unused"}
                    workflow:
                      campaign_type: individual
                      scientific_execution: [generate, analyze]
                      postprocessing: []
                    generation:
                      family: sanz19
                      template_ids: [A02]
                      layers: [1]
                      n_qubits: 4
                      candidate_id_prefix: cli
                    analyzer:
                      selected_metrics: [structural_cost]
                      structural_cost:
                        reference_bounds:
                          parameter_count: {{min: 0, max: 32}}
                          depth: {{min: 0, max: 64}}
                          two_qubit_operation_count: {{min: 0, max: 16}}
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_main(["run", str(config_path), "--output-root", str(root / "outputs")])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["executed_operations"], ["generate", "analyze"])
            self.assertEqual(payload["candidate_ids"], ["cli-a02-l1"])
            for path in payload["analysis_result_paths"]:
                validate_analysis_result_document(json.loads(Path(path).read_text(encoding="utf-8")))

    def test_cli_help_and_packaging_entry_point_are_thin(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(stdout):
                cli_main(["run", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("workflow YAML configuration", stdout.getvalue())
        pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["scripts"]["verfeinert"], "verfeinert.cli:main")

    def test_cli_missing_config_fails_without_traceback(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = cli_main(["run", "missing-workflow.yaml"])

        self.assertEqual(exit_code, 1)
        error = stderr.getvalue()
        self.assertIn("workflow config file not found", error)
        self.assertNotIn("Traceback", error)

    def test_cli_malformed_yaml_fails_without_traceback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "workflow.yaml"
            config_path.write_text("run: [\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = cli_main(["run", str(config_path)])

        self.assertEqual(exit_code, 1)
        error = stderr.getvalue()
        self.assertIn("unable to parse workflow config", error)
        self.assertNotIn("Traceback", error)

    def test_cli_invalid_config_shape_and_semantics_fail_without_traceback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases = {
                "shape": "[]\n",
                "semantics": textwrap.dedent(
                    f"""
                    run:
                      run_id: invalid-cli
                    paths:
                      output_root: {root / "outputs"}
                    workflow:
                      campaign_type: individual
                      scientific_execution: [evolve]
                      postprocessing: []
                    """
                ),
            }
            for name, content in cases.items():
                with self.subTest(name=name):
                    config_path = root / f"{name}-workflow.yaml"
                    config_path.write_text(content, encoding="utf-8")
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        exit_code = cli_main(["run", str(config_path)])

                    self.assertEqual(exit_code, 1)
                    error = stderr.getvalue()
                    self.assertIn("verfeinert: error:", error)
                    self.assertNotIn("Traceback", error)


if __name__ == "__main__":
    unittest.main()

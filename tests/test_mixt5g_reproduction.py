"""Integration tests for the MIXT-5G reproduction example."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_evolver import validate_candidate_document, validate_evolution_run_document
from verfeinert.ansatz_analyzer import validate_analysis_result_document
from verfeinert.core import read_yaml
from verfeinert.workflow import WorkflowConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "MIXT5G_reproduction"
SCRIPT_PATH = EXAMPLE_ROOT / "scripts" / "run_mixt5g_reproduction.py"
CONFIG_PATH = EXAMPLE_ROOT / "config" / "mixt5g_reproduction.yaml"


def _load_script():
    spec = importlib.util.spec_from_file_location("mixt5g_reproduction_script", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load MIXT-5G reproduction script.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MIXT5GReproductionTests(unittest.TestCase):
    def test_config_preserves_reference_scientific_meaning(self) -> None:
        config = read_yaml(CONFIG_PATH)
        campaign = config["mixt5g_campaign"]

        self.assertEqual(campaign["name"], "MIXT-5G")
        self.assertEqual(campaign["mutation_schedule"][0]["mutation_gate"], "crx")
        self.assertEqual(campaign["mutation_schedule"][1]["mutation_gate"], "crz")
        self.assertEqual(campaign["mutation_schedule"][2]["mutation_gate"], "cz")
        self.assertEqual(campaign["selection"]["thresholds"], [1.0, 0.2, 0.1])
        self.assertEqual(campaign["selection"]["fallback_policy"], "none")
        workflow = WorkflowConfig.from_mapping(config)
        self.assertEqual(workflow.campaign_type, "evolutionary")
        self.assertEqual(workflow.scientific_execution, ("generate", "analyze", "evolve"))
        self.assertEqual(workflow.postprocessing, ("ranking",))
        self.assertIn("mutation_policy", workflow.evolver.to_dict())

    def test_smoke_reproduction_uses_single_generic_workflow_evolution_run(self) -> None:
        module = _load_script()
        with TemporaryDirectory() as temp_dir:
            result = module.run_reproduction(
                CONFIG_PATH,
                output_root_override=Path(temp_dir) / "outputs",
                profile="smoke",
            )
            summary = result.to_dict()

            self.assertEqual(summary["generation_count"], 3)
            self.assertEqual(summary["initial_candidate_count"], 2)
            self.assertTrue(Path(summary["comparison_report_path"]).is_file())
            evolution = validate_evolution_run_document(
                json.loads(Path(summary["evolution_run_path"]).read_text(encoding="utf-8")),
            )
            self.assertEqual(len(evolution["generations"]), 3)
            self.assertEqual(summary["workflow_result"]["executed_operations"], ["generate", "analyze", "evolve", "ranking"])
            self.assertEqual(summary["workflow_result"]["provenance"]["execution"]["campaign_type"], "evolutionary")
            self.assertEqual(evolution["generations"][1]["parent_refs"][0]["candidate_id"], "mixt5g-a04-l1")
            self.assertIn("_g001-crx_insert", evolution["generations"][1]["candidate_refs"][0]["candidate_id"])
            self.assertIn("_g002-crz_insert", evolution["generations"][2]["candidate_refs"][0]["candidate_id"])
            self.assertEqual(
                evolution["generations"][1]["candidate_refs"][0]["structural_hash"],
                "18d1c2906fec6d241007fc9bafa6cf43ebc63e996649ee368b00c0ef64ebd337",
            )
            self.assertEqual(
                evolution["generations"][2]["candidate_refs"][0]["structural_hash"],
                "d59d794d7a46440c463a5d4f670e033156539197cf82642fb657d72a7234fc36",
            )

            for path in summary["workflow_result"]["candidate_paths"]:
                validate_candidate_document(json.loads(Path(path).read_text(encoding="utf-8")))
            for path in summary["workflow_result"]["analysis_result_paths"]:
                validate_analysis_result_document(json.loads(Path(path).read_text(encoding="utf-8")))

    def test_example_has_no_local_or_legacy_coupling(self) -> None:
        forbidden = (
            "/home/",
            "Thesis_Data_Processing",
            "python/ansatz_generator",
            "Verfeinert/src",
        )
        violations: list[str] = []
        for path in EXAMPLE_ROOT.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".md", ".json", ".ipynb"}:
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in text:
                        violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

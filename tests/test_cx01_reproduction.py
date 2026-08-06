"""Integration tests for the CX-01 reproduction example."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_evolver import (
    validate_candidate_document,
    validate_evolution_run_document,
)
from verfeinert.ansatz_analyzer import validate_analysis_result_document
from verfeinert.core import read_yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "CX01_reproduction"
SCRIPT_PATH = EXAMPLE_ROOT / "scripts" / "run_cx01_reproduction.py"
CONFIG_PATH = EXAMPLE_ROOT / "config" / "cx01_reproduction.yaml"


def _load_script():
    spec = importlib.util.spec_from_file_location("cx01_reproduction_script", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load CX-01 reproduction script.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CX01ReproductionTests(unittest.TestCase):
    def test_config_preserves_reference_scientific_meaning(self) -> None:
        config = read_yaml(CONFIG_PATH)
        campaign = config["cx01_campaign"]

        self.assertEqual(campaign["name"], "CX-01")
        self.assertEqual(campaign["library"], "sanz19")
        self.assertEqual(campaign["n_qubits"], 4)
        self.assertEqual(campaign["layers"], [1, 2, 3])
        self.assertEqual(campaign["mutation"]["gate"], "cx")
        self.assertEqual(campaign["candidate_policy"]["edges"], "all_valid")
        self.assertEqual(campaign["analysis_reference"]["cost_thresholds"], [1.0, 0.2, 0.1])

    def test_smoke_reproduction_uses_public_workflow_and_valid_schemas(self) -> None:
        module = _load_script()
        with TemporaryDirectory() as temp_dir:
            result = module.run_reproduction(
                CONFIG_PATH,
                output_root_override=Path(temp_dir) / "outputs",
                profile="smoke",
            )
            summary = result.to_dict()

            self.assertEqual(summary["generated_candidate_count"], 4)
            self.assertEqual(len(summary["workflow_result"]["candidate_ids"]), 4)
            self.assertTrue(Path(summary["comparison_report_path"]).is_file())

            for path in summary["workflow_result"]["candidate_paths"]:
                candidate = validate_candidate_document(json.loads(Path(path).read_text(encoding="utf-8")))
                self.assertEqual(candidate["lineage"]["mutation"]["type"], "knock_in")
                self.assertEqual(candidate["lineage"]["mutation"]["operation"], "cx")

            for path in summary["workflow_result"]["analysis_result_paths"]:
                validate_analysis_result_document(json.loads(Path(path).read_text(encoding="utf-8")))

            evolution = validate_evolution_run_document(
                json.loads(Path(summary["workflow_result"]["evolution_run_path"]).read_text(encoding="utf-8")),
            )
            analysis_refs = evolution["generations"][0]["analysis_result_refs"]
            self.assertEqual(
                [ref["candidate_id"] for ref in analysis_refs],
                summary["workflow_result"]["candidate_ids"],
            )

    def test_example_has_no_local_or_legacy_coupling(self) -> None:
        forbidden = (
            "/home/",
            "Thesis_Data_Processing",
            "python/ansatz_generator",
            "Verfeinert/src",
            "project_generator_record_to_candidate",
            "_canonical_operations",
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

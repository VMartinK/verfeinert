"""Integration tests for the CX-01 reproduction example."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from collections import Counter, defaultdict

from verfeinert.ansatz_evolver import (
    validate_candidate_document,
)
from verfeinert.ansatz_analyzer import validate_analysis_result_document
from verfeinert.core import read_yaml
from verfeinert.workflow import WorkflowConfig


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
        workflow = WorkflowConfig.from_mapping(config)
        self.assertEqual(workflow.campaign_type, "individual")
        self.assertEqual(workflow.scientific_execution, ("generate", "analyze"))
        self.assertEqual(workflow.postprocessing, ("ranking",))

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
            self.assertEqual(
                summary["workflow_result"]["candidate_ids"],
                [
                    "cx01repro-a02-l1_cx-v001",
                    "cx01repro-a02-l1_cx-v002",
                    "cx01repro-a09-l1_cx-v001",
                    "cx01repro-a09-l1_cx-v002",
                ],
            )
            self.assertEqual(summary["workflow_result"]["executed_operations"], ["generate", "analyze", "ranking"])
            self.assertIsNone(summary["workflow_result"]["evolution_run_path"])
            self.assertEqual(summary["workflow_result"]["provenance"]["execution"]["campaign_type"], "individual")
            self.assertFalse(summary["workflow_result"]["provenance"]["execution"]["evolution_exported"])
            self.assertTrue(Path(summary["comparison_report_path"]).is_file())

            for path in summary["workflow_result"]["candidate_paths"]:
                candidate = validate_candidate_document(json.loads(Path(path).read_text(encoding="utf-8")))
                self.assertEqual(candidate["lineage"]["mutation"]["type"], "knock_in")
                self.assertEqual(candidate["lineage"]["mutation"]["operation"], "cx")

            for path in summary["workflow_result"]["analysis_result_paths"]:
                validate_analysis_result_document(json.loads(Path(path).read_text(encoding="utf-8")))

    def test_full_reproduction_matches_historical_structural_counts(self) -> None:
        module = _load_script()
        config = read_yaml(CONFIG_PATH)

        records = module.build_cx01_candidate_records(config, profile="full")

        self.assertEqual(len(records), 396)
        self.assertEqual(Counter(record["layer"] for record in records), {1: 132, 2: 132, 3: 132})
        by_template_layer = Counter(
            (record["metadata"]["template_id"], record["layer"])
            for record in records
        )
        expected_l1 = {
            "A01": 0,
            "A02": 6,
            "A03": 6,
            "A04": 6,
            "A05": 12,
            "A06": 12,
            "A07": 6,
            "A08": 6,
            "A09": 6,
            "A10": 8,
            "A11": 6,
            "A12": 6,
            "A13": 8,
            "A14": 8,
            "A15": 8,
            "A16": 6,
            "A17": 6,
            "A18": 8,
            "A19": 8,
        }
        for template_id, count in expected_l1.items():
            self.assertEqual(by_template_layer[(template_id, 1)], count)
        by_template_total = Counter(record["metadata"]["template_id"] for record in records)
        self.assertEqual(by_template_total["A01"], 0)
        self.assertEqual(by_template_total["A02"], 18)
        self.assertEqual(by_template_total["A05"], 36)
        self.assertEqual(by_template_total["A10"], 24)
        self.assertEqual(by_template_total["A19"], 24)
        self.assertEqual(
            module._historical_edges("A02", n_qubits=4),
            ((0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)),
        )
        self.assertEqual(
            module._historical_edges("A10", n_qubits=4),
            ((0, 1), (1, 0), (0, 3), (3, 0), (1, 2), (2, 1), (2, 3), (3, 2)),
        )

        grouped: dict[tuple[str, int], dict[int, dict]] = defaultdict(dict)
        for record in records:
            grouped[(record["metadata"]["template_id"], record["variant_index"])][record["layer"]] = record
        a02_variant_1 = grouped[("A02", 1)]
        self.assertEqual(set(a02_variant_1), {1, 2, 3})
        self.assertEqual(
            {
                layer: item["metadata"]["mutation_edge"]
                for layer, item in a02_variant_1.items()
            },
            {1: [0, 1], 2: [0, 1], 3: [0, 1]},
        )
        self.assertEqual(
            {
                layer: _inserted_cx_count(item)
                for layer, item in a02_variant_1.items()
            },
            {1: 1, 2: 2, 3: 3},
        )

    def test_materialized_smoke_uses_analyzer_owned_qnode_bridge(self) -> None:
        module = _load_script()
        with TemporaryDirectory() as temp_dir:
            result = module.run_reproduction(
                CONFIG_PATH,
                output_root_override=Path(temp_dir) / "outputs",
                profile="materialized_smoke",
            )
            summary = result.to_dict()

            self.assertEqual(summary["generated_candidate_count"], 1)
            self.assertIsNone(summary["workflow_result"]["evolution_run_path"])
            payload = validate_analysis_result_document(
                json.loads(Path(summary["workflow_result"]["analysis_result_paths"][0]).read_text(encoding="utf-8")),
            )
            metrics = {metric["name"]: metric for metric in payload["metrics"]}
            self.assertEqual(metrics["expressibility"]["status"], "computed")
            self.assertEqual(metrics["trainability"]["status"], "computed")
            self.assertTrue(metrics["expressibility"]["metadata"]["qnodes_executed"])
            self.assertTrue(metrics["trainability"]["metadata"]["qnodes_executed"])

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


def _inserted_cx_count(record: dict) -> int:
    return sum(
        1
        for operation in record["operations"]
        if operation["gate"] == "cx"
        and operation.get("metadata", {}).get("source") == "cx01_reproduction"
    )


if __name__ == "__main__":
    unittest.main()

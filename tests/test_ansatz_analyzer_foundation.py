"""Tests for the Verfeinert analyzer foundation slice."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalyzerConfig,
    StructuralCostConfig,
    load_candidate_views,
    validate_analysis_result_document,
    write_analysis_result_json,
)
from verfeinert.ansatz_analyzer.config import AnalyzerConfigError
from verfeinert.ansatz_analyzer.validation import AnalyzerValidationError
from verfeinert.core.io import read_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
ANALYZER_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_analyzer"

EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}

FORBIDDEN_IMPORTS = {
    "verfeinert.ansatz_generator",
    "verfeinert.ansatz_evolver",
    "ansatz_generator",
    "ansatz_evolver",
    "matplotlib",
    "pandas",
    "notebook",
    "nbformat",
    "nbclient",
}
SCIENTIFIC_METRIC_IMPORTS = {
    "numpy",
    "pennylane",
}


def _candidate_example() -> dict:
    return json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))


def _staged_package() -> dict:
    first = _candidate_example()
    second = copy.deepcopy(first)
    second["candidate_id"] = "reference-a02-l1-second"
    second["lineage"]["root_candidate_id"] = "reference-a02-l1-second"
    return {
        "schema_version": "verfeinert.staged_package.v1",
        "package_id": "foundation-package-001",
        "manifest": {
            "package_kind": "candidate_package",
            "created_at": "2026-08-06T00:00:00Z",
            "producer": "schema-test",
            "candidate_count": 2,
            "schema_versions": {
                "candidate": "verfeinert.candidate.v1",
            },
            "execution_flags": {
                "qnodes_executed": False,
                "scientific_metrics_executed": False,
                "generated_callables_imported": False,
            },
        },
        "candidates": [first, second],
        "artifacts": [],
        "provenance": {
            "created_at": "2026-08-06T00:00:00Z",
            "source": "analyzer-foundation-test",
            "software_version": "0.0.0",
            "git_commit": None,
            "input_hashes": {},
        },
    }


def _config(tmp_path: Path, *, structural_cost: StructuralCostConfig | None = None) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    output_root = tmp_path / "outputs"
    input_root.mkdir()
    return AnalyzerConfig(
        run_id="foundation-run",
        input_roots=(input_root,),
        output_root=output_root,
        structural_cost=structural_cost or StructuralCostConfig(
            reference_bounds=EXPLICIT_REFERENCE_BOUNDS,
        ),
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class AnsatzAnalyzerFoundationTests(unittest.TestCase):
    def test_valid_candidate_json_loads_and_builds_candidate_view(self) -> None:
        views = load_candidate_views(CANDIDATE_EXAMPLE)

        self.assertEqual(len(views), 1)
        view = views[0]
        self.assertEqual(view.candidate_id, "reference-a02-l1-parent")
        self.assertEqual(view.n_qubits, 2)
        self.assertEqual(view.parameter_count, 2)
        self.assertEqual(view.operation_count, 3)
        self.assertEqual(view.two_qubit_operation_count, 1)
        self.assertEqual([operation.gate_name for operation in view.operations], ["rx", "rz", "cz"])

    def test_invalid_candidate_is_rejected_by_schema_validation(self) -> None:
        candidate = _candidate_example()
        candidate.pop("circuit")

        with self.assertRaises(AnalyzerValidationError):
            load_candidate_views(candidate)

    def test_staged_package_loads_candidate_views_in_package_order(self) -> None:
        views = load_candidate_views(_staged_package())

        self.assertEqual(
            [view.candidate_id for view in views],
            ["reference-a02-l1-parent", "reference-a02-l1-second"],
        )

    def test_structural_cost_fixture_uses_operation_count_depth_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp))
            result = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0]
            payload = validate_analysis_result_document(result.to_dict())

        self.assertEqual(payload["schema_version"], "verfeinert.analysis_result.v1")
        self.assertEqual(payload["metrics"][0]["status"], "computed")
        self.assertEqual(payload["metrics"][0]["name"], "structural_cost")
        self.assertAlmostEqual(payload["cost"]["structural_cost"], 0.5)
        self.assertEqual(payload["cost"]["parameter_count"], 2)
        self.assertEqual(payload["cost"]["operation_count"], 3)
        self.assertEqual(payload["cost"]["two_qubit_operation_count"], 1)
        metadata = payload["cost"]["metadata"]
        self.assertEqual(metadata["depth_source"], "operation_count_proxy")
        self.assertIn("operation_count as a depth proxy", " ".join(metadata["warnings"]))
        self.assertFalse(payload["provenance"]["execution"]["qnodes_executed"])
        self.assertFalse(payload["provenance"]["execution"]["expensive_metrics_executed"])
        self.assertFalse(payload["provenance"]["execution"]["plots_generated"])

    def test_structural_cost_derives_bounds_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp), structural_cost=StructuralCostConfig())
            result = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0]
            payload = result.to_dict()

        self.assertEqual(payload["cost"]["structural_cost"], 0.0)
        warnings = " ".join(payload["cost"]["metadata"]["warnings"])
        self.assertIn("derived from the selected candidates", warnings)
        self.assertIn("zero width", warnings)

    def test_analysis_result_json_write_is_guarded_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _config(tmp_path)
            result = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0]
            path = write_analysis_result_json(result, config)

            self.assertTrue(path.is_file())
            self.assertEqual(path.parent, tmp_path / "outputs" / "foundation-run")
            payload = validate_analysis_result_document(read_json(path))
            self.assertEqual(
                payload["candidate_ref"]["candidate_id"],
                "reference-a02-l1-parent",
            )

    def test_output_root_nested_with_input_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            with self.assertRaises(ValueError):
                AnalyzerConfig(
                    run_id="bad-output-root",
                    input_roots=(input_root,),
                    output_root=input_root / "nested-output",
                )

    def test_unavailable_expensive_metrics_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            input_root.mkdir()
            with self.assertRaises(AnalyzerConfigError):
                AnalyzerConfig(
                    run_id="bad-metric",
                    input_roots=(input_root,),
                    output_root=tmp_path / "outputs",
                    selected_metrics=("expressibility",),
                )

    def test_pipeline_accepts_staged_package_and_writes_one_result_per_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(Path(tmp))
            paths = AnalysisPipeline(config).run_and_write(_staged_package())

            self.assertEqual(len(paths), 2)
            self.assertEqual([path.suffix for path in paths], [".json", ".json"])
            payloads = [validate_analysis_result_document(read_json(path)) for path in paths]
            self.assertEqual(
                [payload["candidate_ref"]["candidate_id"] for payload in payloads],
                ["reference-a02-l1-parent", "reference-a02-l1-second"],
            )

    def test_analyzer_foundation_has_no_deferred_or_heavy_imports(self) -> None:
        violations: list[str] = []
        for path in sorted(ANALYZER_ROOT.rglob("*.py")):
            for module in _imported_modules(path):
                if any(
                    module == allowed or module.startswith(f"{allowed}.")
                    for allowed in SCIENTIFIC_METRIC_IMPORTS
                ):
                    if path.relative_to(ANALYZER_ROOT).parts[:1] == ("metrics",):
                        continue
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
                    continue
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_IMPORTS
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

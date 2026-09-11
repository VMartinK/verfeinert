"""Tests for CLI scientific overrides (qubits, Hamiltonian, trials, protocol) and serve."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest

import yaml

from verfeinert.cli import main
from verfeinert.workflow import WorkflowConfig


BASE_CONFIG = {
    "run": {"run_id": "override-check", "random_seed": 1},
    "paths": {"output_root": "outputs"},
    "workflow": {"campaign_type": "individual", "scientific_execution": ["generate", "analyze"], "postprocessing": ["ranking"]},
    "generation": {"family": "sanz19", "template_ids": ["A04"], "layers": [1], "n_qubits": 4, "candidate_id_prefix": "chk"},
    "analyzer": {
        "selected_metrics": ["structural_cost"],
        "structural_cost": {
            "reference_bounds": {
                "parameter_count": {"min": 0, "max": 64},
                "depth": {"min": 0, "max": 128},
                "two_qubit_operation_count": {"min": 0, "max": 32},
            },
        },
        "ranking": {"score_components": {"cost.structural_cost": 1.0}, "combination": "weighted_sum", "ascending": True},
    },
}


class CliScientificOverrideTests(unittest.TestCase):
    def _write_config(self, root: Path) -> Path:
        path = root / "workflow.yaml"
        payload = dict(BASE_CONFIG)
        payload["paths"] = {"output_root": str(root / "outputs")}
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        return path

    def test_validate_applies_qubits_hamiltonian_trials_and_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "validate",
                        str(config_path),
                        "--n-qubits",
                        "6",
                        "--hamiltonian",
                        "heisenberg",
                        "--hamiltonian-param",
                        "Jz=2",
                        "--trials",
                        "4",
                        "--protocol",
                        "paper",
                    ],
                )
            self.assertEqual(code, 0, stdout.getvalue())
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "valid")
            from verfeinert.cli import _apply_overrides, _load_config_mapping

            mapping = _apply_overrides(
                _load_config_mapping(config_path),
                {"n_qubits": 6, "hamiltonian": "heisenberg", "hamiltonian_parameters": {"Jz": 2.0}, "n_trials": 4, "protocol": "paper"},
            )
            config = WorkflowConfig.from_mapping(mapping)
            self.assertEqual(config.generation.n_qubits, 6)
            trainability = config.analyzer.metric_configs["trainability"]
            self.assertEqual(trainability["hamiltonian"], "heisenberg")
            self.assertEqual(trainability["hamiltonian_parameters"]["Jz"], 2.0)
            self.assertEqual(trainability["n_trials"], 4)
            self.assertEqual(trainability["n_repeats"], 3000)
            self.assertEqual(config.analyzer.metric_configs["expressibility"]["n_pairs"], 10000)
            self.assertIn("trainability", config.analyzer.selected_metrics)

    def test_invalid_overrides_return_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root)
            stderr = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                code = main(["validate", str(config_path), "--hamiltonian", "hubbard"])
            self.assertEqual(code, 2)
            self.assertIn("Unsupported hamiltonian", stderr.getvalue())
            stderr = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                code = main(["run", str(config_path), "--hamiltonian-param", "J"])
            self.assertEqual(code, 2)
            self.assertIn("NAME=VALUE", stderr.getvalue())

    def test_run_with_fast_protocol_override_executes_scientific_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                code = main(
                    [
                        "run",
                        str(config_path),
                        "--n-qubits",
                        "3",
                        "--hamiltonian",
                        "ising",
                        "--protocol",
                        "fast",
                        "--trials",
                        "2",
                    ],
                )
            self.assertEqual(code, 0, stdout.getvalue())
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["status"], "completed")
            analysis_files = list((root / "outputs").rglob("*analysis*.json"))
            self.assertTrue(analysis_files)
            documents = [json.loads(path.read_text(encoding="utf-8")) for path in analysis_files]
            documents = [doc for doc in documents if isinstance(doc, dict) and doc.get("metrics")]
            self.assertTrue(documents)
            metrics = {metric["name"]: metric for metric in documents[0]["metrics"]}
            self.assertEqual(metrics["trainability"]["status"], "computed", metrics["trainability"].get("error"))
            self.assertEqual(metrics["trainability"]["metadata"]["hamiltonian"], "tfim")
            self.assertEqual(metrics["trainability"]["metadata"]["n_qubits"], 3)
            self.assertEqual(metrics["trainability"]["value"]["n_trials"], 2)
            self.assertEqual(metrics["expressibility"]["metadata"]["bin_strategy"], "equal_mass")

    def test_serve_command_is_registered(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit):
            main(["serve", "--help"])
        self.assertIn("--no-browser", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

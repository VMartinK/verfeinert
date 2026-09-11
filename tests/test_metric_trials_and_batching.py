"""Tests for multi-trial, equal-mass-bin and batched metric evaluation."""

from __future__ import annotations

import math
import unittest

import numpy as np

from verfeinert.ansatz_analyzer import (
    AnalyzerConfig,
    AnalyzerExecutionPermissions,
    CandidateView,
    CircuitMaterializationConfig,
    analyze_candidates,
    materialize_candidate,
)
from verfeinert.ansatz_analyzer.metrics.expressibility import (
    ExpressibilityConfig,
    compute_expressibility_metric,
    haar_bin_edges,
    haar_bin_masses,
)
from verfeinert.ansatz_analyzer.metrics.trainability import (
    TrainabilityConfig,
    compute_trainability_metric,
)
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    build_sanz19_candidate_record,
    export_candidate_json,
)


PERMISSIONS = AnalyzerExecutionPermissions(allow_expensive_metrics=True, allow_qnode_execution=True)


def _candidate(template_id: str = "A04", *, n_qubits: int = 3, layer: int = 1) -> dict:
    record = build_sanz19_candidate_record(template_id, layer, n_qubits=n_qubits)
    return export_candidate_json(record, config=CandidateJsonExportConfig(candidate_id_prefix="trial", n_qubits=n_qubits))


class HaarBinTests(unittest.TestCase):
    def test_equal_mass_bins_have_uniform_haar_mass(self) -> None:
        for n_qubits in (2, 3, 5):
            masses = haar_bin_masses(n_qubits, 10, strategy="equal_mass")
            np.testing.assert_allclose(masses, [0.1] * 10, atol=1e-12)
            edges = haar_bin_edges(n_qubits, 10, strategy="equal_mass")
            self.assertEqual(edges[0], 0.0)
            self.assertEqual(edges[-1], 1.0)
            self.assertTrue(np.all(np.diff(edges) > 0))

    def test_equal_width_bins_are_unchanged(self) -> None:
        np.testing.assert_allclose(haar_bin_edges(3, 4), [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(haar_bin_masses(2, 5), haar_bin_masses(2, 5, strategy="equal_width"))
        with self.assertRaises(ValueError):
            haar_bin_edges(2, 4, strategy="quantile")


class ExpressibilityTrialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _candidate()
        self.view = CandidateView.from_document(self.document)
        self.materialized = materialize_candidate(self.view, config=CircuitMaterializationConfig(enabled=True))

    def test_batched_and_sequential_fidelities_agree(self) -> None:
        config = ExpressibilityConfig(n_pairs=64, n_bins=8, rng_seed=11, bin_strategy="equal_mass")
        sequential = compute_expressibility_metric(self.view, self.materialized.state_callable, config=config, permissions=PERMISSIONS)
        batched = compute_expressibility_metric(
            self.view,
            self.materialized.state_callable,
            config=config,
            permissions=PERMISSIONS,
            materialized=self.materialized,
        )
        self.assertEqual(sequential.status, "computed", sequential.error)
        self.assertEqual(batched.status, "computed", batched.error)
        self.assertEqual(sequential.metadata["batch_size"], 1)
        self.assertGreater(batched.metadata["batch_size"], 1)
        self.assertAlmostEqual(sequential.value["expressibility"], batched.value["expressibility"], places=10)
        self.assertAlmostEqual(sequential.metadata["fidelity_mean"], batched.metadata["fidelity_mean"], places=10)

    def test_single_trial_matches_legacy_value_fields(self) -> None:
        config = ExpressibilityConfig(n_pairs=32, n_bins=6, rng_seed=5)
        metric = compute_expressibility_metric(self.view, self.materialized.state_callable, config=config, permissions=PERMISSIONS)
        self.assertEqual(metric.value["n_trials"], 1)
        self.assertEqual(metric.value["expressibility_std"], 0.0)
        self.assertEqual(len(metric.metadata["trials"]), 1)
        self.assertEqual(metric.metadata["trials"][0]["rng_seed_used"], metric.metadata["rng_seed_used"])
        self.assertEqual(metric.metadata["state_calls"], 64)

    def test_multiple_trials_report_mean_and_std(self) -> None:
        config = ExpressibilityConfig(n_pairs=40, n_bins=6, rng_seed=5, n_trials=4)
        metric = compute_expressibility_metric(
            self.view,
            self.materialized.state_callable,
            config=config,
            permissions=PERMISSIONS,
            materialized=self.materialized,
        )
        trials = metric.metadata["trials"]
        self.assertEqual(len(trials), 4)
        seeds = [trial["rng_seed_used"] for trial in trials]
        self.assertEqual(len(set(seeds)), 4)
        values = [trial["expressibility"] for trial in trials]
        self.assertAlmostEqual(metric.value["expressibility"], float(np.mean(values)))
        self.assertAlmostEqual(metric.value["expressibility_std"], float(np.std(values, ddof=1)))
        self.assertEqual(metric.metadata["state_calls"], 2 * 40 * 4)
        # First trial reproduces the single-trial estimate exactly.
        single = compute_expressibility_metric(
            self.view,
            self.materialized.state_callable,
            config=ExpressibilityConfig(n_pairs=40, n_bins=6, rng_seed=5),
            permissions=PERMISSIONS,
            materialized=self.materialized,
        )
        self.assertAlmostEqual(trials[0]["expressibility"], single.value["expressibility"], places=12)

    def test_from_mapping_accepts_n_samples_alias(self) -> None:
        config = ExpressibilityConfig.from_mapping({"n_samples": 12, "n_bins": 3})
        self.assertEqual(config.n_pairs, 12)
        with self.assertRaises(ValueError):
            ExpressibilityConfig(n_trials=0)


class TrainabilityHamiltonianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _candidate("A10")
        self.view = CandidateView.from_document(self.document)
        self.materialized = materialize_candidate(self.view, config=CircuitMaterializationConfig(enabled=True))

    def test_batched_and_sequential_gradients_agree_for_every_hamiltonian(self) -> None:
        for hamiltonian, parameters in (("local_x", None), ("tfim", {"J": 0.8, "h": 1.2}), ("heisenberg", {"Jz": 1.5})):
            config = TrainabilityConfig(n_repeats=12, rng_seed=3, hamiltonian=hamiltonian, hamiltonian_parameters=parameters)
            sequential = compute_trainability_metric(self.view, self.materialized.state_callable, config=config, permissions=PERMISSIONS)
            batched = compute_trainability_metric(
                self.view,
                self.materialized.state_callable,
                config=config,
                permissions=PERMISSIONS,
                materialized=self.materialized,
            )
            self.assertEqual(sequential.status, "computed", sequential.error)
            self.assertEqual(batched.status, "computed", batched.error)
            self.assertEqual(sequential.metadata["energy_backend"], "dense_matrix.state")
            self.assertEqual(batched.metadata["energy_backend"], "pennylane.expval.broadcast")
            self.assertAlmostEqual(sequential.value["trainability"], batched.value["trainability"], places=9)
            self.assertEqual(batched.metadata["hamiltonian"], hamiltonian)
            self.assertIn("hamiltonian_parameters", batched.metadata)
            self.assertGreater(batched.value["trainability"], 0.0)

    def test_local_x_metadata_remains_backwards_compatible(self) -> None:
        config = TrainabilityConfig(n_repeats=4, rng_seed=1)
        metric = compute_trainability_metric(self.view, self.materialized.state_callable, config=config, permissions=PERMISSIONS)
        self.assertEqual(metric.metadata["hamiltonian"], "local_x")
        self.assertEqual(metric.metadata["hamiltonian_kind"], "sum_x")
        self.assertEqual(metric.metadata["hamiltonian_definition"], "H = sum_i X_i")
        self.assertEqual(metric.metadata["hamiltonian_scale"], 1.0)
        self.assertEqual(metric.value["n_trials"], 1)
        self.assertEqual(metric.value["trainability_std"], 0.0)

    def test_multiple_trials_and_all_parameter_average(self) -> None:
        config = TrainabilityConfig(n_repeats=10, rng_seed=9, hamiltonian="tfim", n_trials=3, average_over="all")
        metric = compute_trainability_metric(
            self.view,
            self.materialized.state_callable,
            config=config,
            permissions=PERMISSIONS,
            materialized=self.materialized,
        )
        self.assertEqual(metric.status, "computed", metric.error)
        trials = metric.metadata["trials"]
        self.assertEqual(len(trials), 3)
        self.assertEqual(len({trial["rng_seed_used"] for trial in trials}), 3)
        values = [trial["trainability"] for trial in trials]
        self.assertAlmostEqual(metric.value["trainability"], float(np.mean(values)))
        self.assertAlmostEqual(metric.value["trainability_std"], float(np.std(values, ddof=1)))
        self.assertAlmostEqual(metric.value["trainability"], metric.value["trainability_all_parameters"])
        self.assertEqual(metric.metadata["gradient_components"], 10 * self.view.parameter_count * 3)

    def test_mapping_aliases_and_validation(self) -> None:
        config = TrainabilityConfig.from_mapping({"n_samples": 7, "hamiltonian": "ising", "hamiltonian_parameters": {"J": 2.0}})
        self.assertEqual(config.n_repeats, 7)
        self.assertEqual(config.hamiltonian, "tfim")
        self.assertEqual(config.hamiltonian_spec.parameters["J"], 2.0)
        with self.assertRaises(ValueError):
            TrainabilityConfig(average_over="median")
        with self.assertRaises(ValueError):
            TrainabilityConfig.from_mapping({"n_samples": 7, "n_repeats": 8})


class PipelineIntegrationTests(unittest.TestCase):
    def test_pipeline_runs_manuscript_hamiltonian_with_trials_for_six_qubits(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        document = _candidate("A14", n_qubits=6)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "candidate.json").write_text(json.dumps(document), encoding="utf-8")
            config = AnalyzerConfig.from_mapping(
                {
                    "run_id": "six-qubit-tfim",
                    "input_roots": [str(inputs)],
                    "output_root": str(root / "outputs"),
                    "selected_metrics": ["structural_cost", "expressibility", "trainability"],
                    "permissions": {"allow_expensive_metrics": True, "allow_qnode_execution": True},
                    "materialization": {"enabled": True},
                    "metric_configs": {
                        "expressibility": {"n_pairs": 50, "n_bins": 10, "bin_strategy": "equal_mass", "n_trials": 2},
                        "trainability": {
                            "n_repeats": 6,
                            "n_trials": 2,
                            "hamiltonian": "tfim",
                            "hamiltonian_parameters": {"J": 1.0, "h": 0.5},
                            "parameter_low": 0.0,
                            "parameter_high": 2.0 * math.pi,
                        },
                    },
                }
            )
            records = analyze_candidates(inputs / "candidate.json", config)
        self.assertEqual(len(records), 1)
        metrics = {metric.name: metric for metric in records[0].metrics}
        self.assertEqual(metrics["expressibility"].status, "computed", metrics["expressibility"].error)
        self.assertEqual(metrics["trainability"].status, "computed", metrics["trainability"].error)
        self.assertEqual(metrics["trainability"].metadata["hamiltonian"], "tfim")
        self.assertEqual(metrics["trainability"].metadata["hamiltonian_parameters"], {"J": 1.0, "h": 0.5})
        self.assertEqual(metrics["trainability"].metadata["n_qubits"], 6)
        self.assertTrue(metrics["trainability"].metadata["batched_evaluation"])
        self.assertTrue(metrics["expressibility"].metadata["batched_evaluation"])
        self.assertEqual(metrics["expressibility"].value["n_trials"], 2)
        self.assertGreaterEqual(metrics["expressibility"].value["expressibility_std"], 0.0)


if __name__ == "__main__":
    unittest.main()

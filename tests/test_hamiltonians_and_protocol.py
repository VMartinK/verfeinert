"""Tests for parametrized benchmark Hamiltonians and manuscript protocol presets."""

from __future__ import annotations

import math
import unittest

import numpy as np

from verfeinert.ansatz_analyzer.metrics.hamiltonians import (
    HamiltonianError,
    HamiltonianSpec,
    hamiltonian_catalog,
    normalize_hamiltonian_kind,
)
from verfeinert.ansatz_analyzer.metrics.protocol import (
    PAPER_COST_WEIGHTS,
    apply_protocol_to_workflow_mapping,
    protocol_metric_configs,
    protocol_summary,
)


class HamiltonianSpecTests(unittest.TestCase):
    def test_aliases_and_defaults(self) -> None:
        self.assertEqual(normalize_hamiltonian_kind("ising"), "tfim")
        self.assertEqual(normalize_hamiltonian_kind("sum_x"), "local_x")
        self.assertEqual(normalize_hamiltonian_kind("XXX"), "heisenberg")
        spec = HamiltonianSpec("ising")
        self.assertEqual(spec.kind, "tfim")
        self.assertEqual(spec.parameters, {"J": 1.0, "h": 1.0})
        self.assertEqual(spec.legacy_kind, "tfim")
        self.assertEqual(HamiltonianSpec().metric_metadata()["hamiltonian_kind"], "sum_x")
        self.assertEqual(HamiltonianSpec().definition(), "H = sum_i X_i")

    def test_rejects_unknown_kind_and_parameters(self) -> None:
        with self.assertRaises(HamiltonianError):
            HamiltonianSpec("hubbard")
        with self.assertRaises(HamiltonianError):
            HamiltonianSpec("tfim", {"Jx": 1.0})
        with self.assertRaises(HamiltonianError):
            HamiltonianSpec("tfim", {"J": float("nan")})

    def test_local_x_matches_legacy_matrix(self) -> None:
        from verfeinert.ansatz_analyzer.metrics.trainability import make_trainability_hamiltonian_matrix

        legacy = make_trainability_hamiltonian_matrix(3, kind="sum_x", scale=2.0)
        new = HamiltonianSpec("local_x", {"h": 2.0}).to_dense(3)
        np.testing.assert_allclose(legacy, new)

    def test_dense_sparse_and_pennylane_agree(self) -> None:
        import pennylane as qml

        for kind, parameters in (
            ("tfim", {"J": 0.7, "h": 1.3}),
            ("heisenberg", {"Jx": 1.0, "Jy": 0.5, "Jz": 2.0, "h": 0.25}),
            ("local_x", {"h": 0.4}),
        ):
            for boundary in ("open", "periodic"):
                spec = HamiltonianSpec(kind, parameters, boundary=boundary)
                for n in (2, 3, 4):
                    dense = spec.to_dense(n)
                    sparse = spec.to_sparse(n).toarray()
                    np.testing.assert_allclose(dense, sparse, atol=1e-12)
                    pennylane = qml.matrix(spec.to_pennylane(n), wire_order=list(range(n)))
                    np.testing.assert_allclose(dense, pennylane, atol=1e-12)
                    self.assertTrue(np.allclose(dense, dense.conj().T))

    def test_ground_state_energies_for_known_cases(self) -> None:
        # Local-X: n qubits, energy -h * n.
        self.assertAlmostEqual(HamiltonianSpec("local_x", {"h": 1.5}).ground_state_energy(3), -4.5)
        # TFIM with h = 0 (classical Ising chain): -J (n - 1).
        self.assertAlmostEqual(HamiltonianSpec("tfim", {"J": 1.0, "h": 0.0}).ground_state_energy(4), -3.0)
        # Two-site isotropic Heisenberg singlet: -3.
        self.assertAlmostEqual(HamiltonianSpec("heisenberg").ground_state_energy(2), -3.0)
        energy, vector = HamiltonianSpec("tfim").ground_state(3)
        matrix = HamiltonianSpec("tfim").to_dense(3)
        np.testing.assert_allclose(matrix @ vector, energy * vector, atol=1e-9)
        self.assertAlmostEqual(HamiltonianSpec("tfim").expectation(vector), energy)

    def test_pauli_terms_scale_with_qubits(self) -> None:
        tfim = HamiltonianSpec("tfim")
        self.assertEqual(tfim.term_count(6), 5 + 6)
        self.assertEqual(HamiltonianSpec("tfim", boundary="periodic").term_count(6), 6 + 6)
        self.assertEqual(HamiltonianSpec("heisenberg").term_count(5), 3 * 4)
        self.assertEqual(HamiltonianSpec("heisenberg", {"h": 1.0}).term_count(5), 3 * 4 + 5)
        self.assertEqual(HamiltonianSpec("local_x").term_count(9), 9)

    def test_catalog_is_json_safe_and_complete(self) -> None:
        catalog = hamiltonian_catalog()
        self.assertEqual([item["kind"] for item in catalog], ["local_x", "tfim", "heisenberg"])
        tfim = next(item for item in catalog if item["kind"] == "tfim")
        self.assertEqual([p["name"] for p in tfim["parameters"]], ["J", "h"])
        self.assertIn("ising", tfim["aliases"])

    def test_resolve_legacy_and_mapping_forms(self) -> None:
        legacy = HamiltonianSpec.resolve(hamiltonian=None, hamiltonian_kind="sum_x", hamiltonian_scale=3.0)
        self.assertEqual((legacy.kind, legacy.parameters), ("local_x", {"h": 3.0}))
        mapped = HamiltonianSpec.from_mapping({"kind": "heisenberg", "Jz": 2.0})
        self.assertEqual(mapped.parameters["Jz"], 2.0)
        with self.assertRaises(HamiltonianError):
            HamiltonianSpec.resolve(hamiltonian="tfim", hamiltonian_kind="sum_x")


class ProtocolPresetTests(unittest.TestCase):
    def test_paper_protocol_matches_manuscript_sampling(self) -> None:
        configs = protocol_metric_configs("paper", hamiltonian="tfim")
        self.assertEqual(configs["expressibility"]["n_pairs"], 10000)
        self.assertEqual(configs["expressibility"]["n_bins"], 75)
        self.assertEqual(configs["expressibility"]["bin_strategy"], "equal_mass")
        self.assertEqual(configs["expressibility"]["n_trials"], 5)
        self.assertEqual(configs["trainability"]["n_repeats"], 3000)
        self.assertEqual(configs["trainability"]["n_trials"], 5)
        self.assertEqual(configs["trainability"]["hamiltonian"], "tfim")
        self.assertEqual(configs["trainability"]["hamiltonian_parameters"], {"J": 1.0, "h": 1.0})
        self.assertAlmostEqual(configs["trainability"]["parameter_high"], 2.0 * math.pi)
        self.assertAlmostEqual(sum(PAPER_COST_WEIGHTS.values()), 1.0, places=3)
        custom = protocol_metric_configs("fast", n_trials=3, hamiltonian="heisenberg", hamiltonian_parameters={"Jz": 0.5}, rng_seed=7)
        self.assertEqual(custom["trainability"]["hamiltonian_parameters"]["Jz"], 0.5)
        self.assertEqual(custom["expressibility"]["rng_seed"], 7)
        with self.assertRaises(ValueError):
            protocol_metric_configs("unknown")
        self.assertEqual(protocol_summary("paper")["vqe"]["steps"], 200)

    def test_apply_protocol_to_workflow_mapping(self) -> None:
        mapping = {
            "generation": {"family": "sanz19", "n_qubits": 4, "template_ids": ["A04"], "layers": [1]},
            "analyzer": {
                "selected_metrics": ["structural_cost"],
                "metric_configs": {"trainability": {"hamiltonian_kind": "sum_x", "rng_seed": 3}},
            },
        }
        updated = apply_protocol_to_workflow_mapping(
            mapping,
            protocol="paper",
            n_qubits=6,
            n_trials=3,
            hamiltonian="ising",
            hamiltonian_parameters={"h": 0.5},
        )
        self.assertEqual(updated["generation"]["n_qubits"], 6)
        trainability = updated["analyzer"]["metric_configs"]["trainability"]
        self.assertEqual(trainability["hamiltonian"], "tfim")
        self.assertEqual(trainability["hamiltonian_parameters"], {"J": 1.0, "h": 0.5})
        self.assertEqual(trainability["n_trials"], 3)
        self.assertEqual(trainability["rng_seed"], 3)
        self.assertNotIn("hamiltonian_kind", trainability)
        self.assertEqual(updated["analyzer"]["metric_configs"]["expressibility"]["n_pairs"], 10000)
        self.assertEqual(updated["analyzer"]["selected_metrics"], ["structural_cost", "expressibility", "trainability"])
        self.assertTrue(updated["analyzer"]["permissions"]["allow_qnode_execution"])
        self.assertTrue(updated["analyzer"]["materialization"]["enabled"])
        self.assertEqual(updated["analyzer"]["structural_cost"]["component_weights"], PAPER_COST_WEIGHTS)
        # Original mapping is untouched.
        self.assertEqual(mapping["generation"]["n_qubits"], 4)
        # Overrides without protocol only touch what was requested.
        partial = apply_protocol_to_workflow_mapping(mapping, n_trials=4)
        self.assertEqual(partial["analyzer"]["metric_configs"]["trainability"]["n_trials"], 4)
        self.assertEqual(partial["analyzer"]["selected_metrics"], ["structural_cost"])


if __name__ == "__main__":
    unittest.main()

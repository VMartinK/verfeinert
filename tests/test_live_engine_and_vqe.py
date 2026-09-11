"""Tests for the interactive evolution engine, VQE validation and local server."""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request

from verfeinert.ansatz_analyzer.metrics.hamiltonians import HamiltonianSpec
from verfeinert.live import (
    OPTIMIZERS,
    LiveEngineError,
    LiveRunConfig,
    VQEConfig,
    evaluate_candidate_document,
    optimizer_catalog,
    run_live_evolution,
    run_vqe,
)
from verfeinert.live.engine import structural_dedupe_key, template_catalog
from verfeinert.live.server import build_catalog, create_server


FAST_CONFIG = {
    "n_qubits": 3,
    "hamiltonian": {"kind": "tfim", "parameters": {"J": 1.0, "h": 1.0}},
    "n_trials": 2,
    "protocol": "custom",
    "n_pairs": 24,
    "n_bins": 6,
    "n_samples": 8,
    "template_ids": ["A01", "A04", "A10"],
    "layers": [1],
    "max_generations": 2,
    "elite_size": 2,
    "children_per_parent": 2,
    "random_seed": 3,
    "workers": 1,
}


class LiveRunConfigTests(unittest.TestCase):
    def test_from_mapping_and_validation(self) -> None:
        config = LiveRunConfig.from_mapping({**FAST_CONFIG, "hamiltonian": "ising", "hamiltonian_parameters": {"h": 0.5}})
        self.assertEqual(config.hamiltonian.kind, "tfim")
        self.assertEqual(config.hamiltonian.parameters["h"], 0.5)
        self.assertEqual(config.template_ids, ("A01", "A04", "A10"))
        metric_configs = config.metric_configs()
        self.assertEqual(metric_configs["expressibility"]["n_pairs"], 24)
        self.assertEqual(metric_configs["trainability"]["n_repeats"], 8)
        self.assertEqual(metric_configs["trainability"]["n_trials"], 2)
        self.assertEqual(metric_configs["trainability"]["hamiltonian"], "tfim")
        paper = LiveRunConfig.from_mapping({"n_qubits": 4, "protocol": "paper", "n_trials": 5})
        self.assertEqual(paper.metric_configs()["expressibility"]["n_pairs"], 10000)
        self.assertEqual(paper.metric_configs()["trainability"]["n_repeats"], 3000)
        with self.assertRaises(LiveEngineError):
            LiveRunConfig.from_mapping({"n_qubits": 1})
        with self.assertRaises(LiveEngineError):
            LiveRunConfig.from_mapping({"template_ids": ["Z99"]})
        self.assertEqual(len(LiveRunConfig.from_mapping({"template_ids": []}).template_ids), 19)
        with self.assertRaises(LiveEngineError):
            LiveRunConfig.from_mapping({"mutation_types": ["teleport"]})
        self.assertEqual(len(template_catalog()), 19)


class LiveEngineTests(unittest.TestCase):
    def test_evolution_emits_events_and_improves_or_keeps_best(self) -> None:
        events: list[dict] = []
        engine, result = run_live_evolution(FAST_CONFIG, emit=events.append)
        self.assertEqual(result["status"], "completed")
        types = [event["event_type"] for event in events]
        self.assertEqual(types[0], "run_started")
        self.assertEqual(types[-1], "run_completed")
        self.assertIn("population_initialized", types)
        self.assertIn("children_generated", types)
        self.assertEqual(types.count("generation_completed"), 3)
        evaluated = [event["candidate"] for event in events if event["event_type"] == "candidate_evaluated"]
        self.assertGreaterEqual(len(evaluated), 3 + 2 * 2)
        generation_zero = [item for item in evaluated if item["generation"] == 0]
        self.assertEqual(len(generation_zero), 3)
        for item in evaluated:
            self.assertEqual(item["status"], "computed", item.get("errors"))
            self.assertAlmostEqual(item["score"], item["expressibility"] * item["trainability"])
            self.assertEqual(len(item["expressibility_trials"]), 2)
            self.assertEqual(len(item["trainability_trials"]), 2)
            self.assertIn("operations", item)
        children = [item for item in evaluated if item["generation"] > 0]
        for child in children:
            self.assertIsNotNone(child["parent_id"])
            self.assertIn(child["mutation"]["type"], {"insert", "replace", "remove", "swap"})
        # Leaderboard is sorted and the best of the final generation event matches it.
        leaderboard = result["leaderboard"]
        scores = [row["score"] for row in leaderboard]
        self.assertEqual(scores, sorted(scores, reverse=True))
        final = [event for event in events if event["event_type"] == "generation_completed"][-1]
        self.assertEqual(final["best"]["candidate_id"], leaderboard[0]["candidate_id"])
        self.assertTrue(set(final["pareto_ids"]).issubset({row["candidate_id"] for row in leaderboard}))
        # Structural deduplication: no two evaluated circuits share a gate sequence.
        keys = {structural_dedupe_key(engine.document(row["candidate_id"])) for row in leaderboard}
        self.assertEqual(len(keys), len(leaderboard))
        json.dumps(events)

    def test_cancellation_stops_the_run(self) -> None:
        counter = {"evaluated": 0}
        events: list[dict] = []

        def emit(event: dict) -> None:
            events.append(event)
            if event["event_type"] == "candidate_evaluated":
                counter["evaluated"] += 1

        engine, result = run_live_evolution(
            {**FAST_CONFIG, "max_generations": 5},
            emit=emit,
            should_cancel=lambda: counter["evaluated"] >= 2,
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(events[-1]["event_type"], "run_cancelled")
        self.assertLessEqual(counter["evaluated"], 3)

    def test_cost_threshold_marks_infeasible_candidates(self) -> None:
        engine, result = run_live_evolution({**FAST_CONFIG, "cost_threshold": 0.3, "max_generations": 1}, emit=lambda e: None)
        rows = result["leaderboard"]
        self.assertTrue(any(not row["feasible"] for row in rows))
        self.assertTrue(all(row["feasible"] for row in rows if row["structural_cost"] <= 0.3))

    def test_evaluate_candidate_document_is_self_contained(self) -> None:
        config = LiveRunConfig.from_mapping(FAST_CONFIG)
        from verfeinert.ansatz_generator import CandidateJsonExportConfig, build_sanz19_candidate_record, export_candidate_json

        document = export_candidate_json(
            build_sanz19_candidate_record("A04", 1, n_qubits=3),
            config=CandidateJsonExportConfig(candidate_id_prefix="solo", n_qubits=3),
        )
        settings = {
            **config.metric_configs(),
            "structural_cost": {"component_weights": {"parameter_count": 1, "depth": 1, "two_qubit_operation_count": 1}},
        }
        result = evaluate_candidate_document(document, settings)
        self.assertEqual(result["status"], "computed", result["errors"])
        self.assertEqual(result["n_qubits"], 3)
        self.assertGreater(result["score"], 0.0)
        self.assertEqual(result["metrics"]["trainability"]["metadata"]["hamiltonian"], "tfim")


class VQETests(unittest.TestCase):
    def test_vqe_reduces_energy_and_reports_normalized_error(self) -> None:
        from verfeinert.ansatz_generator import CandidateJsonExportConfig, build_sanz19_candidate_record, export_candidate_json

        document = export_candidate_json(
            build_sanz19_candidate_record("A14", 1, n_qubits=3),
            config=CandidateJsonExportConfig(candidate_id_prefix="vqe", n_qubits=3),
        )
        events: list[dict] = []
        result = run_vqe(
            document,
            HamiltonianSpec("tfim"),
            config=VQEConfig(steps=25, restarts=2, learning_rate=0.1, random_seed=1, record_every=5),
            emit=events.append,
        )
        self.assertEqual(events[0]["event_type"], "vqe_started")
        self.assertEqual(events[-1]["event_type"], "vqe_completed")
        self.assertEqual(sum(1 for event in events if event["event_type"] == "vqe_step"), 2 * 5)
        self.assertAlmostEqual(result["exact_energy"], HamiltonianSpec("tfim").ground_state_energy(3))
        for restart in result["restarts"]:
            self.assertLess(restart["trajectory"][-1], restart["trajectory"][0])
        self.assertGreaterEqual(result["best_energy"], result["exact_energy"] - 1e-9)
        self.assertGreaterEqual(result["best_normalized_error"], 0.0)
        self.assertIsNotNone(result["ground_state_fidelity"])
        self.assertAlmostEqual(sum(item["probability"] for item in result["top_amplitudes"]), 1.0, places=6)
        self.assertEqual(len(result["median_trajectory"]), 26)
        self.assertEqual(result["optimizer"], "adam")
        self.assertEqual(result["restarts"][0]["iterations"], 25)
        with self.assertRaises(ValueError):
            VQEConfig(steps=0)

    @staticmethod
    def _document(template: str = "A14", n_qubits: int = 3) -> dict:
        from verfeinert.ansatz_generator import CandidateJsonExportConfig, build_sanz19_candidate_record, export_candidate_json

        return export_candidate_json(
            build_sanz19_candidate_record(template, 1, n_qubits=n_qubits),
            config=CandidateJsonExportConfig(candidate_id_prefix="vqe", n_qubits=n_qubits),
        )

    def test_every_optimizer_runs_and_lowers_the_energy(self) -> None:
        document = self._document()
        for optimizer in OPTIMIZERS:
            with self.subTest(optimizer=optimizer):
                events: list[dict] = []
                result = run_vqe(
                    document,
                    HamiltonianSpec("tfim"),
                    config=VQEConfig(steps=6, restarts=2, optimizer=optimizer, random_seed=3, record_every=3),
                    emit=events.append,
                )
                self.assertEqual(result["optimizer"], optimizer)
                self.assertEqual(result["config"]["optimizer"], optimizer)
                for restart in result["restarts"]:
                    self.assertEqual(len(restart["trajectory"]), 7)
                    self.assertGreaterEqual(restart["iterations"], 1)
                    self.assertLessEqual(restart["iterations"], 6)
                    self.assertGreaterEqual(restart["evaluations"], restart["iterations"])
                    self.assertLess(restart["best_energy"], restart["trajectory"][0])
                    self.assertGreaterEqual(restart["best_energy"], result["exact_energy"] - 1e-9)
                self.assertEqual(len(result["median_trajectory"]), 7)
                steps = [event for event in events if event["event_type"] == "vqe_step"]
                self.assertGreaterEqual(len(steps), 2)
                self.assertEqual(steps[-1]["step"], result["restarts"][-1]["iterations"])
                self.assertEqual(events[-1]["event_type"], "vqe_completed")
                self.assertIsNotNone(result["ground_state_fidelity"])

    def test_rotosolve_sweep_is_monotone_and_exact(self) -> None:
        import numpy as np

        from verfeinert.ansatz_analyzer.materialization import materialize_candidate
        from verfeinert.ansatz_analyzer.models import CandidateView

        document = self._document()
        spec = HamiltonianSpec("tfim")
        result = run_vqe(document, spec, config=VQEConfig(steps=4, restarts=1, optimizer="rotosolve", random_seed=1))
        trajectory = result["restarts"][0]["trajectory"]
        self.assertTrue(all(later <= earlier + 1e-9 for earlier, later in zip(trajectory, trajectory[1:])))
        materialized = materialize_candidate(CandidateView.from_document(document))
        energy = materialized.observable_qnode(spec.to_pennylane(3))
        fresh = float(energy(np.asarray(result["restarts"][0]["best_parameters"], dtype=float)))
        self.assertAlmostEqual(fresh, result["best_energy"], places=8)
        self.assertLess(result["best_normalized_error"], 0.05)

    def test_rotoselect_reports_generators_and_state_matches_selection(self) -> None:
        import numpy as np

        from verfeinert.ansatz_analyzer.materialization import materialize_candidate
        from verfeinert.ansatz_analyzer.models import CandidateView

        document = self._document()
        spec = HamiltonianSpec("heisenberg")
        result = run_vqe(document, spec, config=VQEConfig(steps=3, restarts=1, optimizer="rotoselect", random_seed=2))
        generators = result["selected_generators"]
        self.assertTrue(generators)
        for item in generators:
            self.assertIn(item["selected"], ("rx", "ry", "rz"))
            self.assertIn(item["original"], ("rx", "ry", "rz"))
            self.assertTrue(item["operation_ids"])
        self.assertEqual(result["changed_generators"], sum(1 for item in generators if item["selected"] != item["original"]))
        overrides = result["rotation_overrides"]
        self.assertEqual(set(overrides), {op for item in generators for op in item["operation_ids"]})
        materialized = materialize_candidate(CandidateView.from_document(document), rotation_overrides=overrides)
        energy = materialized.observable_qnode(spec.to_pennylane(3))
        fresh = float(energy(np.asarray(result["restarts"][0]["best_parameters"], dtype=float)))
        self.assertAlmostEqual(fresh, result["best_energy"], places=8)

    def test_optimizer_names_and_catalog(self) -> None:
        self.assertEqual(VQEConfig(optimizer="Nelder-Mead").optimizer, "nelder_mead")
        self.assertEqual(VQEConfig(optimizer="SGD").optimizer, "gradient_descent")
        self.assertEqual(VQEConfig(optimizer="L-BFGS-B").optimizer, "l_bfgs_b")
        self.assertEqual(VQEConfig.from_mapping({"optimizer": "rmsprop"}).learning_rate, 0.01)
        self.assertEqual(VQEConfig.from_mapping({"optimizer": "rmsprop", "learning_rate": 0.2}).learning_rate, 0.2)
        self.assertEqual(VQEConfig().to_dict()["optimizer_label"], "Adam")
        with self.assertRaises(ValueError):
            VQEConfig(optimizer="bfgs-of-doom")
        catalog = optimizer_catalog()
        self.assertEqual([item["key"] for item in catalog], list(OPTIMIZERS))
        self.assertTrue(all({"label", "family", "family_label", "uses_learning_rate", "description"} <= set(item) for item in catalog))
        self.assertEqual(build_catalog()["vqe_optimizers"][0]["key"], "adam")


class LiveServerTests(unittest.TestCase):
    def test_catalog_run_and_vqe_over_http(self) -> None:
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            catalog = self._get(f"{base}/api/catalog")
            self.assertEqual([item["kind"] for item in catalog["hamiltonians"]], ["local_x", "tfim", "heisenberg"])
            self.assertEqual(build_catalog()["protocols"]["paper"]["expressibility"]["n_pairs"], 10000)
            page = urllib.request.urlopen(f"{base}/", timeout=10).read().decode("utf-8")
            self.assertIn("Verfeinert", page)
            started = self._post(f"{base}/api/runs", {**FAST_CONFIG, "max_generations": 1, "template_ids": ["A04", "A10"]})
            run_id = started["run_id"]
            status = self._wait(f"{base}/api/runs/{run_id}", "completed")
            self.assertGreaterEqual(status["evaluated_count"], 2)
            stream = urllib.request.urlopen(f"{base}/api/runs/{run_id}/events", timeout=30).read().decode("utf-8")
            self.assertIn("event: run_started", stream)
            self.assertIn("event: run_completed", stream)
            self.assertTrue(stream.rstrip().endswith("data: {}"))
            best = status["leaderboard"][0]["candidate_id"]
            document = self._get(f"{base}/api/runs/{run_id}/candidates/{best}")
            self.assertEqual(document["candidate_id"], best)
            export = self._get(f"{base}/api/runs/{run_id}/export")
            self.assertIn(best, export["candidates"])
            self.assertIn("vqe_optimizers", catalog)
            vqe = self._post(f"{base}/api/runs/{run_id}/vqe", {"candidate_ids": [best], "steps": 5, "restarts": 1, "record_every": 5, "optimizer": "rotosolve"})
            self.assertEqual(vqe["config"]["vqe"]["optimizer"], "rotosolve")
            vqe_status = self._wait(f"{base}/api/vqe/{vqe['vqe_id']}", "completed")
            self.assertEqual(vqe_status["results"][0]["candidate_id"], best)
            self.assertEqual(vqe_status["results"][0]["optimizer_label"], "Rotosolve")
            missing = urllib.request.Request(f"{base}/api/runs/nope")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(missing, timeout=5)
        finally:
            server.shutdown()
            server.server_close()

    @staticmethod
    def _get(url: str) -> dict:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _post(url: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _wait(self, url: str, status: str, timeout: float = 120.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            payload = self._get(url)
            if payload["status"] == status:
                return payload
            if payload["status"] in {"failed", "cancelled"}:
                self.fail(f"job ended with status {payload['status']}: {payload}")
            time.sleep(0.2)
        self.fail(f"timed out waiting for {url} to reach {status}")


if __name__ == "__main__":
    unittest.main()

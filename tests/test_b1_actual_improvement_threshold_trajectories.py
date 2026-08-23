from __future__ import annotations

import hashlib
import importlib
import inspect
import unittest

from verfeinert.ansatz_evolver.policies import (
    StoppingPolicy,
    StoppingState,
    evaluate_stopping_conditions,
)
from verfeinert.ansatz_evolver.selection import ObjectiveSpec
from verfeinert.workflow.config import WorkflowConfig
from verfeinert.workflow.runner import _stopping_decision_for_generation


OBJECTIVES = (
    ObjectiveSpec("expressibility", "maximize"),
    ObjectiveSpec("trainability", "maximize"),
)


def _progress_module():
    # Deliberately imported lazily so every RED test states which missing
    # behavior it needs instead of failing test collection at module import.
    return importlib.import_module("verfeinert.ansatz_evolver.progress")


def _result(candidate_id: str, e: float, t: float, cost: float = 0.0) -> dict:
    # Canonical-enough AnalysisResult shape for the existing selection layer.
    # The progress implementation must delegate metric interpretation to the
    # established selection helpers rather than inventing scientific formulas.
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {
            "candidate_id": candidate_id,
            "structural_hash": hashlib.sha256(candidate_id.encode("utf-8")).hexdigest(),
        },
        "metrics": {
            "expressibility": e,
            "trainability": t,
            "cost_norm_reference": cost,
        },
        "status": "completed",
        "metadata": {},
    }


class B1ActualParetoImprovementTests(unittest.TestCase):
    def _progress(self, previous, current):
        module = _progress_module()
        fn = getattr(module, "accumulated_pareto_progress")
        return fn(
            previous_frontier=tuple(previous),
            candidate_results=tuple(current),
            objectives=OBJECTIVES,
        )

    def test_survivors_without_frontier_change_are_not_improvement(self):
        previous = (
            _result("left", 3.0, 1.0),
            _result("right", 1.0, 3.0),
        )
        current = (
            _result("dominated-but-can-exist-as-current-survivor", 1.0, 1.0),
        )
        progress = self._progress(previous, current)
        self.assertFalse(progress.improved)
        self.assertEqual(
            progress.previous_signature,
            progress.current_signature,
        )

    def test_strict_dominance_changes_accumulated_frontier(self):
        previous = (_result("old", 1.0, 1.0),)
        current = (_result("new", 2.0, 2.0),)
        progress = self._progress(previous, current)
        self.assertTrue(progress.improved)
        self.assertNotEqual(
            progress.previous_signature,
            progress.current_signature,
        )

    def test_internal_frontier_completion_is_improvement(self):
        previous = (
            _result("left", 3.0, 1.0),
            _result("right", 1.0, 3.0),
        )
        current = (_result("middle", 2.0, 2.0),)
        progress = self._progress(previous, current)
        self.assertTrue(progress.improved)
        self.assertIn((2.0, 2.0), progress.current_signature)

    def test_frontier_extension_is_improvement(self):
        previous = (
            _result("left", 3.0, 1.0),
            _result("right", 1.0, 3.0),
        )
        current = (_result("extension", 4.0, 0.8),)
        progress = self._progress(previous, current)
        self.assertTrue(progress.improved)
        self.assertIn((4.0, 0.8), progress.current_signature)

    def test_new_id_with_same_scientific_coordinates_is_not_improvement(self):
        previous = (_result("old-id", 2.0, 2.0),)
        current = (_result("new-id", 2.0, 2.0),)
        progress = self._progress(previous, current)
        self.assertFalse(progress.improved)
        self.assertEqual(
            progress.previous_signature,
            progress.current_signature,
        )

    def test_local_batch_improvement_does_not_override_accumulated_best(self):
        # F1 reached (3,3). A later batch may improve over a poor G2 point
        # but is still dominated by the accumulated best frontier.
        accumulated = (_result("g1-best", 3.0, 3.0),)
        current = (_result("g3-better-than-g2-only", 2.0, 2.0),)
        progress = self._progress(accumulated, current)
        self.assertFalse(progress.improved)
        self.assertEqual(
            progress.previous_signature,
            progress.current_signature,
        )



class B1FitnessImprovementTests(unittest.TestCase):
    def _progress(self, previous, current, *, direction="minimize", keep=1):
        module = _progress_module()
        fn = getattr(module, "accumulated_fitness_progress")
        return fn(
            previous_results=tuple(previous),
            candidate_results=tuple(current),
            metric_name="cost_norm_reference",
            direction=direction,
            keep=keep,
        )

    def test_fitness_survivor_that_does_not_improve_accumulated_best_is_not_progress(self):
        previous = (_result("best", 1.0, 1.0, cost=0.10),)
        current = (_result("worse-current-survivor", 2.0, 2.0, cost=0.20),)
        progress = self._progress(previous, current, direction="minimize")
        self.assertFalse(progress.improved)

    def test_fitness_improvement_uses_existing_metric_order(self):
        previous = (_result("old-best", 1.0, 1.0, cost=0.20),)
        current = (_result("new-best", 2.0, 2.0, cost=0.10),)
        progress = self._progress(previous, current, direction="minimize")
        self.assertTrue(progress.improved)


class B1RunnerSignalRemovalTests(unittest.TestCase):
    def test_runner_no_longer_equates_survivor_presence_with_improvement(self):
        import verfeinert.workflow.runner as runner_module

        source = inspect.getsource(runner_module.WorkflowRunner._run_evolution)
        self.assertNotIn(
            "strict_improvement=bool(selection.survivor_refs)",
            source,
        )


class B1ExplicitTrajectoryConfigTests(unittest.TestCase):
    def _config(self):
        return WorkflowConfig.from_mapping(
            {
                "run": {"run_id": "b1-red-config"},
                "paths": {"output_root": "/tmp/verfeinert-b1-red-config"},
                "workflow": {
                    "scientific_execution": ["evolve"],
                    "postprocessing": [],
                },
                "evolver": {
                    "selection_mode": "strict_pareto_feedback",
                    "objectives": [
                        {"name": "expressibility", "direction": "maximize"},
                        {"name": "trainability", "direction": "maximize"},
                    ],
                    "trajectory_thresholds": {
                        "metric_name": "cost_norm_reference",
                        "direction": "at_most",
                        "trajectories": {
                            "cost-1.0": 1.0,
                            "cost-0.2": 0.2,
                            "cost-0.1": 0.1,
                        },
                    },
                },
            }
        )

    def test_explicit_trajectory_names_and_values_round_trip(self):
        config = self._config()
        payload = config.evolver.to_dict()
        self.assertEqual(
            payload["trajectory_thresholds"],
            {
                "metric_name": "cost_norm_reference",
                "direction": "at_most",
                "trajectories": {
                    "cost-0.1": 0.1,
                    "cost-0.2": 0.2,
                    "cost-1.0": 1.0,
                },
            },
        )

    def test_trajectory_thresholds_do_not_overload_legacy_thresholds(self):
        config = self._config()
        self.assertEqual(dict(config.evolver.thresholds), {})
        self.assertTrue(config.evolver.trajectory_thresholds)


class B1ThresholdTrajectoryStateTests(unittest.TestCase):
    def _specs(self):
        module = _progress_module()
        build = getattr(module, "build_threshold_trajectory_specs")
        return build(
            metric_name="cost_norm_reference",
            direction="at_most",
            trajectories={
                "cost-1.0": 1.0,
                "cost-0.2": 0.2,
                "cost-0.1": 0.1,
            },
        )

    def test_g0_initializes_named_independent_frontiers_without_improvement(self):
        module = _progress_module()
        initialize = getattr(module, "initialize_threshold_trajectories")
        states = initialize(
            specs=self._specs(),
            analysis_results=(
                _result("a", 2.0, 2.0, cost=0.05),
                _result("b", 3.0, 1.0, cost=0.15),
                _result("c", 1.0, 3.0, cost=0.8),
            ),
            objectives=OBJECTIVES,
        )
        self.assertEqual(
            tuple(sorted(states)),
            ("cost-0.1", "cost-0.2", "cost-1.0"),
        )
        for state in states.values():
            self.assertFalse(state.improved)
            self.assertEqual(state.generation_index, 0)

    def test_each_threshold_has_own_parent_and_archive_membership(self):
        module = _progress_module()
        initialize = getattr(module, "initialize_threshold_trajectories")
        states = initialize(
            specs=self._specs(),
            analysis_results=(
                _result("cheap", 2.0, 2.0, cost=0.05),
                _result("medium", 3.0, 1.0, cost=0.15),
                _result("expensive", 1.0, 3.0, cost=0.8),
            ),
            objectives=OBJECTIVES,
        )
        ids = lambda refs: tuple(ref.candidate_id for ref in refs)
        self.assertEqual(ids(states["cost-0.1"].archive_refs), ("cheap",))
        self.assertEqual(
            set(ids(states["cost-0.2"].archive_refs)),
            {"cheap", "medium"},
        )
        self.assertEqual(
            set(ids(states["cost-1.0"].archive_refs)),
            {"cheap", "medium", "expensive"},
        )
        self.assertNotEqual(
            ids(states["cost-0.1"].parent_refs),
            ids(states["cost-1.0"].parent_refs),
        )

    def test_exhausted_trajectory_is_excluded_but_other_parents_continue(self):
        module = _progress_module()
        active = getattr(module, "active_parent_refs_by_trajectory")
        states = {
            "cost-0.1": {
                "parent_refs": [{"candidate_id": "cheap-parent"}],
                "exhausted": True,
            },
            "cost-0.2": {
                "parent_refs": [{"candidate_id": "medium-parent"}],
                "exhausted": False,
            },
            "cost-1.0": {
                "parent_refs": [{"candidate_id": "wide-parent"}],
                "exhausted": False,
            },
        }
        parents = active(states)
        self.assertNotIn("cost-0.1", parents)
        self.assertEqual(
            tuple(ref.candidate_id for ref in parents["cost-0.2"]),
            ("medium-parent",),
        )
        self.assertEqual(
            tuple(ref.candidate_id for ref in parents["cost-1.0"]),
            ("wide-parent",),
        )

    def test_threshold_trajectory_payload_round_trip_is_lossless(self):
        module = _progress_module()
        initialize = getattr(module, "initialize_threshold_trajectories")
        serialize = getattr(module, "threshold_trajectories_to_mapping")
        restore = getattr(module, "threshold_trajectories_from_mapping")

        states = initialize(
            specs=self._specs(),
            analysis_results=(
                _result("cheap", 2.0, 2.0, cost=0.05),
                _result("medium", 3.0, 1.0, cost=0.15),
            ),
            objectives=OBJECTIVES,
        )
        payload = serialize(states)
        restored = restore(payload)
        self.assertEqual(serialize(restored), payload)


class B1StoppingBridgeTests(unittest.TestCase):
    def test_workflow_stopping_bridge_accepts_threshold_improvements(self):
        sig = inspect.signature(_stopping_decision_for_generation)
        self.assertIn("threshold_improvements", sig.parameters)

    def test_one_exhausted_threshold_does_not_stop_other_active_trajectory(self):
        # Engine behavior already exists. This test guards the exact global rule.
        decision = evaluate_stopping_conditions(
            generation_index=1,
            policy=StoppingPolicy(max_generations=10, patience=0),
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=1,
            strict_improvement=True,
            patience_state=StoppingState(),
            threshold_improvements={
                "cost-0.1": False,
                "cost-0.2": True,
            },
        )
        self.assertFalse(decision.should_stop)
        states = decision.metadata["stopping_state"]["threshold_states"]
        self.assertTrue(states["cost-0.1"]["exhausted"])
        self.assertFalse(states["cost-0.2"]["exhausted"])

    def test_improvement_resets_only_its_own_threshold_patience(self):
        policy = StoppingPolicy(max_generations=10, patience=1)
        first = evaluate_stopping_conditions(
            generation_index=1,
            policy=policy,
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=2,
            strict_improvement=False,
            threshold_improvements={
                "cost-0.1": False,
                "cost-0.2": False,
            },
        )
        second = evaluate_stopping_conditions(
            generation_index=2,
            policy=policy,
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=1,
            strict_improvement=True,
            patience_state=first.metadata["stopping_state"],
            threshold_improvements={
                "cost-0.1": False,
                "cost-0.2": True,
            },
        )
        states = second.metadata["stopping_state"]["threshold_states"]
        self.assertEqual(states["cost-0.1"]["consecutive_no_improvement"], 2)
        self.assertTrue(states["cost-0.1"]["exhausted"])
        self.assertEqual(states["cost-0.2"]["consecutive_no_improvement"], 0)
        self.assertFalse(states["cost-0.2"]["exhausted"])

    def test_all_thresholds_exhausted_stops_global_run(self):
        decision = evaluate_stopping_conditions(
            generation_index=1,
            policy=StoppingPolicy(max_generations=10, patience=0),
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=1,
            strict_improvement=False,
            threshold_improvements={
                "cost-0.1": False,
                "cost-0.2": False,
            },
        )
        self.assertTrue(decision.should_stop)
        self.assertEqual(decision.reason, "patience_exhausted")


if __name__ == "__main__":
    unittest.main()

"""Tests for evolver-owned generation state transitions."""

from __future__ import annotations

import hashlib
import unittest

from verfeinert.ansatz_evolver import (
    CandidateRef,
    EvolutionStateMachine,
    EvolutionStateMachineError,
    build_analyzed_generation_record,
    evolution_execution_metadata,
)
from verfeinert.ansatz_evolver.selection import select_by_fitness
from verfeinert.ansatz_evolver.validation import validate_analysis_result_document


CREATED_AT = "2026-08-21T00:00:00Z"
CONFIGURATION = {
    "random_seed": 11,
    "execution": {"mode": "sequential"},
    "mutation_policy": {"policy_id": "test-mutation"},
    "selection_policy": {"policy_id": "fitness"},
}


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _candidate_ref(candidate_id: str) -> CandidateRef:
    return CandidateRef(candidate_id, structural_hash=_hash(candidate_id))


def _analysis_result(candidate_id: str, structural_cost: float) -> dict:
    return validate_analysis_result_document(
        {
            "schema_version": "verfeinert.analysis_result.v1",
            "analysis_result_id": f"analysis-{candidate_id}",
            "candidate_ref": {
                "candidate_id": candidate_id,
                "structural_hash": _hash(candidate_id),
            },
            "metrics": [
                {
                    "metric_id": f"metric-structural-cost-{candidate_id}",
                    "name": "structural_cost",
                    "status": "computed",
                    "value": structural_cost,
                },
            ],
            "cost": {
                "structural_cost": structural_cost,
                "operation_count": 1,
                "two_qubit_operation_count": 0,
                "parameter_count": 1,
            },
            "classifications": [],
            "provenance": {
                "created_at": CREATED_AT,
                "analyzer": "state-machine-test",
                "software_version": "test",
                "git_commit": None,
                "execution": {"qnodes_executed": False},
            },
        },
    )


def _generation():
    results = (
        _analysis_result("candidate-a", 0.1),
        _analysis_result("candidate-b", 0.3),
    )
    refs = tuple(_candidate_ref(result["candidate_ref"]["candidate_id"]) for result in results)
    selection = select_by_fitness(results, metric_name="structural_cost", keep=1)
    return build_analyzed_generation_record(
        generation_index=0,
        candidate_refs=refs,
        analysis_result_documents=results,
        selection=selection,
        analysis_uris={
            "analysis-candidate-a": "analysis/candidate-a.json",
            "analysis-candidate-b": "analysis/candidate-b.json",
        },
        generation_configuration={"workflow_run_id": "state-machine-test"},
    )


class EvolverStateMachineTests(unittest.TestCase):
    def test_analyzed_generation_record_ingests_analysis_and_selection(self) -> None:
        generation = _generation()

        self.assertEqual(generation.generation_index, 0)
        self.assertEqual([ref.candidate_id for ref in generation.survivor_refs], ["candidate-a"])
        self.assertEqual(len(generation.analysis_result_refs), 2)
        self.assertEqual(
            generation.analysis_result_refs[0].analysis_result_uri,
            "analysis/candidate-a.json",
        )
        self.assertIn("selection", generation.configuration)
        self.assertEqual(
            [event.event_type for event in generation.events],
            [
                "evolver_generation_analyzed",
                "evolver_selection_completed",
            ],
        )

    def test_state_machine_plans_appends_and_completes_generations(self) -> None:
        machine = EvolutionStateMachine.start(
            evolution_run_id="state-machine-run",
            configuration=CONFIGURATION,
            created_at=CREATED_AT,
            git_commit=None,
        )

        planned = machine.plan_generation()
        candidates_generated = planned.record_candidates_generated()
        analysis_pending = candidates_generated.request_analysis()
        analysis_complete = analysis_pending.record_analysis_complete()
        selection_complete = analysis_complete.record_selection_complete()
        checkpointed = selection_complete.append_generation(_generation())
        completed = checkpointed.complete(metadata={"final": "ok"})

        self.assertEqual(planned.lifecycle_state, "generation_planned")
        self.assertEqual(planned.pending_generation_index, 0)
        self.assertEqual(candidates_generated.lifecycle_state, "candidates_generated")
        self.assertEqual(analysis_pending.lifecycle_state, "analysis_pending")
        self.assertEqual(analysis_complete.lifecycle_state, "analysis_complete")
        self.assertEqual(selection_complete.lifecycle_state, "selection_complete")
        self.assertEqual(checkpointed.lifecycle_state, "checkpointed")
        self.assertEqual(checkpointed.run_state.execution_metadata["generation_count"], 1)
        self.assertEqual(completed.lifecycle_state, "completed")
        self.assertEqual(completed.run_state.status, "completed")
        self.assertEqual(completed.run_state.metadata, {"final": "ok"})

    def test_state_machine_rejects_illegal_transitions(self) -> None:
        machine = EvolutionStateMachine.start(
            evolution_run_id="state-machine-run",
            configuration=CONFIGURATION,
            created_at=CREATED_AT,
            git_commit=None,
        )
        generation = _generation()

        with self.assertRaisesRegex(EvolutionStateMachineError, "generation_index must be 0"):
            machine.append_generation(
                build_analyzed_generation_record(
                    generation_index=1,
                    candidate_refs=generation.candidate_refs,
                    analysis_result_documents=(
                        _analysis_result("candidate-a", 0.1),
                        _analysis_result("candidate-b", 0.3),
                    ),
                    selection=select_by_fitness(
                        (
                            _analysis_result("candidate-a", 0.1),
                            _analysis_result("candidate-b", 0.3),
                        ),
                        metric_name="structural_cost",
                        keep=1,
                    ),
                ),
            )
        with self.assertRaisesRegex(EvolutionStateMachineError, "planned generation pending"):
            machine.plan_generation().complete()
        with self.assertRaisesRegex(EvolutionStateMachineError, "cannot transition"):
            machine.plan_generation().request_analysis()
        completed = machine.append_generation(generation).complete()
        with self.assertRaisesRegex(EvolutionStateMachineError, "terminal state"):
            completed.append_generation(generation)
        resumed_terminal = EvolutionStateMachine.from_run_state(completed.run_state)
        self.assertEqual(resumed_terminal.lifecycle_state, "completed")
        with self.assertRaisesRegex(EvolutionStateMachineError, "terminal state"):
            resumed_terminal.append_generation(generation)

    def test_state_machine_terminal_failure_and_cancel_statuses(self) -> None:
        machine = EvolutionStateMachine.start(
            evolution_run_id="state-machine-run",
            configuration=CONFIGURATION,
            created_at=CREATED_AT,
            git_commit=None,
        )

        failed = machine.fail(metadata={"reason": "analysis_failed"})
        cancelled = machine.cancel(metadata={"reason": "user_cancelled"})

        self.assertEqual(failed.run_state.status, "failed")
        self.assertEqual(failed.lifecycle_state, "failed")
        self.assertEqual(cancelled.run_state.status, "cancelled")
        self.assertEqual(cancelled.lifecycle_state, "cancelled")

    def test_state_machine_serialization_is_deterministic(self) -> None:
        generation = _generation()

        def build_document():
            return (
                EvolutionStateMachine.start(
                    evolution_run_id="deterministic-run",
                    configuration=CONFIGURATION,
                    metadata={"relationship": "origin"},
                    created_at=CREATED_AT,
                    git_commit=None,
                )
                .append_generation(generation)
                .complete(metadata={"relationship": "origin"})
                .run_state.to_dict()
            )

        self.assertEqual(build_document(), build_document())
        self.assertEqual(evolution_execution_metadata((generation,))["generation_count"], 1)


if __name__ == "__main__":
    unittest.main()

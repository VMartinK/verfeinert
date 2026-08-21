"""Selection, stopping, pipeline, and exporter tests for ansatz_evolver."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_evolver import (
    CandidateRef,
    EvolutionPipelineState,
    EvolverConfig,
    GenerationRecord,
)
from verfeinert.ansatz_evolver.evaluation import ingest_analysis_results
from verfeinert.ansatz_evolver.exporters import (
    export_evolution_run_json,
    write_evolution_run_json,
)
from verfeinert.ansatz_evolver.policies import (
    StoppingPolicy,
    StoppingState,
    evaluate_stopping_conditions,
)
from verfeinert.ansatz_evolver.selection import (
    ObjectiveSpec,
    ThresholdRule,
    dominates,
    non_dominated_ranks,
    select_by_fitness,
    select_by_thresholds,
    select_multithreshold,
    select_pareto_front,
    select_strict_pareto,
)
from verfeinert.ansatz_evolver.validation import validate_analysis_result_document


CREATED_AT = "2026-08-04T00:00:00Z"


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _analysis_result(candidate_id: str, structural_cost: float, expressibility: float) -> dict:
    document = {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {
            "candidate_id": candidate_id,
            "structural_hash": _hash(candidate_id[:1] or "a"),
        },
        "metrics": [
            {
                "metric_id": f"metric-cost-{candidate_id}",
                "name": "structural_cost",
                "status": "computed",
                "value": structural_cost,
            },
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": expressibility,
            },
        ],
        "cost": {
            "structural_cost": structural_cost,
            "operation_count": int(structural_cost * 10),
            "two_qubit_operation_count": 1,
            "parameter_count": 2,
        },
        "classifications": [],
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "schema-test",
            "software_version": "0.0.0",
            "git_commit": None,
            "execution": {"qnodes_executed": False},
        },
    }
    return validate_analysis_result_document(document)


class EvolverSelectionExportTests(unittest.TestCase):
    def test_fitness_and_threshold_selection(self) -> None:
        results = (
            _analysis_result("candidate-a", 0.3, 0.2),
            _analysis_result("candidate-b", 0.1, 0.5),
            _analysis_result("candidate-c", 0.2, 0.4),
        )

        fitness = select_by_fitness(results, metric_name="structural_cost", keep=2)
        threshold = select_by_thresholds(
            results,
            rules=(ThresholdRule("structural_cost", 0.2),),
        )
        multi = select_multithreshold(
            results,
            thresholds={"structural_cost": 0.2, "expressibility": 0.5},
        )

        self.assertEqual([ref.candidate_id for ref in fitness.survivor_refs], ["candidate-b", "candidate-c"])
        self.assertEqual([ref.candidate_id for ref in threshold.survivor_refs], ["candidate-b", "candidate-c"])
        self.assertEqual([ref.candidate_id for ref in multi.survivor_refs], ["candidate-b", "candidate-c"])

    def test_pareto_and_strict_pareto_selection(self) -> None:
        result_a = _analysis_result("candidate-a", 0.1, 0.8)
        result_b = _analysis_result("candidate-b", 0.2, 0.9)
        result_c = _analysis_result("candidate-c", 0.4, 0.2)
        objectives = (
            ObjectiveSpec("structural_cost", "minimize"),
            ObjectiveSpec("expressibility", "maximize"),
        )

        self.assertTrue(dominates(result_a, result_c, objectives))
        self.assertFalse(dominates(result_a, result_b, objectives))

        ranks = non_dominated_ranks((result_a, result_b, result_c), objectives)
        pareto = select_pareto_front((result_a, result_b, result_c), objectives=objectives)
        strict = select_strict_pareto(
            (result_a, result_b, result_c),
            objectives=objectives,
            reference_results=(_analysis_result("reference-a", 0.3, 0.3),),
        )

        self.assertEqual(ranks["candidate-a"], 0)
        self.assertEqual(ranks["candidate-b"], 0)
        self.assertEqual(ranks["candidate-c"], 1)
        self.assertEqual([ref.candidate_id for ref in pareto.survivor_refs], ["candidate-a", "candidate-b"])
        self.assertEqual([ref.candidate_id for ref in strict.survivor_refs], ["candidate-a", "candidate-b"])

    def test_stopping_conditions_cover_terminal_states(self) -> None:
        policy = StoppingPolicy(max_generations=2)

        self.assertEqual(
            evaluate_stopping_conditions(
                generation_index=0,
                policy=policy,
                candidate_count=0,
                analysis_result_count=0,
                survivor_count=0,
            ).reason,
            "no_candidates",
        )
        self.assertEqual(
            evaluate_stopping_conditions(
                generation_index=1,
                policy=policy,
                candidate_count=1,
                analysis_result_count=1,
                survivor_count=1,
                duplicate_only=True,
            ).reason,
            "duplicate_only_generation",
        )
        self.assertEqual(
            evaluate_stopping_conditions(
                generation_index=2,
                policy=policy,
                candidate_count=1,
                analysis_result_count=1,
                survivor_count=1,
            ).reason,
            "max_generations_reached",
        )

    def test_stopping_conditions_cover_failure_cancellation_and_empty_results(self) -> None:
        policy = StoppingPolicy(max_generations=5)

        cases = (
            (
                {"failed": True, "candidate_count": 1, "analysis_result_count": 1, "survivor_count": 1},
                "failure_reported",
                "failed",
            ),
            (
                {"cancelled": True, "candidate_count": 1, "analysis_result_count": 1, "survivor_count": 1},
                "cancelled",
                "cancelled",
            ),
            (
                {"candidate_count": 1, "analysis_result_count": 0, "survivor_count": 0},
                "no_analysis_results",
                "failed",
            ),
            (
                {"candidate_count": 1, "analysis_result_count": 1, "survivor_count": 0},
                "no_survivors",
                "completed",
            ),
            (
                {
                    "candidate_count": 1,
                    "analysis_result_count": 1,
                    "survivor_count": 1,
                    "execution_budget_exhausted": True,
                },
                "execution_budget_exhausted",
                "completed",
            ),
        )

        for kwargs, reason, status in cases:
            with self.subTest(reason=reason):
                decision = evaluate_stopping_conditions(
                    generation_index=0,
                    policy=policy,
                    **kwargs,
                )
                self.assertTrue(decision.should_stop)
                self.assertEqual(decision.reason, reason)
                self.assertEqual(decision.status, status)
                self.assertEqual(decision.metadata["generation_index"], 0)

    def test_patience_none_preserves_immediate_no_improvement_compatibility(self) -> None:
        decision = evaluate_stopping_conditions(
            generation_index=0,
            policy=StoppingPolicy(max_generations=5, patience=None),
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=False,
        )

        self.assertTrue(decision.should_stop)
        self.assertEqual(decision.reason, "no_strict_improvement")
        self.assertFalse(decision.metadata["patience_enabled"])

    def test_patience_zero_stops_on_first_non_improvement(self) -> None:
        decision = evaluate_stopping_conditions(
            generation_index=0,
            policy=StoppingPolicy(max_generations=5, patience=0),
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=False,
        )

        self.assertTrue(decision.should_stop)
        self.assertEqual(decision.reason, "patience_exhausted")
        self.assertEqual(
            decision.metadata["stopping_state"]["consecutive_no_improvement"],
            1,
        )

    def test_patience_allows_configured_consecutive_non_improvements(self) -> None:
        policy = StoppingPolicy(max_generations=5, patience=1)
        first = evaluate_stopping_conditions(
            generation_index=0,
            policy=policy,
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=False,
        )
        second = evaluate_stopping_conditions(
            generation_index=1,
            policy=policy,
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=False,
            patience_state=first.metadata["stopping_state"],
        )

        self.assertFalse(first.should_stop)
        self.assertEqual(first.reason, "continue")
        self.assertEqual(first.metadata["stopping_state"]["consecutive_no_improvement"], 1)
        self.assertTrue(second.should_stop)
        self.assertEqual(second.reason, "patience_exhausted")
        self.assertEqual(second.metadata["stopping_state"]["consecutive_no_improvement"], 2)

    def test_improvement_resets_patience_state(self) -> None:
        policy = StoppingPolicy(max_generations=5, patience=2)
        first = evaluate_stopping_conditions(
            generation_index=0,
            policy=policy,
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=False,
        )
        reset = evaluate_stopping_conditions(
            generation_index=1,
            policy=policy,
            candidate_count=1,
            analysis_result_count=1,
            survivor_count=1,
            strict_improvement=True,
            patience_state=first.metadata["stopping_state"],
        )

        self.assertFalse(reset.should_stop)
        self.assertEqual(reset.metadata["stopping_state"]["consecutive_no_improvement"], 0)
        self.assertEqual(reset.metadata["stopping_state"]["last_improvement_generation"], 1)

    def test_independent_threshold_patience_state_serializes_for_resume(self) -> None:
        policy = StoppingPolicy(max_generations=5, patience=0)
        first = evaluate_stopping_conditions(
            generation_index=0,
            policy=policy,
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=1,
            strict_improvement=False,
            threshold_improvements={"cost-0.2": False, "cost-1.0": True},
        )
        resumed_state = StoppingState.from_mapping(first.metadata["stopping_state"])
        second = evaluate_stopping_conditions(
            generation_index=1,
            policy=policy,
            candidate_count=2,
            analysis_result_count=2,
            survivor_count=1,
            strict_improvement=False,
            threshold_improvements={"cost-0.2": False, "cost-1.0": False},
            patience_state=resumed_state,
        )

        self.assertFalse(first.should_stop)
        threshold_states = first.metadata["stopping_state"]["threshold_states"]
        self.assertTrue(threshold_states["cost-0.2"]["exhausted"])
        self.assertFalse(threshold_states["cost-1.0"]["exhausted"])
        self.assertEqual(resumed_state.to_dict(), first.metadata["stopping_state"])
        self.assertTrue(second.should_stop)
        self.assertEqual(second.reason, "patience_exhausted")
        self.assertEqual(
            second.metadata["exhausted_thresholds"],
            ["cost-0.2", "cost-1.0"],
        )

    def test_pipeline_state_exports_valid_evolution_run(self) -> None:
        result = _analysis_result("candidate-a", 0.1, 0.8)
        ref = CandidateRef("candidate-a", structural_hash=result["candidate_ref"]["structural_hash"])
        ingestion = ingest_analysis_results((ref,), (result,))
        generation = GenerationRecord(
            generation_index=0,
            candidate_refs=(ref,),
            survivor_refs=(ref,),
            archive_refs=(ref,),
            analysis_result_refs=ingestion.analysis_result_refs,
        )

        with TemporaryDirectory() as temp_dir:
            config = EvolverConfig(
                run_id="pipeline-run",
                output_root=Path(temp_dir) / "outputs",
                random_seed=7,
            )
            state = EvolutionPipelineState(
                config=config,
                status="completed",
                generations=(generation,),
            ).to_run_state()
            document = export_evolution_run_json(state)
            path = write_evolution_run_json(state, output_root=Path(temp_dir) / "exports")

            self.assertEqual(document["schema_version"], "verfeinert.evolution_run.v1")
            self.assertTrue(path.is_file())
            self.assertTrue(path.resolve().is_relative_to((Path(temp_dir) / "exports").resolve()))
            self.assertTrue(document["run_metadata"]["execution"]["analysis_results_ingested"])
            self.assertFalse(document["run_metadata"]["execution"]["evolver_executed_metrics"])


if __name__ == "__main__":
    unittest.main()

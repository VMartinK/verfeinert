"""Population, mutation, factory, and evaluation-boundary tests."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from verfeinert.ansatz_evolver import (
    CandidateRef,
    EvolutionEvent,
    GenerationRecord,
    produce_candidate_from_request,
    validate_analysis_result_document,
)
from verfeinert.ansatz_evolver.evaluation import AnalysisRequest, ingest_analysis_results
from verfeinert.ansatz_evolver.mutation import (
    MutationPolicy,
    MutationRecipe,
    MutationSchedule,
    build_mutation_requests,
)
from verfeinert.ansatz_evolver.population import (
    PopulationSnapshot,
    deduplicate_candidate_refs,
)
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    build_sanz19_candidate_record,
    export_candidate_json,
    remove_first_gate_on_wire,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-04T00:00:00Z"


def _generator_candidate_record() -> dict:
    return build_sanz19_candidate_record("A02", 1, n_qubits=4)


def _candidate_json(candidate_id: str = "parent-001") -> dict:
    return export_candidate_json(
        _generator_candidate_record(),
        candidate_id=candidate_id,
        config=CandidateJsonExportConfig(
            created_at=CREATED_AT,
            source_kind="template",
            n_qubits=4,
            git_commit=None,
            discover_git_commit=False,
        ),
    )


def _analysis_result(candidate: dict, result_id: str, structural_cost: float) -> dict:
    document = {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": result_id,
        "candidate_ref": {
            "candidate_id": candidate["candidate_id"],
            "structural_hash": candidate["identity"]["structural_hash"],
        },
        "metrics": [
            {
                "metric_id": f"{result_id}-structural-cost",
                "name": "structural_cost",
                "status": "computed",
                "value": structural_cost,
            }
        ],
        "cost": {
            "structural_cost": structural_cost,
            "operation_count": len(candidate["circuit"]["operations"]),
            "two_qubit_operation_count": sum(
                1 for operation in candidate["circuit"]["operations"] if len(operation["qubits"]) == 2
            ),
            "parameter_count": len(candidate["circuit"]["parameters"]),
        },
        "classifications": [],
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "schema-test",
            "software_version": "0.0.0",
            "git_commit": None,
            "execution": {
                "qnodes_executed": False,
                "expensive_metrics_executed": False,
            },
        },
    }
    return validate_analysis_result_document(document)


class EvolverPopulationMutationEvaluationTests(unittest.TestCase):
    def test_population_snapshot_and_deduplication_preserve_order(self) -> None:
        candidate = _candidate_json()
        ref_a = CandidateRef.from_candidate_document(candidate, role="candidate")
        ref_b = CandidateRef(
            candidate_id="duplicate-structural",
            structural_hash=ref_a.structural_hash,
            lineage_hash=ref_a.lineage_hash,
        )
        snapshot = PopulationSnapshot("population-001", 0, "initial", (ref_a, ref_b))

        kept, report = deduplicate_candidate_refs(snapshot.candidate_refs)

        self.assertEqual([ref.candidate_id for ref in kept], [ref_a.candidate_id])
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual(report.removed_candidate_ids, (ref_b.candidate_id,))
        self.assertEqual(snapshot.to_generation_record().candidate_refs, snapshot.candidate_refs)

    def test_mutation_schedule_and_requests_are_deterministic(self) -> None:
        parent = CandidateRef("parent-001", structural_hash="a" * 64, metadata={"root_candidate_id": "root-001"})
        policy = MutationPolicy(
            "policy-001",
            (
                MutationRecipe("recipe-insert", "insert"),
                MutationRecipe("recipe-remove", "remove"),
            ),
            variants_per_parent=3,
        )
        schedule = MutationSchedule("schedule-001", policy)

        requests = build_mutation_requests((parent,), generation_index=1, policy=schedule.policy_for_generation(1))
        ids_again = [
            request.request_id
            for request in build_mutation_requests((parent,), generation_index=1, policy=policy)
        ]

        self.assertEqual([request.request_id for request in requests], ids_again)
        self.assertEqual([request.mutation_type for request in requests], ["insert", "remove", "insert"])
        self.assertEqual(requests[0].root_candidate_id, "root-001")

    def test_public_candidate_factory_boundary_validates_lineage(self) -> None:
        parent_record = _generator_candidate_record()
        parent_candidate = _candidate_json("parent-001")
        parent_ref = CandidateRef.from_candidate_document(parent_candidate, metadata={"root_candidate_id": "parent-001"})
        policy = MutationPolicy("policy-remove", (MutationRecipe("recipe-remove", "remove"),))
        request = build_mutation_requests((parent_ref,), generation_index=1, policy=policy)[0]

        def factory(mutation_request, _parent_candidate):
            mutation = remove_first_gate_on_wire(parent_record["operations"], wire=0)
            child_record = {
                **parent_record,
                **mutation,
                "circuit_id": "child-001",
                "parent_circuit_id": parent_record["circuit_id"],
                "root_circuit_id": parent_record["circuit_id"],
                "generation_index": mutation_request.generation_index,
                "mutation_type": mutation_request.mutation_type,
                "mutation_id": "mutation-001",
            }
            return export_candidate_json(
                child_record,
                candidate_id="child-001",
                id_map={parent_record["circuit_id"]: "parent-001"},
                config=CandidateJsonExportConfig(
                    created_at=CREATED_AT,
                    source_kind="mutation",
                    n_qubits=4,
                    git_commit=None,
                    discover_git_commit=False,
                ),
            )

        child = produce_candidate_from_request(request, parent_candidate, factory)

        self.assertEqual(child["lineage"]["parent_candidate_id"], "parent-001")
        self.assertEqual(child["lineage"]["generation"], 1)
        self.assertEqual(child["lineage"]["mutation"]["type"], "remove")

    def test_analysis_request_and_ingestion_link_results_to_candidates(self) -> None:
        candidate = _candidate_json()
        ref = CandidateRef.from_candidate_document(candidate)
        request = AnalysisRequest("analysis-request-001", (ref,), requested_metrics=("structural_cost",))
        result = _analysis_result(candidate, "analysis-result-001", 0.25)

        ingestion = ingest_analysis_results(
            request.candidate_refs,
            (result,),
            uri_by_analysis_result_id={"analysis-result-001": "relative://analysis/analysis-result-001.json"},
        )

        self.assertEqual(ingestion.linked_candidate_ids, (candidate["candidate_id"],))
        self.assertEqual(ingestion.missing_candidate_ids, ())
        self.assertEqual(ingestion.unexpected_candidate_ids, ())
        self.assertEqual(ingestion.analysis_result_refs[0].candidate_id, candidate["candidate_id"])

    def test_generation_record_preserves_analysis_refs_and_events(self) -> None:
        candidate = _candidate_json()
        ref = CandidateRef.from_candidate_document(candidate)
        result = _analysis_result(candidate, "analysis-result-001", 0.25)
        ingestion = ingest_analysis_results((ref,), (result,))
        generation = GenerationRecord(
            generation_index=1,
            parent_refs=(ref,),
            candidate_refs=(ref,),
            analysis_result_refs=ingestion.analysis_result_refs,
            survivor_refs=(ref,),
            rejected_refs=(),
            archive_refs=(ref,),
            events=(EvolutionEvent("analysis_result_available", analysis_result_id="analysis-result-001"),),
        )

        document = generation.to_dict()

        self.assertEqual(document["analysis_result_refs"][0]["analysis_result_id"], "analysis-result-001")
        self.assertEqual(document["events"][0]["event_type"], "analysis_result_available")


if __name__ == "__main__":
    unittest.main()

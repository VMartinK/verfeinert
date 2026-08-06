"""End-to-end JSON workflow validation across generator, analyzer, and evolver."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalysisResultCollection,
    AnalyzerConfig,
    StructuralCostConfig,
    validate_analysis_result_document,
)
from verfeinert.ansatz_evolver import (
    CandidateRef,
    EvolutionEvent,
    EvolutionRunState,
    GenerationRecord,
    validate_evolution_run_document,
    validate_staged_package_document,
    write_evolution_run_json,
)
from verfeinert.ansatz_evolver.evaluation import ingest_analysis_results
from verfeinert.ansatz_evolver.selection import select_by_fitness
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    StagedPackageJsonExportConfig,
    build_sanz19_candidate_records,
    write_staged_package_json,
)


CREATED_AT = "2026-08-06T00:00:00Z"


class EndToEndWorkflowTests(unittest.TestCase):
    def test_generator_analyzer_evolver_json_flow(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            records = build_sanz19_candidate_records(("A02",), (1, 2), n_qubits=4)
            staged = write_staged_package_json(
                records,
                config=StagedPackageJsonExportConfig(
                    package_id="e2e-candidates",
                    output_root=root / "generated",
                    created_at=CREATED_AT,
                    git_commit=None,
                    discover_git_commit=False,
                    candidate_export=CandidateJsonExportConfig(
                        candidate_id_prefix="e2e",
                        n_qubits=4,
                        created_at=CREATED_AT,
                        git_commit=None,
                        discover_git_commit=False,
                    ),
                ),
            )

            self.assertIsNotNone(staged.staged_package_path)
            package = validate_staged_package_document(staged.package)
            candidate_ids = tuple(candidate["candidate_id"] for candidate in package["candidates"])

            analyzer_config = AnalyzerConfig(
                run_id="e2e-analysis",
                input_roots=(staged.package_root,),
                output_root=root / "analysis",
                selected_metrics=("structural_cost",),
                structural_cost=StructuralCostConfig(
                    reference_id="e2e-candidate-set",
                    reference_bounds={
                        "parameter_count": {"min": 1, "max": 32},
                        "depth": {"min": 1, "max": 64},
                        "two_qubit_operation_count": {"min": 0, "max": 16},
                    },
                ),
            )
            analysis_paths = tuple(
                AnalysisPipeline(analyzer_config).run_and_write(staged.staged_package_path),
            )
            collection = AnalysisResultCollection.from_sources((root / "analysis" / "e2e-analysis",))

            self.assertEqual(collection.candidate_ids, candidate_ids)
            for path in analysis_paths:
                validate_analysis_result_document(json.loads(path.read_text(encoding="utf-8")))

            candidate_refs = tuple(
                CandidateRef.from_candidate_document(candidate)
                for candidate in package["candidates"]
            )
            ingestion = ingest_analysis_results(candidate_refs, collection.documents)
            selection = select_by_fitness(
                collection.documents,
                metric_name="structural_cost",
                keep=1,
                policy_id="e2e-min-cost",
            )
            generation = GenerationRecord(
                generation_index=0,
                candidate_refs=candidate_refs,
                survivor_refs=selection.survivor_refs,
                rejected_refs=selection.rejected_refs,
                archive_refs=selection.survivor_refs,
                analysis_result_refs=ingestion.analysis_result_refs,
                events=(
                    EvolutionEvent(
                        event_type="e2e_workflow_validated",
                        status="completed",
                        metadata={"candidate_ids": list(candidate_ids)},
                    ),
                ),
            )
            state = EvolutionRunState(
                evolution_run_id="e2e-workflow",
                status="completed",
                configuration={
                    "random_seed": 7,
                    "execution": {"mode": "sequential"},
                    "mutation_policy": {"mode": "none"},
                    "selection_policy": {"policy_id": "e2e-min-cost"},
                    "stopping_policy": {"max_generations": 1},
                },
                generations=(generation,),
                provenance={
                    "created_at": CREATED_AT,
                    "source": "test_end_to_end_workflow",
                    "input_hashes": {},
                },
                created_at=CREATED_AT,
                git_commit=None,
                execution_metadata={
                    "analysis_requested": True,
                    "analysis_results_ingested": True,
                    "selection_executed": True,
                },
            )
            evolution_path = write_evolution_run_json(
                state,
                output_root=root / "evolution",
                input_roots=(staged.package_root, root / "analysis"),
            )
            evolution = validate_evolution_run_document(json.loads(evolution_path.read_text(encoding="utf-8")))

            self.assertEqual(
                tuple(ref["candidate_id"] for ref in evolution["generations"][0]["candidate_refs"]),
                candidate_ids,
            )
            self.assertEqual(
                tuple(ref["candidate_id"] for ref in evolution["generations"][0]["analysis_result_refs"]),
                candidate_ids,
            )
            self.assertFalse(evolution["run_metadata"]["execution"]["evolver_executed_metrics"])
            self.assertEqual(evolution["provenance"]["source"], "test_end_to_end_workflow")


if __name__ == "__main__":
    unittest.main()

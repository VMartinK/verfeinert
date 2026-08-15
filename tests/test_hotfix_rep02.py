"""v0.2.1 REP-02 generic evolution hotfix tests."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from verfeinert.ansatz_evolver import (
    AnalysisResultRef,
    CandidateRef,
    EvolutionRunState,
    GenerationRecord,
    produce_candidate_from_request,
)
from verfeinert.ansatz_evolver.mutation import MutationPolicy, MutationRecipe, expand_mutation_requests
from verfeinert.ansatz_evolver.population import deduplicate_candidate_refs
from verfeinert.ansatz_evolver.selection import ObjectiveSpec, select_strict_pareto_feedback
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    InsertGateMutationFactory,
    build_sanz19_candidate_record,
    export_candidate_json,
)
from verfeinert.core.io import read_json, write_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner
from verfeinert.workflow.config import WorkflowConfigError
from verfeinert.workflow.runner import (
    _AnalysisResultArtifact,
    _analysis_config_fingerprint_from_dict,
    _analysis_result_documents_from_state,
    _matching_analysis_artifact,
    _parent_refs_for_next_generation,
    _selection_reference_results,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIXT_SCRIPT_PATH = PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "scripts" / "run_mixt5g_reproduction.py"
MIXT_CONFIG_PATH = PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "config" / "mixt5g_reproduction.yaml"
CREATED_AT = "2026-08-15T00:00:00Z"


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _candidate_json(template_id: str = "A02", layer: int = 1, *, candidate_id: str = "parent") -> dict:
    return export_candidate_json(
        build_sanz19_candidate_record(template_id, layer, n_qubits=4),
        candidate_id=candidate_id,
        config=CandidateJsonExportConfig(
            created_at=CREATED_AT,
            source_kind="template",
            n_qubits=4,
            git_commit=None,
            discover_git_commit=False,
        ),
    )


def _analysis_result(
    candidate_id: str,
    *,
    expressibility: float | None,
    trainability: float | None,
    cost: float,
    structural_hash: str | None = None,
    fingerprint: str | None = None,
) -> dict:
    metrics = []
    if expressibility is not None:
        metrics.append(
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": {"expressibility": expressibility},
            },
        )
    if trainability is not None:
        metrics.append(
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": {"trainability": trainability},
            },
        )
    metadata = {}
    if fingerprint is not None:
        metadata["analysis_compatibility_fingerprint"] = fingerprint
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {
            "candidate_id": candidate_id,
            "structural_hash": structural_hash or _hash(candidate_id),
        },
        "metrics": metrics,
        "cost": {
            "structural_cost": cost,
            "operation_count": 1,
            "two_qubit_operation_count": 1,
            "parameter_count": 1,
        },
        "classifications": [],
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "schema-test",
            "software_version": "0.0.0",
            "git_commit": None,
            "execution": {"qnodes_executed": False},
        },
        "metadata": metadata,
    }


def _candidate_ref_for_result(document: dict) -> CandidateRef:
    candidate_ref = document["candidate_ref"]
    return CandidateRef(
        candidate_ref["candidate_id"],
        structural_hash=candidate_ref["structural_hash"],
    )


def _analysis_ref(document: dict, *, uri: str | None = None) -> AnalysisResultRef:
    return AnalysisResultRef.from_analysis_result_document(document, analysis_result_uri=uri)


def _strict_feedback_config(output_root: Path) -> WorkflowConfig:
    return WorkflowConfig.from_mapping(
        {
            "run": {"run_id": "strict-feedback-resume"},
            "paths": {"output_root": str(output_root)},
            "workflow": {"scientific_execution": ["evolve"], "postprocessing": []},
            "evolver": {
                "selection_mode": "strict_pareto_feedback",
                "objectives": [
                    {"name": "expressibility", "direction": "maximize"},
                    {"name": "trainability", "direction": "maximize"},
                ],
                "thresholds": {"structural_cost": 1.0},
            },
        },
    )


def _state_with_generations(*generations: GenerationRecord) -> EvolutionRunState:
    return EvolutionRunState(
        "strict-feedback-resume-evolution",
        "running",
        configuration={"random_seed": None, "execution": {}},
        generations=tuple(generations),
        created_at=CREATED_AT,
        git_commit=None,
    )


def _policy_from_generation_override(workflow: WorkflowConfig, generation_index: int) -> MutationPolicy:
    data = dict(workflow.evolver.mutation_policy)
    override = dict(data["generation_overrides"][str(generation_index)])
    return MutationPolicy(
        policy_id=override.get("policy_id", data.get("policy_id", "workflow-mutation-policy")),
        recipes=tuple(MutationRecipe(**dict(recipe)) for recipe in override["recipes"]),
        variants_per_parent=override.get("variants_per_parent", data.get("variants_per_parent", 1)),
        metadata=dict(override.get("metadata", {})),
    )


def _ref_ids(refs) -> tuple[str, ...]:
    return tuple(ref.candidate_id for ref in refs)


class HotfixRep02Tests(unittest.TestCase):
    @staticmethod
    def _select_generation_two(
        config: WorkflowConfig,
        state: EvolutionRunState,
        analysis_by_candidate_id: dict[str, dict],
        results: tuple[dict, ...],
    ) -> GenerationRecord:
        selection = select_strict_pareto_feedback(
            results,
            objectives=(
                ObjectiveSpec("expressibility", "maximize"),
                ObjectiveSpec("trainability", "maximize"),
            ),
            reference_results=_selection_reference_results(config, state, analysis_by_candidate_id, ()),
            thresholds=config.evolver.thresholds,
            strict_ties=config.evolver.strict_ties,
        )
        return GenerationRecord(
            2,
            tuple(_candidate_ref_for_result(result) for result in results),
            parent_refs=tuple(_parent_refs_for_next_generation(config, state, 2)),
            survivor_refs=selection.survivor_refs,
            archive_refs=selection.archive_refs,
            analysis_result_refs=selection.analysis_result_refs,
        )

    def test_all_valid_positions_expansion_preserves_fixed_recipe_cardinality(self) -> None:
        parent = CandidateRef("parent", structural_hash="a" * 64, metadata={"root_candidate_id": "root"})
        candidate = {
            "candidate_id": "parent",
            "circuit": {
                "operations": [
                    {"metadata": {"layer_index": 0}},
                    {"metadata": {"layer_index": 0}},
                    {"metadata": {"layer_index": 0}},
                ],
            },
        }
        policy = MutationPolicy(
            "policy",
            (
                MutationRecipe(
                    "exhaustive",
                    "insert",
                    parameters={
                        "gate": "crx",
                        "edge": [0, 1],
                        "apply_to": "all_valid_positions",
                    },
                ),
                MutationRecipe("fixed", "insert", parameters={"gate": "cz", "edge": [0, 1]}),
            ),
            variants_per_parent=2,
        )

        requests = expand_mutation_requests(
            (parent,),
            generation_index=1,
            policy=policy,
            parent_candidates={"parent": candidate},
        )

        exhaustive = [request for request in requests if request.recipe_id == "exhaustive"]
        fixed = [request for request in requests if request.recipe_id == "fixed"]
        self.assertEqual([request.parameters["insertion_index"] for request in exhaustive], [0, 1, 2, 3])
        self.assertEqual([request.parameters["edge"] for request in exhaustive], [[0, 1]] * 4)
        self.assertEqual([request.metadata["raw_variant_index"] for request in exhaustive], [0, 1, 2, 3])
        self.assertEqual(len(fixed), 2)

    def test_repeat_mutated_single_layer_uses_explicit_insertion_index_and_independent_parameters(self) -> None:
        parent = _candidate_json("A02", 2, candidate_id="parent")
        parent_ref = CandidateRef.from_candidate_document(parent, metadata={"root_candidate_id": "parent"})
        policy = MutationPolicy(
            "policy",
            (
                MutationRecipe(
                    "crx_insert",
                    "insert",
                    parameters={
                        "gate": "crx",
                        "edge": [0, 1],
                        "apply_to": "all_valid_positions",
                        "propagation_policy": "repeat_mutated_single_layer",
                    },
                ),
            ),
        )
        request = expand_mutation_requests(
            (parent_ref,),
            generation_index=1,
            policy=policy,
            parent_candidates={"parent": parent},
        )[0]

        child = produce_candidate_from_request(request, parent, InsertGateMutationFactory())
        inserted = [
            operation
            for operation in child["circuit"]["operations"]
            if operation["gate"]["name"] == "crx"
            and operation["metadata"].get("mutation_code") == "crx_insert"
        ]

        self.assertEqual(len(inserted), 2)
        self.assertEqual([operation["layer"] for operation in inserted], [0, 1])
        self.assertEqual([operation["qubits"] for operation in inserted], [[0, 1], [0, 1]])
        self.assertEqual({operation["metadata"]["insertion_index"] for operation in inserted}, {0})
        parameter_ids = [operation["parameters"][0]["parameter_id"] for operation in inserted]
        self.assertEqual(len(parameter_ids), len(set(parameter_ids)))

    def test_a14_adjacent_fixed_edge_insertions_collapse_structurally(self) -> None:
        parent = _candidate_json("A14", 1, candidate_id="a14-l1")
        parent_ref = CandidateRef.from_candidate_document(parent, metadata={"root_candidate_id": "a14-l1"})
        policy = MutationPolicy(
            "policy",
            (
                MutationRecipe(
                    "crx_insert",
                    "insert",
                    parameters={
                        "gate": "crx",
                        "edge": [0, 1],
                        "apply_to": "all_valid_positions",
                        "propagation_policy": "repeat_mutated_single_layer",
                    },
                ),
            ),
        )
        requests = expand_mutation_requests(
            (parent_ref,),
            generation_index=1,
            policy=policy,
            parent_candidates={"a14-l1": parent},
        )
        by_position = {
            request.parameters["insertion_index"]: produce_candidate_from_request(
                request,
                parent,
                InsertGateMutationFactory(),
            )
            for request in requests
            if request.parameters["insertion_index"] in {7, 8}
        }

        self.assertEqual(
            by_position[7]["identity"]["structural_hash"],
            by_position[8]["identity"]["structural_hash"],
        )

    def test_strict_pareto_feedback_filters_and_updates_archive(self) -> None:
        archive = _analysis_result("archive", expressibility=1.0, trainability=1.0, cost=0.1)
        candidates = (
            _analysis_result("missing", expressibility=2.0, trainability=None, cost=0.1),
            _analysis_result("threshold", expressibility=3.0, trainability=3.0, cost=0.9),
            _analysis_result("tie", expressibility=1.0, trainability=1.0, cost=0.1),
            _analysis_result("archive-dominated", expressibility=0.5, trainability=0.5, cost=0.1),
            _analysis_result("within-dominated", expressibility=1.5, trainability=1.5, cost=0.1),
            _analysis_result("best", expressibility=2.0, trainability=2.0, cost=0.1),
            _analysis_result("tradeoff", expressibility=3.0, trainability=0.5, cost=0.1),
        )

        selection = select_strict_pareto_feedback(
            candidates,
            objectives=(
                ObjectiveSpec("expressibility", "maximize"),
                ObjectiveSpec("trainability", "maximize"),
            ),
            reference_results=(archive,),
            thresholds={"structural_cost": 0.5},
        )
        decisions = {decision.candidate_id: decision.reason for decision in selection.decisions}

        self.assertEqual(decisions["missing"], "missing_metric")
        self.assertEqual(decisions["threshold"], "cost_threshold_failed")
        self.assertEqual(decisions["tie"], "duplicate_or_tie_with_accumulated_frontier")
        self.assertEqual(decisions["archive-dominated"], "dominated_by_accumulated_frontier")
        self.assertEqual(decisions["within-dominated"], "dominated_within_generation")
        self.assertEqual([ref.candidate_id for ref in selection.survivor_refs], ["best", "tradeoff"])
        self.assertEqual([ref.candidate_id for ref in selection.archive_refs], ["best", "tradeoff"])
        self.assertFalse(selection.configuration["combined_score_used"])
        self.assertEqual(
            [objective["name"] for objective in selection.configuration["objectives"]],
            ["expressibility", "trainability"],
        )

    def test_strict_feedback_resume_rehydrates_history_and_matches_continuous_frontier(self) -> None:
        with TemporaryDirectory(prefix="strict-feedback-resume-", dir="/tmp") as temp_dir:
            root = Path(temp_dir)
            config = _strict_feedback_config(root / "outputs")
            g0_result = _analysis_result("g0-seed", expressibility=0.2, trainability=0.2, cost=0.1)
            g1_result = _analysis_result("g1-frontier", expressibility=1.0, trainability=1.0, cost=0.1)
            g0_ref = _candidate_ref_for_result(g0_result)
            g1_ref = _candidate_ref_for_result(g1_result)
            g2_results = (
                _analysis_result("g2-dominated", expressibility=0.5, trainability=0.5, cost=0.1),
                _analysis_result("g2-best", expressibility=1.5, trainability=1.5, cost=0.1),
                _analysis_result("g2-tradeoff", expressibility=2.0, trainability=0.8, cost=0.1),
            )
            source_path = root / "resume" / "evolution_run.json"
            write_json(root / "resume" / "analysis" / "g0.json", g0_result)
            write_json(root / "resume" / "analysis" / "g1.json", g1_result)

            continuous_state = _state_with_generations(
                GenerationRecord(
                    0,
                    (g0_ref,),
                    survivor_refs=(g0_ref,),
                    archive_refs=(g0_ref,),
                    analysis_result_refs=(_analysis_ref(g0_result),),
                ),
                GenerationRecord(
                    1,
                    (g1_ref,),
                    parent_refs=(g0_ref,),
                    survivor_refs=(g1_ref,),
                    archive_refs=(g1_ref,),
                    analysis_result_refs=(_analysis_ref(g1_result),),
                ),
            )
            resumed_state = _state_with_generations(
                GenerationRecord(
                    0,
                    (g0_ref,),
                    survivor_refs=(g0_ref,),
                    archive_refs=(g0_ref,),
                    analysis_result_refs=(_analysis_ref(g0_result, uri="analysis/g0.json"),),
                ),
                GenerationRecord(
                    1,
                    (g1_ref,),
                    parent_refs=(g0_ref,),
                    survivor_refs=(g1_ref,),
                    archive_refs=(g1_ref,),
                    analysis_result_refs=(_analysis_ref(g1_result, uri="analysis/g1.json"),),
                ),
            )

            continuous_generation = self._select_generation_two(
                config,
                continuous_state,
                {"g0-seed": g0_result, "g1-frontier": g1_result},
                g2_results,
            )
            resumed_analysis = _analysis_result_documents_from_state(
                resumed_state,
                source_path=source_path,
            )
            resumed_generation = self._select_generation_two(
                config,
                resumed_state,
                resumed_analysis,
                g2_results,
            )

            self.assertEqual(set(resumed_analysis), {"g0-seed", "g1-frontier"})
            self.assertEqual(_ref_ids(resumed_generation.parent_refs), _ref_ids(continuous_generation.parent_refs))
            self.assertEqual(_ref_ids(resumed_generation.survivor_refs), _ref_ids(continuous_generation.survivor_refs))
            self.assertEqual(_ref_ids(resumed_generation.archive_refs), _ref_ids(continuous_generation.archive_refs))
            self.assertEqual(_ref_ids(resumed_generation.parent_refs), ("g1-frontier",))
            self.assertEqual(_ref_ids(resumed_generation.survivor_refs), ("g2-best", "g2-tradeoff"))
            self.assertEqual(_ref_ids(resumed_generation.archive_refs), ("g2-best", "g2-tradeoff"))

    def test_strict_feedback_resume_fails_closed_when_archive_result_is_unresolved(self) -> None:
        config = _strict_feedback_config(Path("/tmp/verfeinert-strict-feedback-missing"))
        archive_ref = CandidateRef("missing-archive", structural_hash=_hash("missing-archive"))
        state = _state_with_generations(
            GenerationRecord(
                0,
                (archive_ref,),
                survivor_refs=(archive_ref,),
                archive_refs=(archive_ref,),
            ),
        )

        with self.assertRaisesRegex(
            WorkflowConfigError,
            "cannot continue strict_pareto_feedback: unresolved AnalysisResult.*missing-archive",
        ):
            _selection_reference_results(config, state, {}, ())

    def test_analysis_result_rehydration_rejects_wrong_or_conflicting_artifacts(self) -> None:
        with TemporaryDirectory(prefix="strict-feedback-bad-artifacts-", dir="/tmp") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "resume" / "evolution_run.json"
            candidate_result = _analysis_result("candidate", expressibility=1.0, trainability=1.0, cost=0.1)
            candidate_ref = _candidate_ref_for_result(candidate_result)

            wrong_id = {**candidate_result, "analysis_result_id": "analysis-other"}
            write_json(root / "resume" / "analysis" / "wrong-id.json", wrong_id)
            wrong_id_state = _state_with_generations(
                GenerationRecord(
                    0,
                    (candidate_ref,),
                    survivor_refs=(candidate_ref,),
                    archive_refs=(candidate_ref,),
                    analysis_result_refs=(_analysis_ref(candidate_result, uri="analysis/wrong-id.json"),),
                ),
            )
            with self.assertRaisesRegex(WorkflowConfigError, "resolved to AnalysisResult 'analysis-other'"):
                _analysis_result_documents_from_state(wrong_id_state, source_path=source_path)

            wrong_candidate = {
                **candidate_result,
                "candidate_ref": {
                    **candidate_result["candidate_ref"],
                    "candidate_id": "other-candidate",
                },
            }
            write_json(root / "resume" / "analysis" / "wrong-candidate.json", wrong_candidate)
            wrong_candidate_state = _state_with_generations(
                GenerationRecord(
                    0,
                    (candidate_ref,),
                    survivor_refs=(candidate_ref,),
                    archive_refs=(candidate_ref,),
                    analysis_result_refs=(_analysis_ref(candidate_result, uri="analysis/wrong-candidate.json"),),
                ),
            )
            with self.assertRaisesRegex(WorkflowConfigError, "resolved to candidate 'other-candidate'"):
                _analysis_result_documents_from_state(wrong_candidate_state, source_path=source_path)

            replacement_result = {**candidate_result, "analysis_result_id": "analysis-candidate-v2"}
            write_json(root / "resume" / "analysis" / "candidate-v1.json", candidate_result)
            write_json(root / "resume" / "analysis" / "candidate-v2.json", replacement_result)
            conflict_state = _state_with_generations(
                GenerationRecord(
                    0,
                    (candidate_ref,),
                    survivor_refs=(candidate_ref,),
                    archive_refs=(candidate_ref,),
                    analysis_result_refs=(_analysis_ref(candidate_result, uri="analysis/candidate-v1.json"),),
                ),
                GenerationRecord(
                    1,
                    (candidate_ref,),
                    survivor_refs=(candidate_ref,),
                    archive_refs=(candidate_ref,),
                    analysis_result_refs=(
                        AnalysisResultRef(
                            "analysis-candidate-v2",
                            "candidate",
                            analysis_result_uri="analysis/candidate-v2.json",
                        ),
                    ),
                ),
            )
            with self.assertRaisesRegex(WorkflowConfigError, "conflicting AnalysisResult identities"):
                _analysis_result_documents_from_state(conflict_state, source_path=source_path)

    def test_initial_parent_policy_uses_all_generation_zero_candidates_once(self) -> None:
        config = WorkflowConfig.from_mapping(
            {
                "run": {"run_id": "parent-policy"},
                "paths": {"output_root": "/tmp/verfeinert-parent-policy"},
                "workflow": {"scientific_execution": ["evolve"], "postprocessing": []},
                "evolver": {
                    "selection_mode": "strict_pareto_feedback",
                    "objectives": [
                        {"name": "expressibility", "direction": "maximize"},
                        {"name": "trainability", "direction": "maximize"},
                    ],
                    "initial_parent_policy": "all_generation_zero_candidates",
                },
            },
        )
        refs = tuple(CandidateRef(f"candidate-{index}", structural_hash=_hash(str(index))) for index in range(3))
        survivor = refs[:1]
        state = type(
            "State",
            (),
            {
                "generations": (
                    GenerationRecord(0, refs, survivor_refs=survivor, archive_refs=survivor),
                    GenerationRecord(1, survivor, survivor_refs=survivor, archive_refs=survivor),
                ),
            },
        )()

        self.assertEqual(_parent_refs_for_next_generation(config, state, 1), refs)
        self.assertEqual(_parent_refs_for_next_generation(config, state, 2), survivor)

    def test_analysis_reuse_fingerprint_ignores_paths_but_rejects_scientific_differences(self) -> None:
        base = {
            "run_id": "source",
            "input_roots": ["/tmp/source-inputs"],
            "output_root": "/tmp/source-output",
            "selected_metrics": ["structural_cost"],
            "execution": {"mode": "serial", "worker_count": 1},
            "permissions": {"allow_qnode_execution": False, "allow_expensive_metrics": False},
            "random_seed": None,
            "structural_cost": {"reference_id": "same"},
            "metric_configs": {},
            "materialization": {"enabled": False},
        }
        path_changed = {**base, "run_id": "target", "input_roots": ["/tmp/other"], "output_root": "/tmp/other-output"}
        metric_changed = {**base, "selected_metrics": ["structural_cost", "expressibility"]}

        fingerprint = _analysis_config_fingerprint_from_dict(base)
        self.assertEqual(fingerprint, _analysis_config_fingerprint_from_dict(path_changed))
        self.assertNotEqual(fingerprint, _analysis_config_fingerprint_from_dict(metric_changed))

        candidate = _candidate_json(candidate_id="reuse-candidate")
        result = _analysis_result(
            "reuse-candidate",
            expressibility=None,
            trainability=None,
            cost=0.2,
            structural_hash=candidate["identity"]["structural_hash"],
            fingerprint=fingerprint,
        )
        artifact = _AnalysisResultArtifact(result, "/tmp/original-analysis.json")

        self.assertIs(_matching_analysis_artifact(candidate, (artifact,), fingerprint), artifact)
        changed_candidate = {
            **candidate,
            "identity": {**candidate["identity"], "structural_hash": _hash("different")},
        }
        self.assertIsNone(_matching_analysis_artifact(changed_candidate, (artifact,), fingerprint))
        self.assertIsNone(_matching_analysis_artifact(candidate, (artifact,), _hash("other-fingerprint")))
        self.assertEqual(artifact.document["analysis_result_id"], result["analysis_result_id"])
        self.assertEqual(artifact.document["provenance"], result["provenance"])

    def test_mixt5g_full_mapping_exposes_generic_feedback_contract(self) -> None:
        module = _load_mixt_module()
        config = module.load_config(MIXT_CONFIG_PATH)

        self.assertEqual(len(module.build_initial_records(config, profile="full")), 30)
        mapping = module.build_workflow_mapping(
            config,
            output_root=Path("/tmp/verfeinert-mixt5g-full"),
            profile="full",
            cost_threshold=0.2,
            trajectory_index=2,
        )
        workflow = WorkflowConfig.from_mapping(mapping)
        recipes = workflow.evolver.mutation_policy["generation_overrides"]

        self.assertEqual(workflow.evolver.selection_mode, "strict_pareto_feedback")
        self.assertEqual(workflow.evolver.thresholds, {"structural_cost": 0.2})
        self.assertEqual(
            workflow.evolver.objectives,
            (
                {"name": "expressibility", "direction": "maximize"},
                {"name": "trainability", "direction": "maximize"},
            ),
        )
        self.assertEqual(workflow.evolver.initial_parent_policy, "all_generation_zero_candidates")
        self.assertTrue(workflow.evolver.offspring_deduplication["enabled"])
        self.assertTrue(workflow.analysis_result_reuse["enabled"])
        self.assertEqual(workflow.analyzer.selected_metrics, ("structural_cost", "expressibility", "trainability"))
        self.assertEqual(
            [recipes[str(index)]["recipes"][0]["parameters"]["gate"] for index in range(1, 6)],
            ["crx", "crz", "cz", "crx", "crz"],
        )
        for generation in range(1, 6):
            parameters = recipes[str(generation)]["recipes"][0]["parameters"]
            self.assertEqual(parameters["edge"], [0, 1])
            self.assertEqual(parameters["apply_to"], "all_valid_positions")
            self.assertEqual(parameters["propagation_policy"], "repeat_mutated_single_layer")

    def test_mixt5g_full_public_generation_one_structural_anchors(self) -> None:
        module = _load_mixt_module()
        config = module.load_config(MIXT_CONFIG_PATH)
        with TemporaryDirectory(prefix="mixt5g-g1-anchors-", dir="/tmp") as temp_dir:
            output_root = Path(temp_dir)
            generate_mapping = module.build_workflow_mapping(
                config,
                output_root=output_root,
                profile="full",
                scientific_execution=("generate",),
                postprocessing=(),
                total_generations=1,
            )
            generate_result = WorkflowRunner(WorkflowConfig.from_mapping(generate_mapping)).run(
                candidate_records=module.build_initial_records(config, profile="full"),
            )
            parents = tuple(read_json(path) for path in generate_result.candidate_paths)
            parent_by_id = {parent["candidate_id"]: parent for parent in parents}
            workflow = WorkflowConfig.from_mapping(
                module.build_workflow_mapping(
                    config,
                    output_root=output_root,
                    profile="full",
                    postprocessing=(),
                    total_generations=1,
                    cost_threshold=1.0,
                    trajectory_index=1,
                ),
            )
            policy = _policy_from_generation_override(workflow, 1)
            parent_refs = tuple(
                CandidateRef.from_candidate_document(
                    parent,
                    metadata={"root_candidate_id": parent["lineage"]["root_candidate_id"]},
                )
                for parent in parents
            )
            requests = expand_mutation_requests(
                parent_refs,
                generation_index=1,
                policy=policy,
                parent_candidates=parent_by_id,
            )
            factory = InsertGateMutationFactory()
            children = tuple(
                produce_candidate_from_request(request, parent_by_id[request.parent_candidate_id], factory)
                for request in requests
            )
            kept_refs, report = deduplicate_candidate_refs(
                tuple(CandidateRef.from_candidate_document(child) for child in children),
                key="structural_hash",
                keep="first",
            )
            a14_by_position = {
                request.parameters["insertion_index"]: child["identity"]["structural_hash"]
                for request, child in zip(requests, children, strict=True)
                if request.parent_candidate_id == "mixt5g-a14-l1"
                and request.parameters["insertion_index"] in {7, 8}
            }

            self.assertEqual(len(parents), 30)
            self.assertEqual(len(requests), 480)
            self.assertEqual(len(children), 480)
            self.assertEqual(len(kept_refs), 477)
            self.assertEqual(report.input_count, 480)
            self.assertEqual(report.kept_count, 477)
            self.assertEqual(report.duplicate_count, 3)
            self.assertEqual(a14_by_position[7], a14_by_position[8])
            self.assertTrue(all(request.parameters["edge"] == [0, 1] for request in requests))
            self.assertTrue(all(request.parameters["gate"] == "crx" for request in requests))
            self.assertTrue(
                all(
                    request.parameters["propagation_policy"] == "repeat_mutated_single_layer"
                    for request in requests
                ),
            )
            for child in children:
                mutation = child["lineage"]["mutation"]
                self.assertEqual(mutation["operation"], "crx")
                self.assertEqual(mutation["parameters"]["edge"], [0, 1])
                self.assertEqual(mutation["parameters"]["propagation_policy"], "repeat_mutated_single_layer")

    def test_mixt5g_reference_summary_contains_closed_historical_count_contract(self) -> None:
        summary = read_json(PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "comparison" / "reference_summary.json")
        expected = {
            "1.0": {
                "initial_frontier_count": 17,
                "generations": [(477, 24), (364, 17), (271, 18), (277, 10), (160, 4)],
            },
            "0.2": {
                "initial_frontier_count": 8,
                "generations": [(477, 15), (250, 19), (329, 23), (392, 25), (456, 4)],
            },
            "0.1": {
                "initial_frontier_count": 4,
                "generations": [(477, 5), (70, 8), (120, 12), (179, 14), (224, 5)],
            },
        }
        trajectories = summary["historical_trajectory_counts"]["thresholds"]

        for threshold, contract in expected.items():
            trajectory = trajectories[threshold]
            observed = [
                (generation["candidate_count"], generation["survivor_count"])
                for generation in trajectory["generations"]
            ]
            self.assertEqual(trajectory["initial_frontier_count"], contract["initial_frontier_count"])
            self.assertEqual(trajectory["generation_one_parent_count"], 30)
            self.assertEqual(observed, contract["generations"])

        accounting = summary["historical_trajectory_counts"]["accounting"]
        summed_candidates = sum(
            generation["candidate_count"]
            for trajectory in trajectories.values()
            for generation in trajectory["generations"]
        )
        self.assertEqual(summed_candidates, 4523)
        self.assertEqual(accounting["evolutionary_candidate_count_g1_to_g5"], 4523)
        self.assertEqual(accounting["generation_zero_candidate_count_across_trajectories"], 90)
        self.assertEqual(accounting["total_candidate_accounting"], 4613)


def _load_mixt_module():
    spec = importlib.util.spec_from_file_location("mixt5g_reproduction_script", MIXT_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load MIXT-5G reproduction script.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()

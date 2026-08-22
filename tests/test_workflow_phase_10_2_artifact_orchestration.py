"""Phase 10.2 tests for artifact-oriented workflow orchestration."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalyzerExecutionPermissions,
    CircuitMaterializationConfig,
)
from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    ConstraintSet,
    InsertGateMutationFactory,
    StagedPackageJsonExportConfig,
    write_canonical_staged_package_json,
)
from verfeinert.workflow import WorkflowConfig, WorkflowConfigError, WorkflowRunner
from verfeinert.workflow import read_workflow_checkpoint_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
CREATED_AT = "2026-08-06T00:00:00Z"
HASH = "3" * 64


def _bounds() -> dict:
    return {
        "parameter_count": {"min": 0, "max": 8},
        "depth": {"min": 0, "max": 20},
        "two_qubit_operation_count": {"min": 0, "max": 6},
    }


def _workflow_mapping(
    output_root: Path,
    *,
    run_id: str,
    campaign_type: str = "individual",
    scientific_execution=(),
    postprocessing=(),
    artifacts: dict | None = None,
    max_generations: int = 1,
    keep: int = 1,
    resume_mode: str = "continue",
    constraints: dict | None = None,
) -> dict:
    mapping = {
        "run": {
            "run_id": run_id,
            "created_at": CREATED_AT,
            "random_seed": 17,
        },
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": campaign_type,
            "scientific_execution": list(scientific_execution),
            "postprocessing": list(postprocessing),
            "resume": {"mode": resume_mode},
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "phase102",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {"reference_bounds": _bounds()},
            "ranking": {
                "score_components": {"cost.structural_cost": 1},
                "combination": "weighted_sum",
                "ascending": True,
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "phase102-selection",
            "metric_name": "structural_cost",
            "keep": keep,
            "direction": "minimize",
            "max_generations": max_generations,
            "patience": 10,
            "mutation_policy": {
                "policy_id": "phase102-mutation",
                "variants_per_parent": 1,
                "recipes": [{"recipe_id": "insert-test", "mutation_type": "insert"}],
            },
        },
    }
    if constraints is not None:
        mapping["generation"]["constraints"] = constraints
        mapping["evolver"]["mutation_policy"]["recipes"][0]["parameters"] = {
            "gate": "cz",
            "edge": [1, 2],
            "parameterized": False,
        }
    if artifacts is not None:
        mapping["artifacts"] = artifacts
    return mapping


def _linear_constraints() -> dict:
    return {
        "allowed_gates": ["rx", "rz", "cx", "cz"],
        "allowed_inserted_gates": ["cz"],
        "connectivity": {"n_qubits": 4, "topology": "linear"},
    }


def _candidate_document() -> dict:
    return json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))


def _analysis_result(
    candidate_id: str,
    *,
    expressibility: float = 1.0,
    trainability: float = 1.0,
    cost: float = 0.1,
) -> dict:
    return {
        "schema_version": "verfeinert.analysis_result.v1",
        "analysis_result_id": f"analysis-{candidate_id}",
        "candidate_ref": {"candidate_id": candidate_id},
        "metrics": [
            {
                "metric_id": f"metric-expressibility-{candidate_id}",
                "name": "expressibility",
                "status": "computed",
                "value": expressibility,
            },
            {
                "metric_id": f"metric-trainability-{candidate_id}",
                "name": "trainability",
                "status": "computed",
                "value": trainability,
            },
        ],
        "cost": {"structural_cost": cost},
        "classifications": [],
        "metadata": {"candidate_semantics": {"lineage": {"generation": 0}}},
        "provenance": {
            "created_at": CREATED_AT,
            "analyzer": "phase-10-2-test",
            "execution": {"qnodes_executed": False},
        },
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_analysis_results(root: Path) -> tuple[Path, Path]:
    return (
        _write_json(root / "analysis-a.json", _analysis_result("user-alpha", expressibility=1.0, trainability=0.4, cost=0.2)),
        _write_json(root / "analysis-b.json", _analysis_result("user-beta", expressibility=0.7, trainability=0.9, cost=0.3)),
    )


def _write_staged_package(root: Path) -> Path:
    result = write_canonical_staged_package_json(
        [_candidate_document()],
        config=StagedPackageJsonExportConfig(
            package_id="phase102-input-package",
            output_root=root,
            candidate_export=CandidateJsonExportConfig(
                created_at=CREATED_AT,
                source_label="phase-10-2-test",
                git_commit=None,
                discover_git_commit=False,
            ),
            created_at=CREATED_AT,
            producer="phase-10-2-test",
            git_commit=None,
            discover_git_commit=False,
        ),
    )
    assert result.staged_package_path is not None
    return result.staged_package_path


def _evolution_summary(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "status": document["run_metadata"]["status"],
        "final_stopping_decision": document["metadata"]["workflow"]["final_stopping_decision"],
        "generations": [
            {
                "generation_index": generation["generation_index"],
                "candidate_ids": [
                    ref["candidate_id"] for ref in generation["candidate_refs"]
                ],
                "analysis_candidate_ids": [
                    ref["candidate_id"] for ref in generation["analysis_result_refs"]
                ],
                "survivor_ids": [
                    ref["candidate_id"] for ref in generation["survivor_refs"]
                ],
                "rejected_ids": [
                    ref["candidate_id"] for ref in generation.get("rejected_refs", [])
                ],
                "archive_ids": [
                    ref["candidate_id"] for ref in generation.get("archive_refs", [])
                ],
                "stopping": generation["configuration"].get("stopping"),
            }
            for generation in document["generations"]
        ],
    }


class RecordingFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def __call__(self, request, parent):
        self.calls.append((request.parent_candidate_id, request.generation_index))
        child = copy.deepcopy(dict(parent))
        child["candidate_id"] = f"{request.parent_candidate_id}_g{request.generation_index:03d}"
        child["identity"] = {
            "structural_hash": HASH,
            "lineage_hash": HASH,
            "hash_schema_version": "phase-10-2-test",
        }
        child["lineage"] = {
            "generation": request.generation_index,
            "root_candidate_id": parent["lineage"].get("root_candidate_id") or parent["candidate_id"],
            "parent_candidate_id": request.parent_candidate_id,
            "mutation": {
                "mutation_id": request.request_id.replace(":", "-"),
                "type": request.mutation_type,
                "source_candidate_id": request.parent_candidate_id,
                "operation": "test-insert",
                "parameters": dict(request.parameters),
            },
        }
        child["provenance"]["source"] = {
            "kind": "mutation",
            "label": "phase-10-2-recording-factory",
        }
        return child


class WorkflowPhase102ArtifactOrchestrationTests(unittest.TestCase):
    def test_direct_individual_workflow_config_defaults_to_generate_analyze(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorkflowConfig(
                run_id="direct-individual",
                output_root=Path(tmp) / "out",
                campaign_type="individual",
            )

            self.assertEqual(config.scientific_execution, ("generate", "analyze"))
            self.assertEqual(config.postprocessing, ())
            self.assertEqual(config.stages, ("generate", "analyze"))

    def test_nested_legacy_stages_are_normalized_and_conflicts_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(
                Path(tmp) / "out",
                run_id="legacy-normalized",
                scientific_execution=("generate", "analyze"),
            )
            mapping["workflow"] = {"stages": ["generate", "analyze", "csv"]}

            config = WorkflowConfig.from_mapping(mapping)

            self.assertEqual(config.scientific_execution, ("generate", "analyze"))
            self.assertEqual(config.postprocessing, ("export_csv",))
            mapping["stages"] = ["generate", "analyze", "evolve"]
            with self.assertRaises(WorkflowConfigError):
                WorkflowConfig.from_mapping(mapping)

    def test_checkpoint_config_roundtrips_resume_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(
                Path(tmp) / "out",
                run_id="checkpoint-config",
                scientific_execution=("analyze",),
            )
            mapping["workflow"]["checkpoint"] = {"enabled": True}
            mapping["workflow"]["resume"]["checkpoint"] = str(Path(tmp) / "checkpoint.json")

            config = WorkflowConfig.from_mapping(mapping)
            roundtripped = WorkflowConfig.from_mapping(config.to_dict())

            self.assertTrue(roundtripped.checkpoint.enabled)
            self.assertEqual(
                roundtripped.resume.checkpoint,
                str(Path(tmp) / "checkpoint.json"),
            )

    def test_individual_generate_analyze_does_not_create_evolution_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="individual-ga",
                        scientific_execution=("generate", "analyze"),
                    ),
                ),
            ).run()

            self.assertEqual(result.executed_operations, ("generate", "analyze"))
            self.assertIsNone(result.evolution_run_path)
            self.assertIsNone(result.ranking_json_path)
            self.assertFalse(result.provenance["execution"]["evolution_exported"])
            self.assertFalse(result.provenance["execution"]["ranking_executed"])

    def test_generate_analyze_csv_does_not_evolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="individual-ga-csv",
                        scientific_execution=("generate", "analyze"),
                        postprocessing=("csv",),
                    ),
                ),
            ).run()

            self.assertEqual(result.executed_operations, ("generate", "analyze", "export_csv"))
            self.assertIsNone(result.evolution_run_path)
            self.assertTrue(result.analysis_csv_path.is_file())
            with result.analysis_csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["candidate_id"], "phase102-a02-l1")

    def test_candidate_json_enters_directly_at_analyze(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="candidate-to-analysis",
                        scientific_execution=("analyze",),
                        artifacts={"candidates": [str(CANDIDATE_EXAMPLE)]},
                    ),
                ),
            ).run()

            self.assertEqual(result.executed_operations, ("analyze",))
            self.assertEqual(result.candidate_paths, ())
            self.assertEqual(result.candidate_ids, ("reference-a02-l1-parent",))
            self.assertEqual(len(result.analysis_result_paths), 1)
            self.assertFalse(result.provenance["execution"]["candidate_generation_executed"])

    def test_candidate_artifact_violating_generation_constraints_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(
                Path(tmp) / "out",
                run_id="candidate-constraint-reject",
                scientific_execution=("analyze",),
                artifacts={"candidates": [str(CANDIDATE_EXAMPLE)]},
                constraints={
                    "allowed_gates": ["rx", "rz"],
                    "allowed_inserted_gates": ["cz"],
                },
            )

            with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                with self.assertRaisesRegex(WorkflowConfigError, "violates workflow generation.constraints"):
                    WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

    def test_staged_package_enters_directly_at_analyze(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = _write_staged_package(Path(tmp) / "inputs")
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="package-to-analysis",
                        scientific_execution=("analyze",),
                        artifacts={"staged_packages": [str(package_path)]},
                    ),
                ),
            ).run()

            self.assertEqual(result.executed_operations, ("analyze",))
            self.assertIsNone(result.staged_package_path)
            self.assertEqual(result.candidate_ids, ("reference-a02-l1-parent",))
            self.assertEqual(len(result.analysis_result_paths), 1)

    def test_checkpoint_after_generation_resumes_analysis_without_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-generate",
                scientific_execution=("generate",),
            )
            generate_mapping["workflow"]["checkpoint"] = {"enabled": True}
            generated = WorkflowRunner(WorkflowConfig.from_mapping(generate_mapping)).run()

            self.assertTrue(generated.checkpoint_path.is_file())
            checkpoint = read_workflow_checkpoint_json(generated.checkpoint_path)
            self.assertEqual(checkpoint["workflow"]["completed_stages"], ["generate"])
            self.assertFalse(list(generated.checkpoint_path.parent.glob("*.tmp")))

            resume_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-generate",
                scientific_execution=("analyze",),
            )
            resume_mapping["workflow"]["resume"]["checkpoint"] = str(generated.checkpoint_path)
            with (
                mock.patch.object(
                    WorkflowRunner,
                    "_run_generation_stage",
                    side_effect=AssertionError("generation must not rerun"),
                ),
                mock.patch.object(
                    WorkflowRunner,
                    "_run_evolution_stage",
                    side_effect=AssertionError("evolution must not run"),
                ),
            ):
                resumed = WorkflowRunner(WorkflowConfig.from_mapping(resume_mapping)).run()

            self.assertEqual(resumed.executed_operations, ("analyze",))
            self.assertEqual(resumed.candidate_ids, ("phase102-a02-l1",))
            self.assertEqual(len(resumed.analysis_result_paths), 1)
            self.assertEqual(
                {item["kind"] for item in resumed.reused_artifacts},
                {"workflow_checkpoint"},
            )

    def test_checkpoint_resume_rejects_completed_generate_stage_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-repeat-stage",
                scientific_execution=("generate",),
            )
            generate_mapping["workflow"]["checkpoint"] = {"enabled": True}
            generated = WorkflowRunner(WorkflowConfig.from_mapping(generate_mapping)).run()

            resume_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-repeat-stage",
                scientific_execution=("generate", "analyze"),
            )
            resume_mapping["workflow"]["resume"]["checkpoint"] = str(generated.checkpoint_path)
            with self.assertRaisesRegex(WorkflowConfigError, "already completed"):
                WorkflowRunner(WorkflowConfig.from_mapping(resume_mapping)).run()

    def test_checkpoint_after_analysis_resumes_evolution_equivalent_to_uninterrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            continuous = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "continuous",
                        run_id="checkpoint-equivalence",
                        campaign_type="evolutionary",
                        scientific_execution=("generate", "analyze", "evolve"),
                        max_generations=2,
                    ),
                ),
            ).run(candidate_factory=RecordingFactory())

            staged_mapping = _workflow_mapping(
                root / "resumed",
                run_id="checkpoint-equivalence",
                campaign_type="evolutionary",
                scientific_execution=("generate", "analyze"),
                max_generations=2,
            )
            staged_mapping["workflow"]["checkpoint"] = {"enabled": True}
            staged = WorkflowRunner(WorkflowConfig.from_mapping(staged_mapping)).run()

            resume_mapping = _workflow_mapping(
                root / "resumed",
                run_id="checkpoint-equivalence",
                campaign_type="evolutionary",
                scientific_execution=("evolve",),
                max_generations=2,
            )
            resume_mapping["workflow"]["resume"]["checkpoint"] = str(staged.checkpoint_path)
            resumed_factory = RecordingFactory()
            resumed = WorkflowRunner(WorkflowConfig.from_mapping(resume_mapping)).run(
                candidate_factory=resumed_factory,
            )

            self.assertEqual(len(resumed_factory.calls), 1)
            self.assertEqual(
                _evolution_summary(resumed.evolution_run_path),
                _evolution_summary(continuous.evolution_run_path),
            )

    def test_checkpoint_resume_rejects_changed_metric_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-metric-mismatch",
                scientific_execution=("generate",),
            )
            generate_mapping["workflow"]["checkpoint"] = {"enabled": True}
            generated = WorkflowRunner(WorkflowConfig.from_mapping(generate_mapping)).run()

            resume_mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-metric-mismatch",
                scientific_execution=("analyze",),
            )
            resume_mapping["workflow"]["resume"]["checkpoint"] = str(generated.checkpoint_path)
            resume_mapping["analyzer"]["selected_metrics"] = ["structural_cost", "expressibility"]
            with self.assertRaisesRegex(WorkflowConfigError, "workflow_fingerprint mismatch"):
                WorkflowRunner(WorkflowConfig.from_mapping(resume_mapping)).run()

    def test_checkpoint_resume_fails_closed_for_corruption_and_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corrupt = _write_json(root / "bad-checkpoint.json", {"schema_version": "wrong"})
            mapping = _workflow_mapping(
                root / "out",
                run_id="checkpoint-corrupt",
                scientific_execution=("analyze",),
            )
            mapping["workflow"]["resume"]["checkpoint"] = str(corrupt)
            with self.assertRaisesRegex(WorkflowConfigError, "WorkflowCheckpoint"):
                WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            generate_mapping = _workflow_mapping(
                root / "hash-out",
                run_id="checkpoint-hash",
                scientific_execution=("generate",),
            )
            generate_mapping["workflow"]["checkpoint"] = {"enabled": True}
            generated = WorkflowRunner(WorkflowConfig.from_mapping(generate_mapping)).run()
            generated.candidate_paths[0].write_text("changed\n", encoding="utf-8")

            resume_mapping = _workflow_mapping(
                root / "hash-out",
                run_id="checkpoint-hash",
                scientific_execution=("analyze",),
            )
            resume_mapping["workflow"]["resume"]["checkpoint"] = str(generated.checkpoint_path)
            with self.assertRaisesRegex(WorkflowConfigError, "hash mismatch"):
                WorkflowRunner(WorkflowConfig.from_mapping(resume_mapping)).run()

    def test_analysis_result_ranking_reuses_artifact_without_scientific_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_analysis_results(Path(tmp) / "inputs")
            mapping = _workflow_mapping(
                Path(tmp) / "out",
                run_id="analysis-to-ranking",
                scientific_execution=(),
                postprocessing=("ranking",),
                artifacts={"analysis_results": [str(path) for path in paths]},
            )
            mapping["analyzer"]["materialization"] = {"enabled": True}
            mapping["analyzer"]["permissions"] = {
                "allow_expensive_metrics": True,
                "allow_qnode_execution": True,
            }

            with mock.patch.object(AnalysisPipeline, "run_and_write", side_effect=AssertionError("analyzer must not run")):
                result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertEqual(result.executed_operations, ("ranking",))
            self.assertEqual(result.analysis_result_paths, ())
            self.assertTrue(result.ranking_json_path.is_file())
            self.assertFalse(result.provenance["execution"]["analysis_executed"])
            self.assertFalse(result.provenance["execution"]["qnodes_executed_by_runner"])
            self.assertEqual({item["kind"] for item in result.reused_artifacts}, {"analysis_result"})

    def test_analysis_result_pareto_reuses_artifact_without_scientific_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_analysis_results(Path(tmp) / "inputs")
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="analysis-to-pareto",
                        scientific_execution=(),
                        postprocessing=("pareto", "csv"),
                        artifacts={"analysis_results": [str(path) for path in paths]},
                    ),
                ),
            ).run()

            self.assertEqual(result.executed_operations, ("pareto", "export_csv"))
            self.assertEqual(result.analysis_result_paths, ())
            self.assertTrue(result.pareto_json_path.is_file())
            self.assertTrue(result.pareto_csv_path.is_file())
            self.assertFalse(result.provenance["execution"]["candidate_generation_executed"])
            self.assertFalse(result.provenance["execution"]["analysis_executed"])

    def test_evolution_resume_appends_next_generation_without_recomputing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_factory = RecordingFactory()
            first = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="resume-run",
                        campaign_type="evolutionary",
                        scientific_execution=("generate", "analyze", "evolve"),
                        max_generations=3,
                    ),
                ),
            ).run(candidate_factory=first_factory)
            first_doc = json.loads(first.evolution_run_path.read_text(encoding="utf-8"))

            second_factory = RecordingFactory()
            second = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="resume-run",
                        campaign_type="evolutionary",
                        scientific_execution=("evolve",),
                        artifacts={"evolution_run": str(first.evolution_run_path)},
                        max_generations=4,
                    ),
                ),
            ).run(candidate_factory=second_factory)
            second_doc = json.loads(second.evolution_run_path.read_text(encoding="utf-8"))

            self.assertEqual([generation["generation_index"] for generation in first_doc["generations"]], [0, 1, 2])
            self.assertEqual([generation["generation_index"] for generation in second_doc["generations"]], [0, 1, 2, 3])
            self.assertEqual(len(first_factory.calls), 2)
            self.assertEqual(len(second_factory.calls), 1)
            self.assertEqual(first_doc["generations"][0], second_doc["generations"][0])
            self.assertEqual(
                second_doc["generations"][3]["parent_refs"][0]["candidate_id"],
                second_doc["generations"][2]["survivor_refs"][0]["candidate_id"],
            )
            self.assertEqual(second_doc["metadata"]["workflow"]["relationship"]["type"], "continuation")

    def test_changed_evolution_configuration_requires_explicit_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="source-run",
                        campaign_type="evolutionary",
                        scientific_execution=("generate", "analyze", "evolve"),
                        max_generations=2,
                    ),
                ),
            ).run(candidate_factory=RecordingFactory())

            with self.assertRaisesRegex(WorkflowConfigError, "branch required"):
                WorkflowRunner(
                    WorkflowConfig.from_mapping(
                        _workflow_mapping(
                            root / "out",
                            run_id="source-run",
                            campaign_type="evolutionary",
                            scientific_execution=("evolve",),
                            artifacts={"evolution_run": str(source.evolution_run_path)},
                            max_generations=3,
                            keep=2,
                        ),
                    ),
                ).run(candidate_factory=RecordingFactory())

            branch = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "out",
                        run_id="derived-run",
                        campaign_type="evolutionary",
                        scientific_execution=("evolve",),
                        artifacts={"evolution_run": str(source.evolution_run_path)},
                        max_generations=3,
                        keep=2,
                        resume_mode="branch",
                    ),
                ),
            ).run(candidate_factory=RecordingFactory())

            source_doc = json.loads(source.evolution_run_path.read_text(encoding="utf-8"))
            branch_doc = json.loads(branch.evolution_run_path.read_text(encoding="utf-8"))
            relationship = branch_doc["metadata"]["workflow"]["relationship"]
            self.assertEqual(source_doc["evolution_run_id"], "source-run-evolution")
            self.assertEqual(len(source_doc["generations"]), 2)
            self.assertEqual(branch_doc["evolution_run_id"], "derived-run-evolution")
            self.assertEqual(relationship["type"], "branch")
            self.assertEqual(relationship["source_evolution_run_id"], "source-run-evolution")
            self.assertEqual(relationship["source_generation"], 1)
            self.assertEqual(branch_doc["generations"][0], source_doc["generations"][0])

    def test_generation_constraints_roundtrip_and_evolution_resume_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = _workflow_mapping(
                root / "out",
                run_id="constraint-config",
                campaign_type="evolutionary",
                scientific_execution=("generate", "analyze", "evolve"),
                max_generations=2,
                constraints=_linear_constraints(),
            )
            config = WorkflowConfig.from_mapping(mapping)

            self.assertEqual(
                WorkflowConfig.from_mapping(config.to_dict()).generation.constraints.to_dict(),
                config.generation.constraints.to_dict(),
            )

            factory = InsertGateMutationFactory(
                constraints=config.generation.constraints,
                created_at=CREATED_AT,
            )
            result = WorkflowRunner(config).run(candidate_factory=factory)

            first_doc = json.loads(result.evolution_run_path.read_text(encoding="utf-8"))
            self.assertEqual([generation["generation_index"] for generation in first_doc["generations"]], [0, 1])
            self.assertEqual(
                first_doc["configuration"]["mutation_policy"]["structural_constraints"],
                config.generation.constraints.to_dict(),
            )

            resumed_config = WorkflowConfig.from_mapping(
                _workflow_mapping(
                    root / "out",
                    run_id="constraint-config",
                    campaign_type="evolutionary",
                    scientific_execution=("evolve",),
                    artifacts={"evolution_run": str(result.evolution_run_path)},
                    max_generations=3,
                    constraints=_linear_constraints(),
                ),
            )
            resumed = WorkflowRunner(resumed_config).run(
                candidate_factory=InsertGateMutationFactory(
                    constraints=resumed_config.generation.constraints,
                    created_at=CREATED_AT,
                ),
            )
            resumed_doc = json.loads(resumed.evolution_run_path.read_text(encoding="utf-8"))
            self.assertEqual([generation["generation_index"] for generation in resumed_doc["generations"]], [0, 1, 2])
            self.assertEqual(resumed_doc["metadata"]["workflow"]["relationship"]["type"], "continuation")

    def test_changed_generation_constraints_require_explicit_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_mapping = _workflow_mapping(
                root / "out",
                run_id="constraint-source",
                campaign_type="evolutionary",
                scientific_execution=("generate", "analyze", "evolve"),
                max_generations=2,
                constraints=_linear_constraints(),
            )
            source_config = WorkflowConfig.from_mapping(source_mapping)
            source = WorkflowRunner(source_config).run(
                candidate_factory=InsertGateMutationFactory(
                    constraints=source_config.generation.constraints,
                    created_at=CREATED_AT,
                ),
            )

            changed = _linear_constraints()
            changed["connectivity"] = {
                "n_qubits": 4,
                "edges": [[0, 1], [2, 3]],
            }
            with self.assertRaisesRegex(WorkflowConfigError, "branch required"):
                WorkflowRunner(
                    WorkflowConfig.from_mapping(
                        _workflow_mapping(
                            root / "out",
                            run_id="constraint-source",
                            campaign_type="evolutionary",
                            scientific_execution=("evolve",),
                            artifacts={"evolution_run": str(source.evolution_run_path)},
                            max_generations=3,
                            constraints=changed,
                        ),
                    ),
                ).run(
                    candidate_factory=InsertGateMutationFactory(
                        constraints=ConstraintSet.from_mapping(changed),
                        created_at=CREATED_AT,
                    ),
                )

    def test_metric_callables_propagate_into_evolution_generation_analysis(self) -> None:
        """Explicit metric callables must survive every evolutionary analysis call."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = _workflow_mapping(
                root / "out",
                run_id="metric-callables-evolution",
                campaign_type="evolutionary",
                scientific_execution=("generate", "analyze", "evolve"),
                max_generations=2,
            )
            runner = WorkflowRunner(WorkflowConfig.from_mapping(mapping))

            def explicit_state_callable(parameters):
                return parameters

            metric_callables = {"sentinel-candidate": explicit_state_callable}

            with mock.patch.object(
                runner,
                "_run_analysis",
                wraps=runner._run_analysis,
            ) as run_analysis:
                runner.run(
                    candidate_factory=RecordingFactory(),
                    metric_callables=metric_callables,
                )

            self.assertGreaterEqual(run_analysis.call_count, 2)
            received = [
                call.kwargs.get("metric_callables")
                for call in run_analysis.call_args_list
            ]
            self.assertTrue(
                all(value is metric_callables for value in received),
                msg=f"metric_callables propagation mismatch: {received!r}",
            )

    def test_evolution_continue_rejects_changed_analyzer_scientific_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = (
                ("materialization", lambda mapping: mapping["analyzer"].update({"materialization": {"enabled": True}})),
                ("permissions", lambda mapping: mapping["analyzer"].update({"permissions": {"allow_expensive_metrics": False, "allow_qnode_execution": True}})),
                ("analyzer-random-seed", lambda mapping: mapping["analyzer"].update({"random_seed": 23})),
            )

            for case_name, mutate in cases:
                with self.subTest(case=case_name):
                    case_root = root / case_name
                    run_id = f"fingerprint-{case_name}"
                    source = WorkflowRunner(
                        WorkflowConfig.from_mapping(
                            _workflow_mapping(
                                case_root / "out",
                                run_id=run_id,
                                campaign_type="evolutionary",
                                scientific_execution=("generate", "analyze", "evolve"),
                                max_generations=1,
                            ),
                        ),
                    ).run(candidate_factory=RecordingFactory())

                    continue_mapping = _workflow_mapping(
                        case_root / "out",
                        run_id=run_id,
                        campaign_type="evolutionary",
                        scientific_execution=("evolve",),
                        artifacts={"evolution_run": str(source.evolution_run_path)},
                        max_generations=2,
                    )
                    mutate(continue_mapping)

                    with self.assertRaisesRegex(WorkflowConfigError, "branch required"):
                        WorkflowRunner(
                            WorkflowConfig.from_mapping(continue_mapping),
                        ).run(candidate_factory=RecordingFactory())



if __name__ == "__main__":
    unittest.main()

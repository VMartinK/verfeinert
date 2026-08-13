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
    StagedPackageJsonExportConfig,
    write_canonical_staged_package_json,
)
from verfeinert.workflow import WorkflowConfig, WorkflowConfigError, WorkflowRunner


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
            "mutation_policy": {
                "policy_id": "phase102-mutation",
                "variants_per_parent": 1,
                "recipes": [{"recipe_id": "insert-test", "mutation_type": "insert"}],
            },
        },
    }
    if artifacts is not None:
        mapping["artifacts"] = artifacts
    return mapping


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


if __name__ == "__main__":
    unittest.main()

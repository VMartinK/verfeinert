"""Workflow manifest and traceability export tests."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.core.hashing import stable_hash
from verfeinert.workflow import (
    TRACEABILITY_COLUMNS,
    WORKFLOW_MANIFEST_SCHEMA_VERSION,
    WORKFLOW_TRACEABILITY_SCHEMA_VERSION,
    WorkflowConfig,
    WorkflowRunner,
)


CREATED_AT = "2026-08-06T00:00:00Z"
HASH = "5" * 64


def _workflow_mapping(
    output_root: Path,
    *,
    run_id: str,
    campaign_type: str = "evolutionary",
    scientific_execution=("generate", "analyze", "evolve"),
    postprocessing=("ranking",),
    artifacts: dict | None = None,
    max_generations: int = 1,
) -> dict:
    mapping = {
        "run": {
            "run_id": run_id,
            "created_at": CREATED_AT,
            "random_seed": 31,
        },
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": campaign_type,
            "scientific_execution": list(scientific_execution),
            "postprocessing": list(postprocessing),
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "manifest",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {
                "reference_bounds": {
                    "parameter_count": {"min": 0, "max": 8},
                    "depth": {"min": 0, "max": 20},
                    "two_qubit_operation_count": {"min": 0, "max": 6},
                },
            },
            "ranking": {
                "score_components": {"cost.structural_cost": 1.0},
                "combination": "weighted_sum",
                "ascending": True,
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "manifest-selection",
            "metric_name": "structural_cost",
            "keep": 1,
            "direction": "minimize",
            "max_generations": max_generations,
            "patience": 10,
            "mutation_policy": {
                "policy_id": "manifest-mutation",
                "variants_per_parent": 1,
                "recipes": [{"recipe_id": "lineage", "mutation_type": "insert"}],
            },
        },
    }
    if artifacts is not None:
        mapping["artifacts"] = artifacts
    return mapping


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class _LineageFactory:
    def __call__(self, request, parent):
        child = copy.deepcopy(dict(parent))
        child["candidate_id"] = f"{request.parent_candidate_id}-g{request.generation_index:03d}"
        child["identity"] = {
            "structural_hash": HASH,
            "lineage_hash": HASH,
            "hash_schema_version": "verfeinert.candidate_hash.v1",
        }
        child["lineage"] = {
            "generation": request.generation_index,
            "root_candidate_id": (
                request.root_candidate_id
                or parent["lineage"].get("root_candidate_id")
                or parent["candidate_id"]
            ),
            "parent_candidate_id": request.parent_candidate_id,
            "mutation": {
                "mutation_id": request.request_id.replace(":", "-"),
                "type": request.mutation_type,
                "source_candidate_id": request.parent_candidate_id,
                "operation": "manifest-test",
                "parameters": dict(request.parameters),
            },
        }
        return child


class WorkflowManifestTests(unittest.TestCase):
    def test_manifest_and_traceability_exports_are_written_for_full_workflow(self) -> None:
        with TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(Path(tmp) / "out", run_id="manifest-full"),
                ),
            ).run()

            self.assertTrue(result.manifest_path.is_file())
            self.assertTrue(result.traceability_json_path.is_file())
            self.assertTrue(result.traceability_csv_path.is_file())
            self.assertEqual(
                result.to_dict()["traceability_csv_path"],
                str(result.traceability_csv_path),
            )

            manifest = _read_json(result.manifest_path)
            self.assertEqual(manifest["schema_version"], WORKFLOW_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(manifest["run_id"], "manifest-full")
            self.assertEqual(manifest["stages"]["status"], "completed")
            self.assertEqual(
                manifest["stages"]["requested"],
                {
                    "scientific": ["generate", "analyze", "evolve"],
                    "postprocessing": ["ranking"],
                },
            )
            self.assertEqual(
                manifest["stages"]["completed"],
                ["generate", "analyze", "evolve", "ranking"],
            )
            self.assertEqual(manifest["final_stopping_reason"], "max_generations_reached")
            self.assertIsInstance(manifest["config"]["hash"], str)
            self.assertEqual(
                manifest["config"]["hash"],
                stable_hash(manifest["config"]["snapshot"]),
            )
            self.assertEqual(manifest["seed_policy"]["workflow_seed"], 31)
            self.assertEqual(manifest["execution"]["mode"], "sequential")
            self.assertEqual(
                manifest["artifacts"]["paths"]["traceability_json_path"],
                str(result.traceability_json_path),
            )
            self.assertEqual(
                manifest["artifacts"]["paths"]["evolution_run_path"],
                str(result.evolution_run_path),
            )

            traceability = _read_json(result.traceability_json_path)
            self.assertEqual(
                traceability["schema_version"],
                WORKFLOW_TRACEABILITY_SCHEMA_VERSION,
            )
            self.assertEqual(traceability["columns"], list(TRACEABILITY_COLUMNS))
            self.assertEqual(len(traceability["rows"]), 1)
            row = traceability["rows"][0]
            self.assertEqual(row["run_id"], "manifest-full")
            self.assertEqual(row["candidate_id"], "manifest-a02-l1")
            self.assertEqual(row["analysis_result_id"], result.analysis_result_ids[0])
            self.assertIsNotNone(row["structural_hash"])
            self.assertIsNotNone(row["lineage_hash"])
            self.assertEqual(row["generation"], 0)
            self.assertIsNotNone(row["structural_cost"])
            self.assertTrue(row["survivor"])
            self.assertTrue(row["archive"])
            self.assertFalse(row["rejected"])
            self.assertEqual(row["final_stopping_reason"], "max_generations_reached")

            csv_rows = _csv_rows(result.traceability_csv_path)
            self.assertEqual(list(csv_rows[0].keys()), list(TRACEABILITY_COLUMNS))
            self.assertEqual(csv_rows[0]["candidate_id"], "manifest-a02-l1")
            self.assertEqual(csv_rows[0]["survivor"], "True")

    def test_generate_only_traceability_does_not_fabricate_missing_metrics(self) -> None:
        with TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="manifest-generate-only",
                        campaign_type="individual",
                        scientific_execution=("generate",),
                        postprocessing=(),
                    ),
                ),
            ).run()

            manifest = _read_json(result.manifest_path)
            traceability = _read_json(result.traceability_json_path)
            row = traceability["rows"][0]

            self.assertEqual(manifest["stages"]["completed"], ["generate"])
            self.assertIsNone(manifest["final_stopping_reason"])
            self.assertEqual(row["candidate_id"], "manifest-a02-l1")
            self.assertIsNone(row["analysis_result_id"])
            self.assertIsNone(row["expressibility"])
            self.assertIsNone(row["trainability"])
            self.assertIsNone(row["structural_cost"])
            self.assertFalse(row["survivor"])
            self.assertFalse(row["archive"])
            self.assertIsNone(row["final_stopping_reason"])

            csv_row = _csv_rows(result.traceability_csv_path)[0]
            self.assertEqual(csv_row["analysis_result_id"], "")
            self.assertEqual(csv_row["expressibility"], "")
            self.assertEqual(csv_row["structural_cost"], "")
            self.assertEqual(csv_row["survivor"], "False")

    def test_multi_generation_traceability_includes_child_lineage(self) -> None:
        with TemporaryDirectory() as tmp:
            result = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        Path(tmp) / "out",
                        run_id="manifest-lineage",
                        max_generations=2,
                    ),
                ),
            ).run(candidate_factory=_LineageFactory())

            traceability = _read_json(result.traceability_json_path)
            rows = traceability["rows"]
            child_id = "manifest-a02-l1-g001"
            by_id = {row["candidate_id"]: row for row in rows}

            self.assertEqual([row["candidate_id"] for row in rows], ["manifest-a02-l1", child_id])
            self.assertEqual(by_id[child_id]["generation"], 1)
            self.assertEqual(by_id[child_id]["parent_candidate_id"], "manifest-a02-l1")
            self.assertIsNotNone(by_id[child_id]["analysis_result_id"])
            self.assertIsNotNone(by_id[child_id]["structural_cost"])
            self.assertTrue(by_id[child_id]["survivor"])
            self.assertTrue(by_id[child_id]["archive"])
            self.assertEqual(
                by_id[child_id]["final_stopping_reason"],
                "max_generations_reached",
            )

    def test_reused_evolution_source_feeds_manifest_and_traceability_exports(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(root / "source", run_id="manifest-source"),
                ),
            ).run()

            reused = WorkflowRunner(
                WorkflowConfig.from_mapping(
                    _workflow_mapping(
                        root / "reuse",
                        run_id="manifest-reuse",
                        scientific_execution=(),
                        postprocessing=(),
                        artifacts={"evolution_run": str(source.evolution_run_path)},
                    ),
                ),
            ).run()

            manifest = _read_json(reused.manifest_path)
            traceability = _read_json(reused.traceability_json_path)
            row = traceability["rows"][0]

            self.assertEqual(reused.executed_operations, ())
            self.assertEqual(
                {artifact["kind"] for artifact in reused.reused_artifacts},
                {"evolution_run"},
            )
            self.assertEqual(
                manifest["artifacts"]["paths"]["evolution_run_path"],
                str(source.evolution_run_path),
            )
            self.assertEqual(manifest["final_stopping_reason"], "max_generations_reached")
            self.assertEqual(row["candidate_id"], "manifest-a02-l1")
            self.assertEqual(row["analysis_result_id"], source.analysis_result_ids[0])
            self.assertEqual(row["final_stopping_reason"], "max_generations_reached")
            self.assertIsNotNone(row["structural_cost"])


if __name__ == "__main__":
    unittest.main()

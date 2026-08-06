"""Validation tests for canonical Verfeinert data model schemas."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, RefResolver
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_ROOT = PROJECT_ROOT / "schemas"
SCHEMA_FIXTURES_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "schemas"

SCHEMA_FILES = {
    "candidate": SCHEMAS_ROOT / "candidate.schema.json",
    "experiment": SCHEMAS_ROOT / "experiment.schema.json",
    "staged_package": SCHEMAS_ROOT / "staged_package.schema.json",
    "analysis_result": SCHEMAS_ROOT / "analysis_result.schema.json",
    "evolution_run": SCHEMAS_ROOT / "evolution_run.schema.json",
}

FORBIDDEN_TOKENS = (
    "Thesis_Data_Processing",
    "/analysis_results/",
    "\\analysis_results\\",
    "analysis_exports",
    "python/analysis/analysis_results",
    "/home/",
    "TFG",
    "CX01",
    "CX_01",
    "MIXT",
    "legacy_import",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_store() -> dict[str, dict]:
    schemas = {name: _read_json(path) for name, path in SCHEMA_FILES.items()}
    return {
        schema["$id"]: schema
        for schema in schemas.values()
    }


def _validator(schema_name: str) -> Draft202012Validator:
    schema = _read_json(SCHEMA_FILES[schema_name])
    store = _schema_store()
    resolver = RefResolver.from_schema(schema, store=store)
    return Draft202012Validator(schema, resolver=resolver)


def _candidate_example() -> dict:
    return _read_json(SCHEMA_FIXTURES_ROOT / "candidate_example.json")


def _candidate_ref(*, include_lineage_hash: bool = True) -> dict:
    candidate = _candidate_example()
    ref = {
        "candidate_id": candidate["candidate_id"],
        "candidate_uri": "relative://candidates/reference-a02-l1-parent.json",
        "structural_hash": candidate["identity"]["structural_hash"],
    }
    if include_lineage_hash:
        ref["lineage_hash"] = candidate["identity"]["lineage_hash"]
    return ref


def _analysis_result_ref() -> dict:
    return {
        "analysis_result_id": "analysis-result-001",
        "candidate_id": _candidate_ref()["candidate_id"],
        "analysis_result_uri": "relative://analysis/analysis-result-001.json",
        "schema_version": "verfeinert.analysis_result.v1",
        "hash": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "metadata": {
            "source": "schema-test"
        }
    }


class DataModelSchemaTests(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for name, path in SCHEMA_FILES.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(_read_json(path))

    def test_candidate_example_validates(self) -> None:
        _validator("candidate").validate(_candidate_example())

    def test_experiment_yaml_example_validates(self) -> None:
        payload = yaml.safe_load((SCHEMA_FIXTURES_ROOT / "experiment_example.yaml").read_text(encoding="utf-8"))
        _validator("experiment").validate(payload)

    def test_staged_package_minimal_document_validates(self) -> None:
        candidate = _candidate_example()
        document = {
            "schema_version": "verfeinert.staged_package.v1",
            "package_id": "reference-package-001",
            "manifest": {
                "package_kind": "candidate_package",
                "created_at": "2026-08-04T00:00:00Z",
                "producer": "verfeinert.ansatz_generator",
                "candidate_count": 1,
                "schema_versions": {
                    "candidate": "verfeinert.candidate.v1"
                },
                "execution_flags": {
                    "qnodes_executed": False,
                    "scientific_metrics_executed": False,
                    "generated_callables_imported": False
                }
            },
            "candidates": [candidate],
            "artifacts": [
                {
                    "artifact_id": "candidate-json",
                    "kind": "metadata",
                    "uri": "relative://package/metadata.json",
                    "format": "json"
                }
            ],
            "provenance": {
                "created_at": "2026-08-04T00:00:00Z",
                "source": "schema-test",
                "software_version": "0.0.0",
                "git_commit": None,
                "input_hashes": {}
            }
        }
        _validator("staged_package").validate(document)

    def test_analysis_result_minimal_document_validates(self) -> None:
        document = {
            "schema_version": "verfeinert.analysis_result.v1",
            "analysis_result_id": "analysis-result-001",
            "candidate_ref": _candidate_ref(include_lineage_hash=False),
            "metrics": [
                {
                    "metric_id": "metric-structural-cost",
                    "name": "structural_cost",
                    "status": "computed",
                    "value": 3.0
                }
            ],
            "cost": {
                "structural_cost": 3.0,
                "operation_count": 3,
                "two_qubit_operation_count": 1,
                "parameter_count": 2
            },
            "classifications": [
                {
                    "classification_id": "classification-pareto",
                    "name": "pareto_status",
                    "label": "undetermined"
                }
            ],
            "provenance": {
                "created_at": "2026-08-04T00:00:00Z",
                "analyzer": "verfeinert.ansatz_analyzer",
                "software_version": "0.0.0",
                "git_commit": None,
                "execution": {
                    "qnodes_executed": False
                }
            }
        }
        _validator("analysis_result").validate(document)

    def test_evolution_run_minimal_document_validates(self) -> None:
        candidate_ref = _candidate_ref()
        document = {
            "schema_version": "verfeinert.evolution_run.v1",
            "evolution_run_id": "evolution-run-001",
            "run_metadata": {
                "created_at": "2026-08-04T00:00:00Z",
                "status": "completed",
                "software_version": "0.0.0",
                "git_commit": None
            },
            "configuration": {
                "experiment_ref": {
                    "document_id": "reference-single-analysis",
                    "uri": "relative://experiments/reference-single-analysis.yaml",
                    "schema_version": "verfeinert.experiment.v1"
                },
                "random_seed": 12345,
                "execution": {
                    "mode": "sequential",
                    "scope": "candidate",
                    "worker_count": 1
                },
                "mutation_policy": {
                    "mode": "structural"
                },
                "selection_policy": {
                    "mode": "reference"
                }
            },
            "generations": [
                {
                    "generation_index": 0,
                    "candidate_refs": [candidate_ref],
                    "survivor_refs": [candidate_ref],
                    "archive_refs": [candidate_ref],
                    "events": []
                }
            ],
            "provenance": {
                "created_at": "2026-08-04T00:00:00Z",
                "source": "schema-test",
                "input_hashes": {}
            }
        }
        _validator("evolution_run").validate(document)

    def test_evolution_run_reference_refinement_validates(self) -> None:
        candidate_ref = _candidate_ref()
        analysis_ref = _analysis_result_ref()
        document = {
            "schema_version": "verfeinert.evolution_run.v1",
            "evolution_run_id": "evolution-run-refs-001",
            "run_metadata": {
                "created_at": "2026-08-04T00:00:00Z",
                "status": "completed",
                "software_version": "0.0.0",
                "git_commit": None,
                "execution": {
                    "evolver_executed_metrics": False,
                    "qnodes_executed_by_evolver": False,
                    "analysis_requested": True,
                    "analysis_results_ingested": True,
                    "selection_executed": True,
                    "plots_generated_by_evolver": False
                }
            },
            "configuration": {
                "random_seed": 12345,
                "execution": {
                    "mode": "sequential"
                },
                "mutation_policy": {
                    "policy_id": "schema-mutation-policy"
                },
                "selection_policy": {
                    "policy_id": "schema-selection-policy"
                },
                "stopping_policy": {
                    "max_generations": 1
                }
            },
            "generations": [
                {
                    "generation_index": 1,
                    "parent_refs": [candidate_ref],
                    "candidate_refs": [candidate_ref],
                    "analysis_result_refs": [analysis_ref],
                    "survivor_refs": [candidate_ref],
                    "rejected_refs": [],
                    "archive_refs": [candidate_ref],
                    "events": [
                        {
                            "event_type": "analysis_result_available",
                            "candidate_id": candidate_ref["candidate_id"],
                            "analysis_result_id": analysis_ref["analysis_result_id"],
                            "status": "ingested"
                        },
                        {
                            "event_type": "selection_completed",
                            "policy_id": "schema-selection-policy",
                            "status": "completed"
                        }
                    ]
                }
            ],
            "provenance": {
                "created_at": "2026-08-04T00:00:00Z",
                "source": "schema-test",
                "input_hashes": {}
            }
        }
        _validator("evolution_run").validate(document)

    def test_evolution_run_events_require_event_type(self) -> None:
        candidate_ref = _candidate_ref()
        document = {
            "schema_version": "verfeinert.evolution_run.v1",
            "evolution_run_id": "evolution-run-bad-event",
            "run_metadata": {
                "created_at": "2026-08-04T00:00:00Z",
                "status": "planned"
            },
            "configuration": {
                "random_seed": None,
                "execution": {}
            },
            "generations": [
                {
                    "generation_index": 0,
                    "candidate_refs": [candidate_ref],
                    "survivor_refs": [],
                    "archive_refs": [],
                    "events": [
                        {
                            "status": "missing-event-type"
                        }
                    ]
                }
            ],
            "provenance": {
                "created_at": "2026-08-04T00:00:00Z",
                "source": "schema-test",
                "input_hashes": {}
            }
        }
        with self.assertRaises(Exception):
            _validator("evolution_run").validate(document)

    def test_schemas_and_examples_do_not_contain_local_or_campaign_specific_tokens(self) -> None:
        checked_files = [
            *SCHEMAS_ROOT.glob("*.json"),
            *SCHEMA_FIXTURES_ROOT.glob("*.json"),
            *SCHEMA_FIXTURES_ROOT.glob("*.yaml"),
            *SCHEMA_FIXTURES_ROOT.glob("*.yml"),
        ]
        violations: list[str] = []
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

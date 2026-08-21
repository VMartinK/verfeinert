"""v0.4.0 reproducibility equivalence gate for workflow orchestration."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/verfeinert-test-mplconfig")

from verfeinert.workflow import WorkflowConfig, WorkflowResult, WorkflowRunner


CREATED_AT = "2026-08-21T00:00:00Z"
RUN_ID = "cp15-reproducibility"
STRUCTURAL_BOUNDS = {
    "parameter_count": {"min": 1, "max": 96},
    "depth": {"min": 1, "max": 192},
    "two_qubit_operation_count": {"min": 0, "max": 64},
}


def test_independent_sequential_runs_are_canonical_equivalent(tmp_path: Path) -> None:
    first = _run_workflow(tmp_path / "sequential-a")
    second = _run_workflow(tmp_path / "sequential-b")

    _assert_canonical_equivalent(first, second)


def test_parallel_workflow_matches_sequential_science_state(tmp_path: Path) -> None:
    sequential = _run_workflow(tmp_path / "sequential")
    parallel = _run_workflow(
        tmp_path / "parallel",
        execution={
            "mode": "multiprocessing",
            "parallelize_candidates": True,
            "worker_count": 2,
        },
    )

    _assert_canonical_equivalent(sequential, parallel)


def test_checkpoint_resume_matches_uninterrupted_final_state(tmp_path: Path) -> None:
    continuous = _run_workflow(tmp_path / "continuous")

    staged = _run_workflow(
        tmp_path / "resumed",
        scientific_execution=("generate", "analyze"),
        postprocessing=(),
        checkpoint=True,
    )
    assert staged.checkpoint_path is not None

    resumed = _run_workflow(
        tmp_path / "resumed",
        scientific_execution=("evolve",),
        resume_checkpoint=staged.checkpoint_path,
    )

    _assert_canonical_equivalent(continuous, resumed)
    assert {artifact["kind"] for artifact in resumed.reused_artifacts} >= {
        "workflow_checkpoint",
    }


def _run_workflow(
    output_root: Path,
    *,
    execution: dict[str, Any] | None = None,
    scientific_execution: tuple[str, ...] = ("generate", "analyze", "evolve"),
    postprocessing: tuple[str, ...] = ("ranking", "pareto"),
    checkpoint: bool = False,
    resume_checkpoint: Path | None = None,
) -> WorkflowResult:
    return WorkflowRunner(
        WorkflowConfig.from_mapping(
            _workflow_mapping(
                output_root,
                execution=execution,
                scientific_execution=scientific_execution,
                postprocessing=postprocessing,
                checkpoint=checkpoint,
                resume_checkpoint=resume_checkpoint,
            ),
        ),
    ).run()


def _workflow_mapping(
    output_root: Path,
    *,
    execution: dict[str, Any] | None,
    scientific_execution: tuple[str, ...],
    postprocessing: tuple[str, ...],
    checkpoint: bool,
    resume_checkpoint: Path | None,
) -> dict[str, Any]:
    workflow: dict[str, Any] = {
        "campaign_type": "evolutionary",
        "scientific_execution": list(scientific_execution),
        "postprocessing": list(postprocessing),
        "checkpoint": {"enabled": checkpoint},
        "resume": {"mode": "continue"},
        "analysis_result_reuse": {"enabled": True},
    }
    if resume_checkpoint is not None:
        workflow["resume"]["checkpoint"] = str(resume_checkpoint)
    return {
        "run": {
            "run_id": RUN_ID,
            "created_at": CREATED_AT,
            "random_seed": 12345,
        },
        "paths": {"output_root": str(output_root)},
        "execution": execution or {},
        "workflow": workflow,
        "generation": {
            "family": "sanz19",
            "template_ids": ["A04", "A07"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "cp15",
            "source_label": "cp15_reproducibility_gate",
            "metadata": {"gate": "cp15"},
        },
        "analyzer": {
            "selected_metrics": [
                "structural_cost",
                "expressibility",
                "trainability",
            ],
            "permissions": {
                "allow_expensive_metrics": True,
                "allow_qnode_execution": True,
            },
            "materialization": {
                "enabled": True,
                "backend": "pennylane",
                "device": "default.qubit",
                "interface": "autograd",
                "diff_method": "best",
            },
            "structural_cost": {
                "reference_id": "cp15-reference",
                "reference_bounds": STRUCTURAL_BOUNDS,
                "component_weights": {
                    "parameter_count": 1,
                    "depth": 1,
                    "two_qubit_operation_count": 1,
                },
                "allow_operation_count_as_depth_proxy": True,
            },
            "metric_configs": {
                "expressibility": {
                    "n_pairs": 2,
                    "n_bins": 3,
                    "rng_seed": 12345,
                },
                "trainability": {
                    "n_repeats": 1,
                    "rng_seed": 12345,
                },
            },
            "ranking": {
                "score_components": {
                    "expressibility": 1,
                    "trainability": 1,
                },
                "combination": "product",
                "ascending": False,
            },
            "pareto": {
                "objectives": [
                    {"metric_name": "expressibility", "direction": "maximize"},
                    {"metric_name": "trainability", "direction": "maximize"},
                ],
                "cost_thresholds": [1.0, 0.2],
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "cp15-fitness-selection",
            "metric_name": "structural_cost",
            "direction": "minimize",
            "objectives": [
                {"name": "expressibility", "direction": "maximize"},
                {"name": "trainability", "direction": "maximize"},
            ],
            "thresholds": {"structural_cost": 10.0},
            "threshold_direction": "at_most",
            "strict_ties": True,
            "keep": 1,
            "max_generations": 3,
            "initial_parent_policy": "all_generation_zero_candidates",
            "offspring_deduplication": {
                "enabled": True,
                "key": "structural_hash",
                "keep": "first",
            },
            "mutation_policy": {
                "policy_id": "cp15-insert-schedule",
                "variants_per_parent": 1,
                "candidate_factory": {"type": "canonical"},
                "recipes": [
                    {
                        "recipe_id": "crx_insert",
                        "mutation_type": "insert",
                        "parameters": {
                            "gate": "crx",
                            "edge": [0, 1],
                            "insertion_strategy": "before_first_multiqubit",
                            "candidate_id_template": (
                                "{root_candidate_id}_g{generation:03d}-"
                                "{recipe_id}-v{variant_ordinal:03d}"
                            ),
                        },
                    },
                ],
                "generation_overrides": {
                    "2": {
                        "recipes": [
                            {
                                "recipe_id": "crz_insert",
                                "mutation_type": "insert",
                                "parameters": {
                                    "gate": "crz",
                                    "edge": [0, 1],
                                    "insertion_strategy": "before_first_multiqubit",
                                    "candidate_id_template": (
                                        "{root_candidate_id}_g{generation:03d}-"
                                        "{recipe_id}-v{variant_ordinal:03d}"
                                    ),
                                },
                            },
                        ],
                    },
                },
            },
        },
        "metadata": {"gate": "cp15-reproducibility"},
    }


def _assert_canonical_equivalent(left: WorkflowResult, right: WorkflowResult) -> None:
    left_signature = _semantic_signature(left)
    right_signature = _semantic_signature(right)
    assert left_signature == right_signature
    assert left_signature["evolution"]["final_stopping_decision"]["reason"] == (
        "max_generations_reached"
    )
    assert [item["generation_index"] for item in left_signature["evolution"]["generations"]] == [
        0,
        1,
        2,
    ]
    assert all(
        "threshold_states" in item["stopping_state"]
        for item in left_signature["evolution"]["stopping_trajectory"]
    )


def _semantic_signature(result: WorkflowResult) -> dict[str, Any]:
    evolution = _read_json(_require_path(result.evolution_run_path))
    analysis_documents = _analysis_documents_from_evolution(evolution)
    return {
        "candidate_identity": _candidate_identity_signature(evolution),
        "metrics": _metric_signature(analysis_documents),
        "ranking": _ranking_signature(_read_json(_require_path(result.ranking_json_path))),
        "pareto": _pareto_signature(_read_json(_require_path(result.pareto_json_path))),
        "evolution": _evolution_signature(evolution),
    }


def _analysis_documents_from_evolution(evolution: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    documents: dict[str, dict[str, Any]] = {}
    for generation in evolution["generations"]:
        for ref in generation.get("analysis_result_refs", ()):
            uri = ref.get("analysis_result_uri")
            assert uri, f"missing AnalysisResult URI for {ref['analysis_result_id']}"
            document = _read_json(Path(uri))
            documents[document["analysis_result_id"]] = document
    return tuple(
        documents[key]
        for key in sorted(
            documents,
            key=lambda analysis_result_id: (
                documents[analysis_result_id]["candidate_ref"]["candidate_id"],
                analysis_result_id,
            ),
        )
    )


def _candidate_identity_signature(evolution: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    refs: dict[str, dict[str, Any]] = {}
    for generation in evolution["generations"]:
        for role in (
            "candidate_refs",
            "parent_refs",
            "survivor_refs",
            "archive_refs",
            "rejected_refs",
        ):
            for ref in generation.get(role, ()):
                refs.setdefault(
                    ref["candidate_id"],
                    _candidate_ref_signature(ref),
                )
    return tuple(refs[candidate_id] for candidate_id in sorted(refs))


def _metric_signature(documents: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "analysis_result_id": document["analysis_result_id"],
            "candidate_ref": _candidate_ref_signature(document["candidate_ref"]),
            "cost": document["cost"],
            "metrics": tuple(
                _metric_record_signature(metric)
                for metric in sorted(document["metrics"], key=lambda item: item["name"])
            ),
            "candidate_semantics": document.get("metadata", {}).get("candidate_semantics"),
        }
        for document in documents
    )


def _metric_record_signature(metric: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(metric)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("elapsed_seconds", None)
    return payload


def _ranking_signature(ranking: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(ranking)
    payload.pop("created_at", None)
    return payload


def _pareto_signature(pareto: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(pareto)


def _evolution_signature(evolution: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(evolution.get("metadata", {}))
    workflow_metadata = dict(metadata.get("workflow", {}))
    return {
        "schema_version": evolution["schema_version"],
        "evolution_run_id": evolution["evolution_run_id"],
        "status": evolution["run_metadata"]["status"],
        "execution": {
            key: value
            for key, value in evolution["run_metadata"]["execution"].items()
            if key
            in {
                "analysis_requested",
                "analysis_results_ingested",
                "selection_executed",
                "generation_count",
            }
        },
        "configuration": _evolution_configuration_signature(evolution["configuration"]),
        "final_stopping_decision": workflow_metadata.get("final_stopping_decision"),
        "generations": tuple(
            _generation_signature(generation)
            for generation in evolution["generations"]
        ),
        "stopping_trajectory": tuple(
            _stopping_trajectory_entry(generation)
            for generation in evolution["generations"]
        ),
    }


def _evolution_configuration_signature(configuration: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(configuration)
    payload.pop("execution", None)
    return payload


def _generation_signature(generation: dict[str, Any]) -> dict[str, Any]:
    return {
        "generation_index": generation["generation_index"],
        "candidate_refs": tuple(
            _candidate_ref_signature(ref)
            for ref in generation.get("candidate_refs", ())
        ),
        "parent_refs": tuple(
            _candidate_ref_signature(ref)
            for ref in generation.get("parent_refs", ())
        ),
        "analysis_result_refs": tuple(
            _analysis_ref_signature(ref)
            for ref in generation.get("analysis_result_refs", ())
        ),
        "survivor_refs": tuple(
            _candidate_ref_signature(ref)
            for ref in generation.get("survivor_refs", ())
        ),
        "archive_refs": tuple(
            _candidate_ref_signature(ref)
            for ref in generation.get("archive_refs", ())
        ),
        "rejected_refs": tuple(
            _candidate_ref_signature(ref)
            for ref in generation.get("rejected_refs", ())
        ),
        "configuration": copy.deepcopy(generation.get("configuration", {})),
        "events": tuple(
            _generation_event_signature(event)
            for event in generation.get("events", ())
        ),
    }


def _candidate_ref_signature(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ref.get(key)
        for key in ("candidate_id", "structural_hash", "lineage_hash")
        if ref.get(key) is not None
    }


def _analysis_ref_signature(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_result_id": ref["analysis_result_id"],
        "candidate_id": ref["candidate_id"],
        "schema_version": ref["schema_version"],
    }


def _generation_event_signature(event: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(event)
    payload.pop("created_at", None)
    return payload


def _stopping_trajectory_entry(generation: dict[str, Any]) -> dict[str, Any]:
    stopping = dict(generation.get("configuration", {}).get("stopping", {}))
    metadata = dict(stopping.get("metadata", {}))
    return {
        "generation_index": generation["generation_index"],
        "should_stop": stopping.get("should_stop"),
        "reason": stopping.get("reason"),
        "status": stopping.get("status"),
        "stopping_state": metadata.get("stopping_state", {}),
    }


def _require_path(path: Path | None) -> Path:
    assert path is not None
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

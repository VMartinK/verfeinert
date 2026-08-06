"""Run the MIXT-5G reproduction example through public Verfeinert APIs."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from verfeinert.ansatz_evolver import CandidateRef, EvolutionRunState, GenerationRecord, write_evolution_run_json
from verfeinert.ansatz_generator import build_sanz19_candidate_records
from verfeinert.core import read_yaml, write_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = EXAMPLE_ROOT / "config" / "mixt5g_reproduction.yaml"


@dataclass(frozen=True)
class MIXT5GReproductionResult:
    """Artifacts produced by the MIXT-5G reproduction example."""

    generation_results: tuple[object, ...]
    combined_evolution_run_path: Path
    comparison_report_path: Path
    profile: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "profile": self.profile,
            "generation_count": len(self.generation_results),
            "combined_evolution_run_path": str(self.combined_evolution_run_path),
            "comparison_report_path": str(self.comparison_report_path),
            "generation_results": [result.to_dict() for result in self.generation_results],
        }


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the MIXT-5G reproduction YAML configuration."""
    payload = read_yaml(path)
    if not isinstance(payload, Mapping):
        raise ValueError("MIXT-5G reproduction config must be a mapping.")
    return dict(payload)


def build_initial_records(config: Mapping[str, Any], *, profile: str = "smoke") -> list[dict[str, Any]]:
    """Build the configured generation-0 reference parent records."""
    profile_config = dict(config["profiles"][profile])
    records = build_sanz19_candidate_records(
        tuple(profile_config["initial_template_ids"]),
        tuple(int(layer) for layer in profile_config["layers"]),
        n_qubits=int(config["generation"]["n_qubits"]),
    )
    return records[: int(profile_config.get("max_initial_parents") or len(records))]


def run_reproduction(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    output_root_override: str | Path | None = None,
    profile: str = "smoke",
) -> MIXT5GReproductionResult:
    """Execute a bounded MIXT-5G reproduction workflow."""
    config_path = Path(config_path).expanduser().resolve(strict=False)
    config = load_config(config_path)
    output_root = _resolve_output_root(config, config_path=config_path, override=output_root_override)
    profile_config = dict(config["profiles"][profile])
    base_run_id = str(config["run"]["run_id"])

    generation_results = []
    generation_records: list[GenerationRecord] = []
    parent_records = build_initial_records(config, profile=profile)

    generation0 = _run_generation(
        config,
        output_root=output_root,
        run_id=f"{base_run_id}-g000",
        candidate_records=parent_records,
    )
    generation_results.append(generation0)
    generation_records.append(_generation_record_from_result(generation0, generation_index=0, parent_refs=()))
    parent_records = _annotate_records(parent_records, generation0.candidate_ids)

    schedule = tuple(config["mixt5g_campaign"]["mutation_schedule"])
    generations = int(profile_config["generations"])
    parents_per_generation = profile_config.get("parents_per_generation")
    edges = _edges(profile_config.get("edges", "all_valid"), n_qubits=int(config["generation"]["n_qubits"]))
    for generation_index in range(1, generations + 1):
        scheduled = dict(schedule[generation_index - 1])
        selected_parents = parent_records[: int(parents_per_generation or len(parent_records))]
        child_records = [
            _scheduled_child_record(
                parent,
                gate=str(scheduled["mutation_gate"]).lower(),
                mutation_code=str(scheduled["mutation_code"]),
                edge=edges[(variant_index - 1) % len(edges)],
                generation_index=generation_index,
                variant_index=variant_index,
            )
            for variant_index, parent in enumerate(selected_parents, start=1)
        ]
        result = _run_generation(
            config,
            output_root=output_root,
            run_id=f"{base_run_id}-g{generation_index:03d}",
            candidate_records=child_records,
        )
        generation_results.append(result)
        parent_refs = tuple(
            CandidateRef(candidate_id=str(parent["metadata"]["canonical_candidate_id"]))
            for parent in selected_parents
        )
        generation_records.append(
            _generation_record_from_result(
                result,
                generation_index=generation_index,
                parent_refs=parent_refs,
            ),
        )
        survivor_ids = set(result.survivor_candidate_ids)
        parent_records = _annotate_records(
            [
                record
                for record, candidate_id in zip(child_records, result.candidate_ids, strict=True)
                if candidate_id in survivor_ids
            ]
            or child_records[:1],
            [
                candidate_id
                for candidate_id in result.candidate_ids
                if candidate_id in survivor_ids
            ]
            or result.candidate_ids[:1],
        )

    combined_path = _write_combined_evolution(config, output_root=output_root, generations=tuple(generation_records))
    comparison_path = _write_comparison_report(
        config,
        output_root=output_root,
        generation_results=tuple(generation_results),
        combined_evolution_run_path=combined_path,
        profile=profile,
    )
    return MIXT5GReproductionResult(
        generation_results=tuple(generation_results),
        combined_evolution_run_path=combined_path,
        comparison_report_path=comparison_path,
        profile=profile,
    )


def _run_generation(
    config: Mapping[str, Any],
    *,
    output_root: Path,
    run_id: str,
    candidate_records: Sequence[Mapping[str, Any]],
):
    workflow_mapping = dict(config)
    workflow_mapping["run"] = {
        **dict(config["run"]),
        "run_id": run_id,
    }
    workflow_mapping["paths"] = {"output_root": str(output_root)}
    workflow_mapping["generation"] = {
        **dict(config["generation"]),
        "family": "provided",
        "created_at": config["run"]["created_at"],
    }
    workflow_mapping["metadata"] = {
        "example": "mixt5g_reproduction",
        "campaign_reference": config["mixt5g_campaign"],
    }
    return WorkflowRunner(WorkflowConfig.from_mapping(workflow_mapping)).run(
        candidate_records=tuple(candidate_records),
    )


def _scheduled_child_record(
    parent: Mapping[str, Any],
    *,
    gate: str,
    mutation_code: str,
    edge: tuple[int, int],
    generation_index: int,
    variant_index: int,
) -> dict[str, Any]:
    parent_candidate_id = str(parent["metadata"]["canonical_candidate_id"])
    root_candidate_id = str(parent["metadata"].get("canonical_root_candidate_id", parent_candidate_id))
    operations = [copy.deepcopy(dict(operation)) for operation in parent["operations"]]
    insert_at = _after_rotation_block_index(operations)
    operations = operations[:insert_at] + [
        {
            "gate": gate,
            "wires": list(edge),
            "parameterized": gate not in {"cx", "cz", "swap"},
            "params": [],
            "layer": 0,
            "metadata": {
                "source": "mixt5g_reproduction",
                "mutation_code": mutation_code,
                "edge": list(edge),
                "variant_index": variant_index,
            },
        }
    ] + operations[insert_at:]
    operations = _renumber_operations(operations)
    child_label_root = root_candidate_id.removeprefix("mixt5g-")
    child_id = f"{child_label_root}_g{generation_index:03d}-{mutation_code}-v{variant_index:03d}"
    record = {
        **dict(parent),
        "circuit_id": child_id,
        "child_id": child_id,
        "parent_circuit_id": parent_candidate_id,
        "root_circuit_id": root_candidate_id,
        "generation_index": generation_index,
        "mutation_type": "insert",
        "mutation_gate": gate,
        "mutation_id": f"{child_id}-mutation",
        "variant_index": variant_index,
        "operations": operations,
        "metadata": {
            **dict(parent.get("metadata", {})),
            "reproduction": "mixt5g",
            "canonical_parent_candidate_id": parent_candidate_id,
            "canonical_root_candidate_id": root_candidate_id,
            "mutation_type": "insert",
            "mutation_gate": gate,
            "mutation_code": mutation_code,
            "mutation_edge": list(edge),
        },
    }
    record.pop("template_id", None)
    record.pop("ansatz_id", None)
    return record


def _generation_record_from_result(
    result,
    *,
    generation_index: int,
    parent_refs: tuple[CandidateRef, ...],
) -> GenerationRecord:
    source = result.generation_record
    return GenerationRecord(
        generation_index=generation_index,
        parent_refs=parent_refs,
        candidate_refs=source.candidate_refs,
        survivor_refs=source.survivor_refs,
        rejected_refs=source.rejected_refs,
        archive_refs=source.archive_refs,
        analysis_result_refs=source.analysis_result_refs,
        configuration={
            **source.configuration,
            "reproduction_generation_index": generation_index,
        },
        events=source.events,
    )


def _annotate_records(records: Sequence[Mapping[str, Any]], candidate_ids: Sequence[str]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for record, candidate_id in zip(records, candidate_ids, strict=True):
        item = copy.deepcopy(dict(record))
        metadata = dict(item.get("metadata", {}))
        metadata["canonical_candidate_id"] = candidate_id
        metadata.setdefault("canonical_root_candidate_id", candidate_id)
        item["metadata"] = metadata
        annotated.append(item)
    return annotated


def _write_combined_evolution(
    config: Mapping[str, Any],
    *,
    output_root: Path,
    generations: tuple[GenerationRecord, ...],
) -> Path:
    run_id = str(config["run"]["run_id"])
    state = EvolutionRunState(
        evolution_run_id=f"{run_id}-combined-evolution",
        status="completed",
        configuration={
            "random_seed": config["run"]["random_seed"],
            "execution": {"mode": "sequential"},
            "mutation_policy": {
                "schedule": config["mixt5g_campaign"]["mutation_schedule"],
                "source": "mixt5g_reproduction_example",
            },
            "selection_policy": config["mixt5g_campaign"]["selection"],
            "stopping_policy": {
                "max_generations": config["evolver"]["max_generations"],
            },
        },
        generations=generations,
        provenance={
            "created_at": config["run"]["created_at"],
            "source": "mixt5g_reproduction",
            "input_hashes": {},
        },
        metadata={
            "reference_campaign": config["mixt5g_campaign"],
            "bounded_profile": True,
        },
        created_at=config["run"]["created_at"],
        git_commit=None,
        execution_metadata={
            "analysis_requested": True,
            "analysis_results_ingested": True,
            "selection_executed": True,
        },
    )
    return write_evolution_run_json(state, output_root=output_root / run_id / "combined_evolution")


def _write_comparison_report(
    config: Mapping[str, Any],
    *,
    output_root: Path,
    generation_results: tuple[object, ...],
    combined_evolution_run_path: Path,
    profile: str,
) -> Path:
    root = output_root / str(config["run"]["run_id"]) / "comparison"
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "verfeinert.example.mixt5g_reproduction.comparison.v1",
        "profile": profile,
        "reference_campaign": config["mixt5g_campaign"],
        "generation_count": len(generation_results),
        "candidate_counts": [len(result.candidate_ids) for result in generation_results],
        "survivor_candidate_ids_by_generation": [
            list(result.survivor_candidate_ids)
            for result in generation_results
        ],
        "combined_evolution_run_path": str(combined_evolution_run_path),
        "full_metric_reproduction_status": "opt_in_expensive_metrics_not_run_by_smoke_profile",
    }
    return write_json(root / "comparison_report.json", report)


def _after_rotation_block_index(operations: Sequence[Mapping[str, Any]]) -> int:
    for index, operation in enumerate(operations):
        wires = operation.get("wires", operation.get("qubits", ()))
        if len(tuple(wires)) == 2:
            return index
    return len(operations)


def _renumber_operations(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for order, operation in enumerate(operations):
        item = copy.deepcopy(dict(operation))
        item["order"] = order
        metadata = dict(item.get("metadata", {}))
        metadata["order"] = order
        item["metadata"] = metadata
        records.append(item)
    return records


def _edges(raw: object, *, n_qubits: int) -> tuple[tuple[int, int], ...]:
    if raw == "all_valid":
        return tuple((wire, target) for wire in range(n_qubits) for target in range(n_qubits) if wire != target)
    return tuple((int(edge[0]), int(edge[1])) for edge in raw)  # type: ignore[index]


def _resolve_output_root(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    override: str | Path | None,
) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve(strict=False)
    configured = Path(str(config["paths"]["output_root"])).expanduser()
    if configured.is_absolute():
        return configured.resolve(strict=False)
    return (config_path.parent.parent / configured).resolve(strict=False)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the example from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--profile", default="smoke", choices=("smoke", "full"))
    args = parser.parse_args(argv)
    result = run_reproduction(args.config, output_root_override=args.output_root, profile=args.profile)
    print(result.to_dict())


if __name__ == "__main__":
    main()

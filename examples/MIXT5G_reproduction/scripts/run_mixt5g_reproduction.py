"""Run the MIXT-5G reproduction example through public Verfeinert APIs."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from verfeinert.ansatz_generator import InsertGateMutationFactory, build_sanz19_candidate_records
from verfeinert.core import read_yaml, write_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = EXAMPLE_ROOT / "config" / "mixt5g_reproduction.yaml"


@dataclass(frozen=True)
class MIXT5GReproductionResult:
    """Artifacts produced by the MIXT-5G reproduction example."""

    workflow_result: object
    evolution_run_path: Path
    comparison_report_path: Path
    profile: str
    initial_candidate_count: int
    generation_count: int

    @property
    def combined_evolution_run_path(self) -> Path:
        """Compatibility alias for the single generic workflow EvolutionRun."""
        return self.evolution_run_path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "profile": self.profile,
            "generation_count": self.generation_count,
            "initial_candidate_count": self.initial_candidate_count,
            "evolution_run_path": str(self.evolution_run_path),
            "combined_evolution_run_path": str(self.combined_evolution_run_path),
            "comparison_report_path": str(self.comparison_report_path),
            "workflow_result": self.workflow_result.to_dict(),
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


def build_workflow_mapping(
    config: Mapping[str, Any],
    *,
    output_root: Path,
    profile: str,
    scientific_execution: Sequence[str] | None = None,
    postprocessing: Sequence[str] | None = None,
    total_generations: int | None = None,
    evolution_run_source: str | Path | None = None,
) -> dict[str, Any]:
    """Build the canonical public workflow mapping for this example profile."""
    profile_config = dict(config["profiles"][profile])
    requested_scientific = tuple(scientific_execution or config["workflow"]["scientific_execution"])
    requested_postprocessing = tuple(
        config["workflow"].get("postprocessing", ())
        if postprocessing is None
        else postprocessing
    )
    workflow = copy.deepcopy(dict(config))
    workflow["run"] = dict(config["run"])
    workflow["paths"] = {"output_root": str(output_root)}
    workflow["workflow"] = {
        **dict(config["workflow"]),
        "campaign_type": "evolutionary",
        "scientific_execution": list(requested_scientific),
        "postprocessing": list(requested_postprocessing),
        "resume": dict(config["workflow"].get("resume", {"mode": "continue"})),
    }
    workflow["generation"] = {
        **dict(config["generation"]),
        "family": "provided",
        "created_at": config["run"]["created_at"],
    }
    workflow["evolver"] = {
        **copy.deepcopy(dict(config["evolver"])),
        "max_generations": int(total_generations or int(profile_config["generations"]) + 1),
        "mutation_policy": build_mutation_policy(config, profile=profile),
    }
    if evolution_run_source is not None:
        workflow["artifacts"] = {"evolution_run": str(evolution_run_source)}
    workflow["metadata"] = {
        "example": "mixt5g_reproduction",
        "campaign_reference": config["mixt5g_campaign"],
        "profile": profile,
    }
    return workflow


def build_mutation_policy(config: Mapping[str, Any], *, profile: str) -> dict[str, Any]:
    """Convert campaign schedule data into the generic evolver mutation policy."""
    policy = copy.deepcopy(dict(config["evolver"]["mutation_policy"]))
    profile_config = dict(config["profiles"][profile])
    edges = _edges(profile_config.get("edges", "all_valid"), n_qubits=int(config["generation"]["n_qubits"]))
    overrides: dict[str, Any] = {}
    for scheduled in config["mixt5g_campaign"]["mutation_schedule"]:
        generation = int(scheduled["generation"])
        overrides[str(generation)] = {
            "recipes": [_mutation_recipe(scheduled, edges=edges)],
        }
    policy["recipes"] = [overrides["1"]["recipes"][0]]
    policy["generation_overrides"] = overrides
    policy["metadata"] = {
        **dict(policy.get("metadata", {})),
        "profile": profile,
        "edge_count": len(edges),
        "schedule_generations": len(overrides),
    }
    return policy


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
    initial_records = build_initial_records(config, profile=profile)
    workflow_mapping = build_workflow_mapping(config, output_root=output_root, profile=profile)
    workflow_result = WorkflowRunner(WorkflowConfig.from_mapping(workflow_mapping)).run(
        candidate_records=initial_records,
        candidate_factory=InsertGateMutationFactory(),
    )
    if workflow_result.evolution_run_path is None:
        raise RuntimeError("MIXT-5G reproduction did not produce an EvolutionRun.")
    generation_count = _evolution_generation_count(workflow_result.evolution_run_path)
    comparison_path = _write_comparison_report(
        config,
        output_root=output_root,
        workflow_result=workflow_result,
        profile=profile,
        generation_count=generation_count,
    )
    return MIXT5GReproductionResult(
        workflow_result=workflow_result,
        evolution_run_path=workflow_result.evolution_run_path,
        comparison_report_path=comparison_path,
        profile=profile,
        initial_candidate_count=len(initial_records),
        generation_count=generation_count,
    )


def resume_reproduction(
    evolution_run_path: str | Path,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    output_root_override: str | Path | None = None,
    profile: str = "smoke",
    total_generations: int,
):
    """Resume an existing MIXT-5G EvolutionRun through the same public workflow."""
    config_path = Path(config_path).expanduser().resolve(strict=False)
    config = load_config(config_path)
    output_root = _resolve_output_root(config, config_path=config_path, override=output_root_override)
    workflow_mapping = build_workflow_mapping(
        config,
        output_root=output_root,
        profile=profile,
        scientific_execution=("evolve",),
        postprocessing=(),
        total_generations=total_generations,
        evolution_run_source=evolution_run_path,
    )
    return WorkflowRunner(WorkflowConfig.from_mapping(workflow_mapping)).run(
        candidate_factory=InsertGateMutationFactory(),
    )


def _mutation_recipe(scheduled: Mapping[str, Any], *, edges: Sequence[tuple[int, int]]) -> dict[str, Any]:
    return {
        "recipe_id": str(scheduled["mutation_code"]),
        "mutation_type": "insert",
        "parameters": {
            "gate": str(scheduled["mutation_gate"]).lower(),
            "mutation_code": str(scheduled["mutation_code"]),
            "edges": [list(edge) for edge in edges],
            "edge_selection": "parent_index_cycle",
            "insertion_strategy": "before_first_multiqubit",
            "candidate_id_template": "{root_candidate_id}_g{generation:03d}-{recipe_id}-v{parent_ordinal:03d}",
            "source_label": "mixt5g_reproduction",
        },
    }


def _write_comparison_report(
    config: Mapping[str, Any],
    *,
    output_root: Path,
    workflow_result,
    profile: str,
    generation_count: int,
) -> Path:
    root = output_root / str(config["run"]["run_id"]) / "comparison"
    root.mkdir(parents=True, exist_ok=True)
    evolution = json.loads(Path(workflow_result.evolution_run_path).read_text(encoding="utf-8"))
    report = {
        "schema_version": "verfeinert.example.mixt5g_reproduction.comparison.v1",
        "profile": profile,
        "reference_campaign": config["mixt5g_campaign"],
        "generation_count": generation_count,
        "candidate_counts": [
            len(generation.get("candidate_refs", ()))
            for generation in evolution["generations"]
        ],
        "survivor_candidate_ids_by_generation": [
            [
                ref["candidate_id"]
                for ref in generation.get("survivor_refs", ())
            ]
            for generation in evolution["generations"]
        ],
        "evolution_run_path": str(workflow_result.evolution_run_path),
        "full_metric_reproduction_status": "opt_in_expensive_metrics_not_run_by_smoke_profile",
    }
    return write_json(root / "comparison_report.json", report)


def _evolution_generation_count(path: Path) -> int:
    return len(json.loads(path.read_text(encoding="utf-8"))["generations"])


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

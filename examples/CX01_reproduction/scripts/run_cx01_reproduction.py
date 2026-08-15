"""Run the CX-01 reproduction example through public Verfeinert APIs."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from verfeinert.ansatz_generator import (
    SANZ19_TEMPLATE_IDS,
    build_sanz19_candidate_record,
    build_sanz19_candidate_records,
)
from verfeinert.core import read_yaml, write_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = EXAMPLE_ROOT / "config" / "cx01_reproduction.yaml"


@dataclass(frozen=True)
class CX01ReproductionResult:
    """Artifacts produced by the CX-01 reproduction example."""

    workflow_result: object
    comparison_report_path: Path
    profile: str
    generated_candidate_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "profile": self.profile,
            "generated_candidate_count": self.generated_candidate_count,
            "comparison_report_path": str(self.comparison_report_path),
            "workflow_result": self.workflow_result.to_dict(),
        }


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the CX-01 reproduction YAML configuration."""
    payload = read_yaml(path)
    if not isinstance(payload, Mapping):
        raise ValueError("CX-01 reproduction config must be a mapping.")
    return dict(payload)


def build_cx01_candidate_records(
    config: Mapping[str, Any],
    *,
    profile: str = "smoke",
) -> list[dict[str, Any]]:
    """Build CX knock-in candidate records for the selected profile."""
    campaign = dict(config["cx01_campaign"])
    profile_config = dict(config["profiles"][profile])
    template_ids = _template_ids(profile_config.get("template_ids", "all"))
    layers = tuple(int(layer) for layer in profile_config.get("layers", campaign["layers"]))
    raw_edges = profile_config.get("edges", "all_valid")
    gate = str(campaign["mutation"]["gate"]).lower()

    if raw_edges == "all_valid":
        return _build_topology_aware_records(
            template_ids,
            layers,
            n_qubits=int(campaign["n_qubits"]),
            gate=gate,
            max_candidates=profile_config.get("max_candidates"),
        )

    edges = _edges(raw_edges, n_qubits=int(campaign["n_qubits"]))
    parents = build_sanz19_candidate_records(
        template_ids,
        layers,
        n_qubits=int(campaign["n_qubits"]),
    )
    records: list[dict[str, Any]] = []
    for parent in parents:
        for variant_index, edge in enumerate(edges, start=1):
            records.append(_cx_knock_in_record(parent, gate=gate, edge=edge, variant_index=variant_index))
    max_candidates = profile_config.get("max_candidates")
    if max_candidates is not None:
        records = records[: int(max_candidates)]
    return records


def _build_topology_aware_records(
    template_ids: Sequence[str],
    layers: Sequence[int],
    *,
    n_qubits: int,
    gate: str,
    max_candidates: object,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for template_id in template_ids:
        parent_l1 = build_sanz19_candidate_record(template_id, 1, n_qubits=n_qubits)
        for variant_index, edge in enumerate(_historical_edges(template_id, n_qubits=n_qubits), start=1):
            unit_operations = _mutated_l1_operations(
                parent_l1["operations"],
                gate=gate,
                edge=edge,
                variant_index=variant_index,
            )
            for layer in layers:
                records.append(
                    _cx_repeated_layer_record(
                        parent_l1,
                        gate=gate,
                        edge=edge,
                        variant_index=variant_index,
                        layer=int(layer),
                        unit_operations=unit_operations,
                    ),
                )
    if max_candidates is not None:
        records = records[: int(max_candidates)]
    return records


def run_reproduction(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    output_root_override: str | Path | None = None,
    profile: str = "smoke",
) -> CX01ReproductionResult:
    """Execute the CX-01 reproduction workflow."""
    config_path = Path(config_path).expanduser().resolve(strict=False)
    config = load_config(config_path)
    output_root = _resolve_output_root(config, config_path=config_path, override=output_root_override)
    candidate_records = build_cx01_candidate_records(config, profile=profile)
    workflow_mapping = _workflow_mapping(config, output_root=output_root, profile=profile)
    workflow_result = WorkflowRunner(WorkflowConfig.from_mapping(workflow_mapping)).run(
        candidate_records=candidate_records,
    )
    comparison_report_path = _write_comparison_report(
        config,
        workflow_result=workflow_result,
        profile=profile,
        candidate_records=candidate_records,
    )
    return CX01ReproductionResult(
        workflow_result=workflow_result,
        comparison_report_path=comparison_report_path,
        profile=profile,
        generated_candidate_count=len(candidate_records),
    )


def _cx_knock_in_record(
    parent: Mapping[str, Any],
    *,
    gate: str,
    edge: tuple[int, int],
    variant_index: int,
) -> dict[str, Any]:
    operations = [copy.deepcopy(dict(operation)) for operation in parent["operations"]]
    insert_at = _after_rotation_block_index(operations)
    mutation_operation = {
        "gate": gate,
        "wires": list(edge),
        "parameterized": False,
        "params": [],
        "layer": 0,
        "metadata": {
            "source": "cx01_reproduction",
            "placement": "after_rotation_block",
            "edge": list(edge),
            "variant_index": variant_index,
        },
    }
    operations = operations[:insert_at] + [mutation_operation] + operations[insert_at:]
    operations = _renumber_operations(operations)
    template_id = str(parent["template_id"])
    layer = int(parent["layer"])
    child_id = f"{template_id}-L{layer}_cx-v{variant_index:03d}"
    record = {
        **dict(parent),
        "circuit_id": child_id,
        "child_id": child_id,
        "parent_circuit_id": parent["circuit_id"],
        "root_circuit_id": parent["circuit_id"],
        "generation_index": 1,
        "mutation_type": "knock_in",
        "mutation_gate": gate,
        "mutation_id": f"{child_id}-mutation",
        "variant_index": variant_index,
        "operations": operations,
        "metadata": {
            **dict(parent.get("metadata", {})),
            "reproduction": "cx01",
            "mutation_type": "knock_in",
            "mutation_gate": gate,
            "mutation_edge": list(edge),
            "placement": "after_rotation_block",
        },
    }
    record.pop("template_id", None)
    record.pop("ansatz_id", None)
    return record


def _cx_repeated_layer_record(
    parent_l1: Mapping[str, Any],
    *,
    gate: str,
    edge: tuple[int, int],
    variant_index: int,
    layer: int,
    unit_operations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    operations = _repeat_mutated_layer(unit_operations, layer)
    template_id = str(parent_l1["template_id"])
    child_id = f"{template_id}-L{layer}_cx-v{variant_index:03d}"
    record = {
        **dict(parent_l1),
        "circuit_id": child_id,
        "child_id": child_id,
        "parent_circuit_id": parent_l1["circuit_id"],
        "root_circuit_id": parent_l1["circuit_id"],
        "generation_index": 1,
        "mutation_type": "knock_in",
        "mutation_gate": gate,
        "mutation_id": f"{child_id}-mutation",
        "variant_index": variant_index,
        "layer": layer,
        "L": f"L{layer}",
        "recipe_id": f"{template_id}_CX_V{variant_index:03d}_L{layer}",
        "operations": operations,
        "metadata": {
            **dict(parent_l1.get("metadata", {})),
            "reproduction": "cx01",
            "mutation_type": "knock_in",
            "mutation_gate": gate,
            "mutation_edge": list(edge),
            "placement": "after_rotation_block",
            "propagation_policy": "repeat_mutated_single_layer",
            "layer_generation_policy": "mutate_then_repeat_layer",
            "base_layer_source": f"{template_id}-L1",
            "variant_index": variant_index,
            "layer": layer,
            "L": f"L{layer}",
        },
    }
    record.pop("template_id", None)
    record.pop("ansatz_id", None)
    return record


def _mutated_l1_operations(
    operations: Sequence[Mapping[str, Any]],
    *,
    gate: str,
    edge: tuple[int, int],
    variant_index: int,
) -> list[dict[str, Any]]:
    unit = [copy.deepcopy(dict(operation)) for operation in operations]
    insert_at = _after_rotation_block_index(unit)
    mutation_operation = {
        "gate": gate,
        "wires": list(edge),
        "parameterized": False,
        "params": [],
        "layer": 0,
        "metadata": {
            "source": "cx01_reproduction",
            "placement": "after_rotation_block",
            "edge": list(edge),
            "variant_index": variant_index,
            "propagation_policy": "repeat_mutated_single_layer",
            "layer_generation_policy": "mutate_then_repeat_layer",
            "mutation_applied_to_single_layer_block": True,
        },
    }
    return _renumber_operations(unit[:insert_at] + [mutation_operation] + unit[insert_at:])


def _repeat_mutated_layer(
    unit_operations: Sequence[Mapping[str, Any]],
    layer_count: int,
) -> list[dict[str, Any]]:
    repeated: list[dict[str, Any]] = []
    for layer_index in range(layer_count):
        for layer_local_order, operation in enumerate(unit_operations):
            item = copy.deepcopy(dict(operation))
            item["layer"] = layer_index
            metadata = dict(item.get("metadata", {}))
            metadata["layer_index"] = layer_index
            metadata["layer_local_order"] = layer_local_order
            if metadata.get("source") == "cx01_reproduction":
                metadata["replicated_layer"] = layer_index
            item["metadata"] = metadata
            repeated.append(item)
    return _renumber_operations(repeated)


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
        metadata.setdefault("layer_local_order", order)
        item["metadata"] = metadata
        records.append(item)
    return records


def _template_ids(raw: object) -> tuple[str, ...]:
    if raw == "all":
        return tuple(SANZ19_TEMPLATE_IDS)
    return tuple(str(item).upper() for item in raw)  # type: ignore[union-attr]


def _edges(raw: object, *, n_qubits: int) -> tuple[tuple[int, int], ...]:
    if raw == "all_valid":
        return tuple((wire, target) for wire in range(n_qubits) for target in range(n_qubits) if wire != target)
    return tuple((int(edge[0]), int(edge[1])) for edge in raw)  # type: ignore[index]


def _historical_edges(template_id: str, *, n_qubits: int) -> tuple[tuple[int, int], ...]:
    topology = _historical_topology(template_id)
    if topology == "disconnected":
        return ()
    if topology == "all_to_all":
        return tuple(
            (source, target)
            for source in range(n_qubits)
            for target in range(n_qubits)
            if source != target
        )
    undirected = [(wire, wire + 1) for wire in range(n_qubits - 1)]
    if topology == "ring":
        undirected.append((0, n_qubits - 1))
    directed: list[tuple[int, int]] = []
    for source, target in sorted(tuple(sorted(edge)) for edge in undirected):
        directed.append((source, target))
        directed.append((target, source))
    return tuple(directed)


def _historical_topology(template_id: str) -> str:
    normalized = str(template_id).upper()
    if normalized == "A01":
        return "disconnected"
    if normalized in {"A05", "A06"}:
        return "all_to_all"
    if normalized in {"A10", "A13", "A14", "A15", "A18", "A19"}:
        return "ring"
    return "linear"


def _workflow_mapping(config: Mapping[str, Any], *, output_root: Path, profile: str) -> dict[str, Any]:
    workflow = dict(config)
    profile_config = dict(config["profiles"][profile])
    workflow["paths"] = {"output_root": str(output_root)}
    workflow["generation"] = dict(config["generation"])
    workflow["generation"]["family"] = "provided"
    workflow["generation"]["created_at"] = config["run"]["created_at"]
    workflow["analyzer"] = _merged_mapping(config["analyzer"], profile_config.get("analyzer", {}))
    workflow["metadata"] = {
        "example": "cx01_reproduction",
        "campaign_reference": config["cx01_campaign"],
        "profile": profile,
    }
    return workflow


def _merged_mapping(base: Mapping[str, Any], override: object) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    if not isinstance(override, Mapping):
        return result
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merged_mapping(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _write_comparison_report(
    config: Mapping[str, Any],
    *,
    workflow_result,
    profile: str,
    candidate_records: Sequence[Mapping[str, Any]],
) -> Path:
    comparison_root = workflow_result.run_root / "comparison"
    comparison_root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "verfeinert.example.cx01_reproduction.comparison.v1",
        "profile": profile,
        "reference_campaign": config["cx01_campaign"],
        "generated_candidate_count": len(candidate_records),
        "workflow_candidate_count": len(workflow_result.candidate_ids),
        "candidate_ids": list(workflow_result.candidate_ids),
        "analysis_result_ids": list(workflow_result.analysis_result_ids),
        "survivor_candidate_ids": list(workflow_result.survivor_candidate_ids),
        "full_metric_reproduction_status": "opt_in_expensive_metrics_not_run_by_smoke_profile",
    }
    return write_json(comparison_root / "comparison_report.json", report)


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
    parser.add_argument("--profile", default="smoke", choices=("smoke", "materialized_smoke", "full"))
    args = parser.parse_args(argv)
    result = run_reproduction(args.config, output_root_override=args.output_root, profile=args.profile)
    print(result.to_dict())


if __name__ == "__main__":
    main()

"""Tests for public canonical mutation candidate factories."""

from __future__ import annotations

import json
import unittest

from verfeinert.ansatz_generator import (
    CandidateJsonExportConfig,
    CanonicalMutationFactory,
    Connectivity,
    ConstraintSet,
    build_sanz19_candidate_record,
    export_candidate_json,
    validate_candidate_constraints,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError


CREATED_AT = "2026-08-06T00:00:00Z"


def _parent(*, template_id: str = "A02", layer: int = 1) -> dict:
    return export_candidate_json(
        build_sanz19_candidate_record(template_id, layer, n_qubits=4),
        config=CandidateJsonExportConfig(
            candidate_id_prefix="mutation",
            n_qubits=4,
            created_at=CREATED_AT,
            source_label="mutation-factory-test",
            git_commit=None,
            discover_git_commit=False,
        ),
    )


def _request(parent: dict, mutation_type: str, parameters: dict, *, variant_index: int = 0) -> dict:
    return {
        "request_id": f"{parent['candidate_id']}:{mutation_type}:{variant_index}",
        "parent_candidate_id": parent["candidate_id"],
        "generation_index": 1,
        "mutation_type": mutation_type,
        "policy_id": "canonical-mutation-test",
        "recipe_id": f"{mutation_type}-recipe",
        "variant_index": variant_index,
        "root_candidate_id": parent["lineage"]["root_candidate_id"],
        "parameters": parameters,
        "metadata": {},
    }


class AnsatzGeneratorCanonicalMutationFactoryTests(unittest.TestCase):
    def test_factory_supports_all_supported_mutation_families(self) -> None:
        parent = _parent()
        layered_parent = _parent(layer=2)
        factory = CanonicalMutationFactory(created_at=CREATED_AT)

        insert = factory(_request(parent, "insert", {"gate": "cz", "edge": [1, 2]}), parent)
        self.assertEqual(insert["lineage"]["mutation"]["type"], "insert")
        self.assertEqual(len(insert["circuit"]["operations"]), len(parent["circuit"]["operations"]) + 1)

        replaced = factory(_request(parent, "replace", {"target_index": 0, "gate": "ry"}), parent)
        self.assertEqual(replaced["lineage"]["mutation"]["type"], "replace")
        self.assertEqual(replaced["circuit"]["operations"][0]["gate"]["name"], "ry")
        self.assertEqual(replaced["metadata"]["mutation_status"], "valid_mutation")

        removed = factory(_request(parent, "remove", {"target_index": 0}), parent)
        self.assertEqual(removed["lineage"]["mutation"]["type"], "remove")
        self.assertEqual(len(removed["circuit"]["operations"]), len(parent["circuit"]["operations"]) - 1)

        swapped = factory(_request(parent, "swap", {"target_index": 0, "swap_with_index": 1}), parent)
        self.assertEqual(swapped["lineage"]["mutation"]["type"], "swap")
        self.assertEqual(swapped["circuit"]["operations"][0]["gate"]["name"], "rz")
        self.assertEqual(swapped["circuit"]["operations"][1]["gate"]["name"], "rx")

        reordered = factory(_request(parent, "reorder", {"target_index": 0, "new_index": 2}), parent)
        self.assertEqual(reordered["lineage"]["mutation"]["type"], "reorder")
        self.assertEqual(reordered["circuit"]["operations"][2]["gate"]["name"], "rx")

        propagated = factory(
            _request(layered_parent, "layer_propagation", {"gate": "cz", "edge": [1, 2]}),
            layered_parent,
        )
        self.assertEqual(propagated["lineage"]["mutation"]["type"], "layer_propagation")
        self.assertTrue(
            any(
                operation["metadata"].get("propagation_policy") == "repeat_mutated_single_layer"
                for operation in propagated["circuit"]["operations"]
            ),
        )

    def test_factory_outputs_are_deterministic_and_preserve_lineage(self) -> None:
        parent = _parent()
        factory = CanonicalMutationFactory(created_at=CREATED_AT)
        request = _request(parent, "replace", {"target_index": 0, "gate": "ry"})

        first = factory(request, parent)
        second = factory(request, parent)

        self.assertEqual(first, second)
        self.assertEqual(first["lineage"]["parent_candidate_id"], parent["candidate_id"])
        self.assertEqual(first["lineage"]["generation"], 1)
        self.assertEqual(first["lineage"]["mutation"]["metadata"]["policy_id"], "canonical-mutation-test")
        self.assertEqual(first["lineage"]["mutation"]["metadata"]["recipe_id"], "replace-recipe")
        self.assertIn(first["candidate_id"], json.dumps(first, sort_keys=True))

    def test_factory_records_no_op_outcomes_explicitly(self) -> None:
        parent = _parent()
        factory = CanonicalMutationFactory(created_at=CREATED_AT)

        child = factory(_request(parent, "swap", {"target_index": 0, "swap_with_index": 0}), parent)

        self.assertEqual(child["identity"]["structural_hash"], parent["identity"]["structural_hash"])
        self.assertEqual(child["metadata"]["mutation_status"], "skipped_noop")
        self.assertEqual(child["metadata"]["no_op_status"], "skipped_noop")
        self.assertEqual(child["lineage"]["mutation"]["parameters"]["mutation_status"], "skipped_noop")

    def test_factory_rejects_invalid_mutation_requests(self) -> None:
        parent = _parent()
        factory = CanonicalMutationFactory(created_at=CREATED_AT)

        with self.assertRaisesRegex(GeneratorValidationError, "expects 2 qubit"):
            factory(_request(parent, "replace", {"target_index": 0, "gate": "cz"}), parent)

        with self.assertRaisesRegex(GeneratorValidationError, "operation range"):
            factory(_request(parent, "reorder", {"target_index": 999}), parent)

        with self.assertRaisesRegex(GeneratorValidationError, "mutation_type must be one of"):
            factory(_request(parent, "unsupported", {}), parent)

    def test_factory_applies_constraints_to_structural_children(self) -> None:
        parent = _parent()
        constraints = ConstraintSet(
            allowed_gates=("rx", "rz", "cx"),
            allowed_inserted_gates=("cz",),
            connectivity=Connectivity.linear(4),
        )
        factory = CanonicalMutationFactory(created_at=CREATED_AT, constraints=constraints)

        with self.assertRaisesRegex(GeneratorValidationError, "gate 'ry'.*not allowed"):
            factory(_request(parent, "replace", {"target_index": 0, "gate": "ry"}), parent)

        valid = factory(_request(parent, "reorder", {"target_index": 0, "new_index": 2}), parent)
        self.assertEqual(validate_candidate_constraints(valid, constraints), valid)


if __name__ == "__main__":
    unittest.main()

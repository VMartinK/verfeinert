"""Regression tests for parent→child ConstraintSet invariants."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from verfeinert.ansatz_generator import (
    CanonicalMutationFactory,
    ConstraintSet,
    GeneratorValidationError,
    InsertGateMutationFactory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = (
    PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
)
CREATED_AT = "2026-08-22T00:00:00Z"


def _root_candidate() -> dict:
    return json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))


def _parameter_count(candidate: dict) -> int:
    return len(candidate["circuit"]["parameters"])


def _operation_layer(operation: dict) -> int:
    if "layer" in operation:
        return int(operation["layer"])
    metadata = operation.get("metadata")
    if isinstance(metadata, dict) and "layer_index" in metadata:
        return int(metadata["layer_index"])
    return 0


def _layer_count(candidate: dict) -> int:
    operations = candidate["circuit"]["operations"]
    return len({_operation_layer(operation) for operation in operations})


def _next_layer(candidate: dict) -> int:
    operations = candidate["circuit"]["operations"]
    if not operations:
        return 0
    return max(_operation_layer(operation) for operation in operations) + 1


def _request(
    root: dict,
    *,
    mutation_type: str,
    recipe_id: str,
    parameters: dict,
) -> dict:
    root_id = root["candidate_id"]
    return {
        "request_id": f"b2-{recipe_id}",
        "parent_candidate_id": root_id,
        "root_candidate_id": root_id,
        "generation_index": 1,
        "mutation_type": mutation_type,
        "policy_id": "b2-transition-constraints",
        "recipe_id": recipe_id,
        "variant_index": 0,
        "parameters": dict(parameters),
        "metadata": {"parent_index": 0},
    }


class TransitionConstraintTests(unittest.TestCase):
    FACTORIES = (InsertGateMutationFactory, CanonicalMutationFactory)

    def test_parameterized_insert_rejected_when_parameter_preservation_enabled(
        self,
    ) -> None:
        root = _root_candidate()
        constraints = ConstraintSet(
            allowed_inserted_gates=("rx",),
            preserve_layer_count=True,
            preserve_parameter_count=True,
        )
        request = _request(
            root,
            mutation_type="insert",
            recipe_id="rx-preserved-params",
            parameters={
                "gate": "rx",
                "qubits": [0],
                "insertion_strategy": "append",
            },
        )

        for factory_type in self.FACTORIES:
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(
                    created_at=CREATED_AT,
                    constraints=constraints,
                )
                with self.assertRaisesRegex(
                    GeneratorValidationError,
                    "preserve_parameter_count",
                ):
                    factory(request, root)

    def test_parameterized_insert_allowed_when_parameter_preservation_disabled(
        self,
    ) -> None:
        root = _root_candidate()
        constraints = ConstraintSet(
            allowed_inserted_gates=("rx",),
            preserve_layer_count=True,
            preserve_parameter_count=False,
        )
        request = _request(
            root,
            mutation_type="insert",
            recipe_id="rx-free-params",
            parameters={
                "gate": "rx",
                "qubits": [0],
                "insertion_strategy": "append",
            },
        )

        for factory_type in self.FACTORIES:
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(
                    created_at=CREATED_AT,
                    constraints=constraints,
                )
                child = factory(request, root)
                self.assertEqual(
                    _parameter_count(child),
                    _parameter_count(root) + 1,
                )

    def test_new_layer_insert_rejected_when_layer_preservation_enabled(
        self,
    ) -> None:
        root = _root_candidate()
        constraints = ConstraintSet(
            allowed_inserted_gates=("cz",),
            preserve_layer_count=True,
            preserve_parameter_count=False,
        )
        request = _request(
            root,
            mutation_type="insert",
            recipe_id="cz-preserved-layers",
            parameters={
                "gate": "cz",
                "edge": [0, 1],
                "layer": _next_layer(root),
                "insertion_strategy": "append",
            },
        )

        for factory_type in self.FACTORIES:
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(
                    created_at=CREATED_AT,
                    constraints=constraints,
                )
                with self.assertRaisesRegex(
                    GeneratorValidationError,
                    "preserve_layer_count",
                ):
                    factory(request, root)

    def test_new_layer_insert_allowed_when_layer_preservation_disabled(
        self,
    ) -> None:
        root = _root_candidate()
        constraints = ConstraintSet(
            allowed_inserted_gates=("cz",),
            preserve_layer_count=False,
            preserve_parameter_count=False,
        )
        request = _request(
            root,
            mutation_type="insert",
            recipe_id="cz-free-layers",
            parameters={
                "gate": "cz",
                "edge": [0, 1],
                "layer": _next_layer(root),
                "insertion_strategy": "append",
            },
        )

        for factory_type in self.FACTORIES:
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(
                    created_at=CREATED_AT,
                    constraints=constraints,
                )
                child = factory(request, root)
                self.assertEqual(
                    _layer_count(child),
                    _layer_count(root) + 1,
                )


if __name__ == "__main__":
    unittest.main()

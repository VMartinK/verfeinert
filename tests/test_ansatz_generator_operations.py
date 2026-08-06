"""Tests for generator operation and parameter representation."""

from __future__ import annotations

import unittest

from verfeinert.ansatz_generator import (
    DEFAULT_GATE_REGISTRY,
    GateDef,
    GateRegistry,
    Operation,
    Parameter,
    ParameterMap,
)
from verfeinert.ansatz_generator.validation import GeneratorValidationError


class AnsatzGeneratorOperationTests(unittest.TestCase):
    def test_gate_registry_supports_beta_gate_set_and_extension(self) -> None:
        self.assertTrue(DEFAULT_GATE_REGISTRY.has("RX"))
        self.assertTrue(DEFAULT_GATE_REGISTRY.has("cnot"))
        self.assertEqual(DEFAULT_GATE_REGISTRY.get("Hadamard").name, "h")

        registry = GateRegistry()
        registry.register(
            GateDef(
                name="custom",
                n_wires=1,
                n_params=1,
                aliases=("CUST",),
                is_parameterized=True,
                is_trainable=True,
            )
        )
        self.assertEqual(registry.normalize("CUST"), "custom")
        self.assertTrue(registry.get("custom").is_parametrized)

    def test_operation_validation_and_serialization(self) -> None:
        operation = Operation(
            gate="RX",
            wires=(0,),
            parameters=("theta_0",),
            layer=1,
            order=2,
            metadata={"block_id": "rotation"},
        )

        self.assertEqual(operation.gate, "rx")
        self.assertEqual(operation.trainable_parameter_names, ("theta_0",))
        self.assertEqual(operation.to_dict()["wires"], [0])

        with self.assertRaises(GeneratorValidationError):
            Operation(gate="rx", wires=(0, 1))
        with self.assertRaises(GeneratorValidationError):
            Operation(gate="cx", wires=(0, 0))
        with self.assertRaises(GeneratorValidationError):
            Operation(gate="h", wires=(0,), parameters=("theta",))

    def test_parameter_map_preserves_first_appearance_and_sharing(self) -> None:
        parameter = Parameter(name="theta_0", index=0)
        self.assertEqual(parameter.name, "theta_0")

        parameter_map = ParameterMap.from_names(["theta_1", "theta_0", "theta_1"])
        self.assertEqual(parameter_map.as_tuple(), ("theta_1", "theta_0"))
        self.assertEqual(parameter_map.get_index("theta_0"), 1)
        self.assertEqual(parameter_map.get_name(0), "theta_1")

        operations = [
            Operation(gate="rx", wires=(0,), parameters=("theta_0",)),
            Operation(gate="rz", wires=(0,), parameters=(0.25,)),
            Operation(gate="ry", wires=(1,), parameters=("theta_0",)),
        ]
        self.assertEqual(ParameterMap.from_operations(operations).as_tuple(), ("theta_0",))

        with self.assertRaises(GeneratorValidationError):
            ParameterMap(["theta", "theta"])


if __name__ == "__main__":
    unittest.main()

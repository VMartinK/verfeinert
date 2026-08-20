"""Phase 10.1 tests for analyzer-owned scientific materialization."""

from __future__ import annotations

from importlib import metadata
import math
from pathlib import Path
import tempfile
import tomllib
import unittest

import numpy as np

import verfeinert
from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalyzerConfig,
    AnalyzerExecutionPermissions,
    CircuitMaterializationConfig,
    CircuitMaterializationError,
    OperationView,
    StructuralCostConfig,
    materialize_candidate,
    validate_analysis_result_document,
)
from verfeinert._version import PACKAGE_NAME, SOURCE_TREE_VERSION
from verfeinert.core.io import read_json
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
HASH = "0" * 64
CREATED_AT = "2026-08-06T00:00:00Z"
EXPLICIT_REFERENCE_BOUNDS = {
    "parameter_count": {"min": 0.0, "max": 4.0},
    "depth": {"min": 0.0, "max": 6.0},
    "two_qubit_operation_count": {"min": 0.0, "max": 2.0},
}


def _canonical_candidate(
    *,
    candidate_id: str,
    n_qubits: int = 1,
    parameters: list[dict] | None = None,
    operations: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "schema_version": "verfeinert.candidate.v1",
        "candidate_id": candidate_id,
        "identity": {
            "structural_hash": HASH,
            "lineage_hash": HASH,
            "hash_schema_version": "test-hash-v1",
        },
        "circuit": {
            "n_qubits": n_qubits,
            "wire_order": list(range(n_qubits)),
            "parameters": parameters or [],
            "operations": operations
            or [
                {
                    "operation_id": "op-000",
                    "gate": {"name": "x"},
                    "qubits": [0],
                    "parameters": [],
                    "order": 0,
                },
            ],
        },
        "lineage": {
            "generation": 0,
            "root_candidate_id": candidate_id,
            "parent_candidate_id": None,
            "mutation": None,
        },
        "metadata": metadata or {},
        "provenance": {
            "created_at": CREATED_AT,
            "source": {"kind": "manual", "label": "phase-10-1-test"},
            "software_version": "test",
            "git_commit": None,
            "input_hashes": {},
        },
    }


def _op(
    operation_id: str,
    gate: str,
    qubits: list[int],
    parameters: list[dict] | None = None,
    *,
    namespace: str | None = None,
    version: str | None = None,
) -> dict:
    gate_record = {"name": gate}
    if namespace is not None:
        gate_record["namespace"] = namespace
    if version is not None:
        gate_record["version"] = version
    return {
        "operation_id": operation_id,
        "gate": gate_record,
        "qubits": qubits,
        "parameters": parameters or [],
        "order": int(operation_id.rsplit("-", 1)[-1]),
    }


def _ref(parameter_id: str) -> dict:
    return {"kind": "reference", "parameter_id": parameter_id}


def _literal(value: float) -> dict:
    return {"kind": "literal", "value": value}


def _analysis_config(
    tmp_path: Path,
    *,
    selected_metrics=("structural_cost", "expressibility", "trainability"),
    materialization: CircuitMaterializationConfig | None = None,
    permissions: AnalyzerExecutionPermissions | None = None,
) -> AnalyzerConfig:
    input_root = tmp_path / "inputs"
    output_root = tmp_path / "outputs"
    input_root.mkdir(parents=True)
    return AnalyzerConfig(
        run_id="phase101-run",
        input_roots=(input_root,),
        output_root=output_root,
        selected_metrics=selected_metrics,
        permissions=permissions
        or AnalyzerExecutionPermissions(
            allow_expensive_metrics=True,
            allow_qnode_execution=True,
        ),
        structural_cost=StructuralCostConfig(reference_bounds=EXPLICIT_REFERENCE_BOUNDS),
        materialization=materialization or CircuitMaterializationConfig(enabled=True),
        metric_configs={
            "expressibility": {
                "n_pairs": 3,
                "n_bins": 3,
                "rng_seed": 123,
            },
            "trainability": {
                "n_repeats": 2,
                "rng_seed": 123,
            },
        },
    )


def _explicit_state_callable(params):
    from pennylane import numpy as pnp

    angle = params[0] if len(params) else 0.0
    return pnp.array([pnp.cos(angle), pnp.sin(angle), 0.0, 0.0], dtype=complex)


class AnalyzerPhase101MaterializationTests(unittest.TestCase):
    def test_operation_view_preserves_v030_positional_constructor_contract(self) -> None:
        parameters = ({"kind": "reference", "parameter_id": "theta-0"},)
        metadata = {"source": "legacy-positional"}

        legacy = OperationView(
            "op-legacy",
            "rx",
            (1,),
            parameters,
            2,
            3,
            "candidate",
            metadata,
        )

        self.assertEqual(legacy.operation_id, "op-legacy")
        self.assertEqual(legacy.gate_name, "rx")
        self.assertEqual(legacy.qubits, (1,))
        self.assertEqual(legacy.parameters, parameters)
        self.assertEqual(legacy.layer, 2)
        self.assertEqual(legacy.order, 3)
        self.assertEqual(legacy.role, "candidate")
        self.assertEqual(legacy.metadata, metadata)
        self.assertIsNone(legacy.gate_namespace)
        self.assertIsNone(legacy.gate_version)

        keyword_identity = OperationView(
            "op-keyword",
            "rz",
            (0,),
            parameters,
            1,
            2,
            "reference",
            {"source": "keyword"},
            gate_namespace="verfeinert.default_gates",
            gate_version="test-version",
        )
        self.assertEqual(keyword_identity.gate_namespace, "verfeinert.default_gates")
        self.assertEqual(keyword_identity.gate_version, "test-version")

        from_document = OperationView.from_document(
            {
                "operation_id": "op-document",
                "gate": {
                    "name": "ry",
                    "namespace": "verfeinert.default_gates",
                    "version": "document-version",
                },
                "qubits": [0],
                "parameters": list(parameters),
                "layer": 4,
                "order": 5,
                "role": "document",
                "metadata": {"source": "document"},
            },
        )
        self.assertEqual(from_document.gate_name, "ry")
        self.assertEqual(from_document.gate_namespace, "verfeinert.default_gates")
        self.assertEqual(from_document.gate_version, "document-version")
        self.assertEqual(from_document.parameters, parameters)
        self.assertEqual(from_document.layer, 4)
        self.assertEqual(from_document.order, 5)
        self.assertEqual(from_document.role, "document")
        self.assertEqual(from_document.metadata, {"source": "document"})

    def test_static_candidate_materializes_and_preserves_operation_order(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-static",
            operations=[
                _op("op-000", "x", [0]),
                _op("op-001", "h", [0]),
            ],
        )

        materialized = materialize_candidate(
            candidate,
            config=CircuitMaterializationConfig(enabled=True),
        )
        state = np.asarray(materialized.state_callable([]), dtype=complex)

        expected = np.asarray([1 / math.sqrt(2), -1 / math.sqrt(2)], dtype=complex)
        self.assertTrue(np.allclose(state, expected))
        self.assertEqual(materialized.trainable_parameter_ids, ())
        self.assertEqual(materialized.gate_names, ("x", "h"))

    def test_built_in_candidate_fixture_materializes_with_default_namespace(self) -> None:
        materialized = materialize_candidate(
            read_json(CANDIDATE_EXAMPLE),
            config=CircuitMaterializationConfig(enabled=True),
        )
        state = np.asarray(materialized.state_callable([0.0, 0.0]), dtype=complex)

        self.assertEqual(materialized.gate_names, ("rx", "rz", "cz"))
        self.assertEqual(materialized.trainable_parameter_ids, ("theta-0", "theta-1"))
        self.assertAlmostEqual(float(np.sum(np.abs(state) ** 2)), 1.0)

    def test_parameter_order_literals_and_repeated_references_are_canonical(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-parameters",
            parameters=[
                {"parameter_id": "theta-a", "kind": "trainable", "symbol": "a"},
                {"parameter_id": "theta-b", "kind": "trainable", "symbol": "b"},
            ],
            operations=[
                _op("op-000", "rx", [0], [_ref("theta-b")]),
                _op("op-001", "rx", [0], [_ref("theta-b")]),
                _op("op-002", "rz", [0], [_literal(0.0)]),
            ],
        )

        materialized = materialize_candidate(
            candidate,
            config=CircuitMaterializationConfig(enabled=True),
        )
        state = np.asarray(materialized.state_callable([0.0, math.pi / 4.0]), dtype=complex)

        expected = np.asarray([math.sqrt(0.5), -1j * math.sqrt(0.5)], dtype=complex)
        self.assertEqual(materialized.trainable_parameter_ids, ("theta-a", "theta-b"))
        self.assertTrue(np.allclose(state, expected))
        self.assertEqual(
            materialized.to_metadata()["trainable_parameter_ids"],
            ["theta-a", "theta-b"],
        )

    def test_supported_public_gate_set_materializes(self) -> None:
        parameters = [
            {"parameter_id": f"theta-{index}", "kind": "trainable", "symbol": f"theta_{index}"}
            for index in range(9)
        ]
        parameterized = [
            ("rx", [0]),
            ("ry", [1]),
            ("rz", [0]),
            ("crx", [0, 1]),
            ("cry", [0, 1]),
            ("crz", [0, 1]),
            ("isingxx", [0, 1]),
            ("isingyy", [0, 1]),
            ("isingzz", [0, 1]),
        ]
        operations = [
            _op("op-000", "x", [0]),
            _op("op-001", "y", [1]),
            _op("op-002", "z", [0]),
            _op("op-003", "h", [1]),
            _op("op-004", "cx", [0, 1]),
            _op("op-005", "cnot", [1, 0]),
            _op("op-006", "cz", [0, 1]),
            _op("op-007", "swap", [0, 1]),
        ]
        for offset, (gate, wires) in enumerate(parameterized, start=len(operations)):
            operations.append(_op(f"op-{offset:03d}", gate, wires, [_ref(f"theta-{offset - 8}")]))
        candidate = _canonical_candidate(
            candidate_id="phase101-gates",
            n_qubits=2,
            parameters=parameters,
            operations=operations,
        )

        materialized = materialize_candidate(
            candidate,
            config=CircuitMaterializationConfig(enabled=True),
        )
        state = np.asarray(materialized.state_callable([0.1] * 9), dtype=complex)

        self.assertEqual(len(state), 4)
        self.assertAlmostEqual(float(np.sum(np.abs(state) ** 2)), 1.0)
        self.assertEqual(
            materialized.gate_names,
            (
                "x",
                "y",
                "z",
                "h",
                "cx",
                "cnot",
                "cz",
                "swap",
                "rx",
                "ry",
                "rz",
                "crx",
                "cry",
                "crz",
                "isingxx",
                "isingyy",
                "isingzz",
            ),
        )

    def test_unsupported_operation_fails_clearly(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-unsupported",
            operations=[_op("op-000", "mystery", [0])],
        )

        with self.assertRaisesRegex(CircuitMaterializationError, "unsupported candidate operation 'mystery'"):
            materialize_candidate(candidate, config=CircuitMaterializationConfig(enabled=True))

    def test_derived_parameter_is_representable_but_not_materializable(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-derived",
            parameters=[
                {"parameter_id": "theta-a", "kind": "trainable", "symbol": "theta_a"},
                {
                    "parameter_id": "theta-derived",
                    "kind": "derived",
                    "symbol": "theta_derived",
                    "metadata": {"expression": "2 * theta_a"},
                },
            ],
            operations=[
                _op("op-000", "rx", [0], [_ref("theta-derived")]),
            ],
        )

        with self.assertRaisesRegex(CircuitMaterializationError, "derived parameter 'theta-derived'.*not materializable"):
            materialize_candidate(candidate, config=CircuitMaterializationConfig(enabled=True))

    def test_unsupported_gate_namespace_is_not_matched_by_name(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-namespace",
            operations=[
                _op(
                    "op-000",
                    "rx",
                    [0],
                    [_literal(0.0)],
                    namespace="external.default_gates",
                ),
            ],
        )

        with self.assertRaisesRegex(CircuitMaterializationError, "unsupported semantic gate identity"):
            materialize_candidate(candidate, config=CircuitMaterializationConfig(enabled=True))

    def test_unsupported_gate_version_is_not_matched_by_name(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-version",
            operations=[
                _op(
                    "op-000",
                    "rx",
                    [0],
                    [_literal(0.0)],
                    namespace="verfeinert.default_gates",
                    version="2026-08",
                ),
            ],
        )

        with self.assertRaisesRegex(CircuitMaterializationError, "unsupported semantic gate identity"):
            materialize_candidate(candidate, config=CircuitMaterializationConfig(enabled=True))

    def test_non_numeric_literal_parameter_fails_clearly(self) -> None:
        candidate = _canonical_candidate(
            candidate_id="phase101-literal",
            operations=[_op("op-000", "rx", [0], [{"kind": "literal", "value": "pi"}])],
        )

        with self.assertRaisesRegex(CircuitMaterializationError, "literal value must be numeric"):
            materialize_candidate(candidate, config=CircuitMaterializationConfig(enabled=True))

    def test_pipeline_computes_real_metrics_from_candidate_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _analysis_config(Path(tmp))
            record = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0]
            payload = validate_analysis_result_document(record.to_dict())

        metrics = {metric["name"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics["expressibility"]["status"], "computed")
        self.assertEqual(metrics["trainability"]["status"], "computed")
        self.assertIn("expressibility", metrics["expressibility"]["value"])
        self.assertIn("trainability", metrics["trainability"]["value"])
        self.assertTrue(metrics["expressibility"]["metadata"]["qnodes_executed"])
        self.assertTrue(metrics["trainability"]["metadata"]["qnodes_executed"])
        self.assertEqual(
            metrics["trainability"]["metadata"]["state_callable_source"],
            "automatic_materialization",
        )
        self.assertEqual(
            metrics["trainability"]["metadata"]["materialization"]["trainable_parameter_ids"],
            ["theta-0", "theta-1"],
        )
        self.assertTrue(payload["provenance"]["execution"]["qnodes_executed"])
        self.assertTrue(payload["provenance"]["execution"]["automatic_materialization_used"])
        self.assertTrue(payload["provenance"]["execution"]["materialized_callables_executed"])
        self.assertNotEqual(payload["provenance"]["software_version"], "0.0.0")
        self.assertEqual(
            payload["metadata"]["candidate_semantics"]["lineage"]["root_candidate_id"],
            "reference-a02-l1-parent",
        )
        self.assertEqual(payload["candidate_ref"]["candidate_id"], "reference-a02-l1-parent")
        self.assertNotIn("candidate_id", payload["metadata"]["candidate_semantics"])

    def test_explicit_callable_takes_precedence_over_automatic_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _analysis_config(
                Path(tmp),
                selected_metrics=("expressibility",),
                permissions=AnalyzerExecutionPermissions(
                    allow_expensive_metrics=True,
                    allow_qnode_execution=False,
                ),
                materialization=CircuitMaterializationConfig(enabled=True),
            )
            record = AnalysisPipeline(config).run(
                CANDIDATE_EXAMPLE,
                metric_callables={
                    "expressibility": {
                        "reference-a02-l1-parent": _explicit_state_callable,
                    },
                },
            )[0]
            payload = record.to_dict()

        metric = payload["metrics"][0]
        self.assertEqual(metric["status"], "computed")
        self.assertEqual(metric["metadata"]["state_callable_source"], "explicit")
        self.assertFalse(metric["metadata"]["automatic_materialization_used"])
        self.assertFalse(payload["provenance"]["execution"]["qnodes_executed"])

    def test_disabled_materialization_keeps_existing_skip_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _analysis_config(
                Path(tmp),
                selected_metrics=("expressibility",),
                materialization=CircuitMaterializationConfig(enabled=False),
            )
            payload = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0].to_dict()

        metric = payload["metrics"][0]
        self.assertEqual(metric["status"], "skipped")
        self.assertEqual(metric["metadata"]["reason"], "no state callable provided")
        self.assertFalse(metric["metadata"]["materialization_enabled"])

    def test_qnode_permission_denial_skips_automatic_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _analysis_config(
                Path(tmp),
                selected_metrics=("trainability",),
                permissions=AnalyzerExecutionPermissions(
                    allow_expensive_metrics=True,
                    allow_qnode_execution=False,
                ),
                materialization=CircuitMaterializationConfig(enabled=True),
            )
            payload = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0].to_dict()

        metric = payload["metrics"][0]
        self.assertEqual(metric["status"], "skipped")
        self.assertIn("allow_qnode_execution", metric["metadata"]["reason"])
        self.assertFalse(metric["metadata"]["qnodes_executed"])

    def test_workflow_passes_materialization_config_to_analyzer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "outputs"
            config = WorkflowConfig.from_mapping(
                {
                    "run": {
                        "run_id": "phase101-workflow",
                        "created_at": CREATED_AT,
                        "random_seed": 123,
                    },
                    "paths": {"output_root": str(output_root)},
                    "generation": {
                        "family": "sanz19",
                        "template_ids": ["A02"],
                        "layers": [1],
                        "n_qubits": 2,
                        "candidate_id_prefix": "phase101wf",
                    },
                    "analyzer": {
                        "selected_metrics": ["structural_cost", "expressibility", "trainability"],
                        "permissions": {
                            "allow_expensive_metrics": True,
                            "allow_qnode_execution": True,
                        },
                        "materialization": {"enabled": True},
                        "structural_cost": {
                            "reference_bounds": EXPLICIT_REFERENCE_BOUNDS,
                        },
                        "metric_configs": {
                            "expressibility": {"n_pairs": 3, "n_bins": 3, "rng_seed": 5},
                            "trainability": {"n_repeats": 2, "rng_seed": 5},
                        },
                        "ranking": {
                            "score_components": {"cost.structural_cost": 1.0},
                            "combination": "weighted_sum",
                            "ascending": True,
                        },
                    },
                    "evolver": {
                        "selection_mode": "fitness",
                        "policy_id": "phase101-selection",
                        "metric_name": "structural_cost",
                        "keep": 1,
                        "direction": "minimize",
                    },
                },
            )
            result = WorkflowRunner(config).run()
            payload = read_json(result.analysis_result_paths[0])

        metrics = {metric["name"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics["expressibility"]["status"], "computed")
        self.assertEqual(metrics["trainability"]["status"], "computed")
        self.assertTrue(payload["provenance"]["execution"]["automatic_materialization_used"])
        self.assertFalse(result.provenance["execution"]["qnodes_executed_by_runner"])

    def test_software_version_resolves_from_installed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _analysis_config(Path(tmp))
            payload = AnalysisPipeline(config).run(CANDIDATE_EXAMPLE)[0].to_dict()

        project_metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        expected_version = project_metadata["project"]["version"]
        self.assertEqual(SOURCE_TREE_VERSION, expected_version)
        self.assertEqual(metadata.version(PACKAGE_NAME), expected_version)
        self.assertEqual(verfeinert.__version__, expected_version)
        self.assertEqual(payload["provenance"]["software_version"], expected_version)

    def test_structural_cost_result_is_unchanged_by_disabled_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base = _analysis_config(
                tmp_path / "base",
                selected_metrics=("structural_cost",),
                permissions=AnalyzerExecutionPermissions(),
                materialization=CircuitMaterializationConfig(enabled=False),
            )
            enabled = _analysis_config(
                tmp_path / "enabled",
                selected_metrics=("structural_cost",),
                permissions=AnalyzerExecutionPermissions(),
                materialization=CircuitMaterializationConfig(enabled=True),
            )
            base_payload = AnalysisPipeline(base).run(CANDIDATE_EXAMPLE)[0].to_dict()
            enabled_payload = AnalysisPipeline(enabled).run(CANDIDATE_EXAMPLE)[0].to_dict()

        self.assertEqual(base_payload["cost"], enabled_payload["cost"])
        self.assertEqual(base_payload["metrics"][0], enabled_payload["metrics"][0])


if __name__ == "__main__":
    unittest.main()

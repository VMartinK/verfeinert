"""Phase 8 reference validation for v1-aligned scientific metrics."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
import unittest

from verfeinert.ansatz_analyzer import AnalyzerExecutionPermissions, load_candidate_views
from verfeinert.ansatz_analyzer.metrics.expressibility import (
    ExpressibilityConfig as V2ExpressibilityConfig,
    compute_expressibility_metric as compute_v2_expressibility,
)
from verfeinert.ansatz_analyzer.metrics.trainability import (
    TrainabilityConfig as V2TrainabilityConfig,
    compute_trainability_metric as compute_v2_trainability,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_WORKSPACE_ROOT = PROJECT_ROOT.parent
V1_SRC = LEGACY_WORKSPACE_ROOT / "Verfeinert" / "src"
V1_METRICS = LEGACY_WORKSPACE_ROOT / "Verfeinert" / "src" / "ansatz_analyzer" / "metrics"
V2_METRICS = PROJECT_ROOT / "verfeinert" / "ansatz_analyzer" / "metrics"
REFERENCE_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "reference_metrics"
PHASE8_REPORT = PROJECT_ROOT / "docs" / "migration" / "phase8_metrics_validation_report.md"
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class MetricsReferenceValidationTests(unittest.TestCase):
    def test_metric_audit_sources_are_available_in_legacy_context(self) -> None:
        if not V1_METRICS.exists():
            self.skipTest("Legacy Verfeinert v1 metrics are not available outside a legacy reference workspace.")

        required = (
            V1_METRICS / "expressibility.py",
            V1_METRICS / "trainability.py",
            V2_METRICS / "expressibility.py",
            V2_METRICS / "trainability.py",
        )
        missing = [str(path) for path in required if not path.is_file()]
        self.assertEqual(missing, [])

    def test_expressibility_uses_v1_numpy_rng_methodology(self) -> None:
        if not V1_METRICS.exists():
            self.skipTest("Legacy Verfeinert v1 metrics are not available outside a legacy reference workspace.")

        v1 = _read(V1_METRICS / "expressibility.py")
        v2 = _read(V2_METRICS / "expressibility.py")
        report = _read(PHASE8_REPORT)

        self.assertIn("np.random.default_rng", v1)
        self.assertIn("np.random.default_rng", v2)
        self.assertNotIn("random.Random", v2)
        self.assertIn("Expressibility", report)
        self.assertIn("8.0.1", report)

    def test_trainability_uses_v1_pennylane_gradient_methodology(self) -> None:
        if not V1_METRICS.exists():
            self.skipTest("Legacy Verfeinert v1 metrics are not available outside a legacy reference workspace.")

        v1 = _read(V1_METRICS / "trainability.py")
        v2 = _read(V2_METRICS / "trainability.py")
        report = _read(PHASE8_REPORT)

        self.assertIn("qml.grad", v1)
        self.assertIn("qml.grad", v2)
        self.assertNotIn("plus[index]", v2)
        self.assertNotIn("minus[index]", v2)
        self.assertIn("Trainability", report)
        self.assertIn("8.0.1", report)

    def test_expressibility_matches_v1_tiny_reference_fixture(self) -> None:
        self._skip_without_optional_dependencies("numpy", "pandas")
        v1_expressibility = self._v1_expressibility_module()
        view = load_candidate_views(CANDIDATE_EXAMPLE)[0]

        def toy_state(params):
            import numpy as np

            angle = float(sum(params))
            return np.array([math.cos(angle), math.sin(angle), 0.0, 0.0], dtype=complex)

        v1_record = v1_expressibility.compute_expressibility_for_circuit(
            view.candidate_id,
            toy_state,
            parameter_count=view.parameter_count,
            layer=1,
            config=v1_expressibility.ExpressibilityConfig(
                n_qubits=view.n_qubits,
                n_pairs=8,
                n_bins=5,
                rng_seed=123,
            ),
        )
        v2_metric = compute_v2_expressibility(
            view,
            toy_state,
            config=V2ExpressibilityConfig(
                n_qubits=view.n_qubits,
                n_pairs=8,
                n_bins=5,
                rng_seed=123,
            ),
            permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        )

        self.assertEqual(v2_metric.status, "computed")
        self.assertAlmostEqual(v2_metric.value["dkl"], v1_record["dkl"], places=12)
        self.assertAlmostEqual(
            v2_metric.value["expressibility"],
            v1_record["expressibility"],
            places=12,
        )
        self.assertEqual(v2_metric.metadata["rng_backend"], "numpy.random.default_rng")

    def test_trainability_matches_v1_tiny_reference_fixture(self) -> None:
        self._skip_without_optional_dependencies("numpy", "pandas", "pennylane")
        v1_trainability = self._v1_trainability_module()
        view = load_candidate_views(CANDIDATE_EXAMPLE)[0]

        def toy_state(params):
            from pennylane import numpy as pnp

            angle = params[0] + params[1]
            return pnp.array([pnp.cos(angle), pnp.sin(angle), 0.0, 0.0], dtype=complex)

        v1_record = v1_trainability.compute_trainability_for_circuit(
            view.candidate_id,
            toy_state,
            parameter_count=view.parameter_count,
            layer=1,
            config=v1_trainability.TrainabilityConfig(
                n_qubits=view.n_qubits,
                n_repeats=3,
                rng_seed=123,
            ),
        )
        v2_metric = compute_v2_trainability(
            view,
            toy_state,
            config=V2TrainabilityConfig(
                n_qubits=view.n_qubits,
                n_repeats=3,
                rng_seed=123,
            ),
            permissions=AnalyzerExecutionPermissions(allow_expensive_metrics=True),
        )

        self.assertEqual(v2_metric.status, "computed")
        self.assertAlmostEqual(
            v2_metric.value["trainability"],
            v1_record["trainability_score"],
            places=12,
        )
        self.assertEqual(v2_metric.metadata["gradient_backend"], "pennylane.qml.grad")

    def test_numeric_reference_fixture_directory_is_present(self) -> None:
        missing = [
            name
            for name in ("numpy", "pandas", "pennylane")
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            self.skipTest(
                "Numeric v1/v2 reference fixtures require optional dependencies: "
                + ", ".join(missing)
            )

        manifest = REFERENCE_FIXTURES / "manifest.json"
        self.assertTrue(manifest.is_file())

    def _skip_without_optional_dependencies(self, *names: str) -> None:
        missing = [name for name in names if importlib.util.find_spec(name) is None]
        if missing:
            self.skipTest("Optional dependencies unavailable: " + ", ".join(missing))

    def _v1_expressibility_module(self):
        self._ensure_v1_src_path()
        from ansatz_analyzer.metrics import expressibility

        return expressibility

    def _v1_trainability_module(self):
        self._ensure_v1_src_path()
        from ansatz_analyzer.metrics import trainability

        return trainability

    def _ensure_v1_src_path(self) -> None:
        if not V1_SRC.exists():
            self.skipTest("Legacy Verfeinert v1 source is not available.")
        value = str(V1_SRC)
        if value not in sys.path:
            sys.path.insert(0, value)


if __name__ == "__main__":
    unittest.main()

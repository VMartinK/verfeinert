"""Phase 8.1 package-hardening tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verfeinert.core import load_schema, read_schema_text, schema_filename, schema_names


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_SCHEMAS = PROJECT_ROOT / "schemas"
FRAMEWORK_ROOT = PROJECT_ROOT / "verfeinert"


class PackageHardeningTests(unittest.TestCase):
    def test_packaged_schema_resources_match_root_schemas(self) -> None:
        for name in schema_names():
            with self.subTest(schema=name):
                root_text = (ROOT_SCHEMAS / schema_filename(name)).read_text(encoding="utf-8")
                self.assertEqual(read_schema_text(name), root_text)
                self.assertEqual(load_schema(name), json.loads(root_text))

    def test_public_imports_and_schema_loading_work_from_external_cwd(self) -> None:
        code = """
import json
from verfeinert.core import load_schema, schema_names
from verfeinert.ansatz_generator import build_sanz19_candidate_record, export_candidate_json
from verfeinert.ansatz_analyzer import validate_candidate_document
from verfeinert.ansatz_evolver import CandidateRef
from verfeinert.workflow import WorkflowConfig

record = build_sanz19_candidate_record("A02", 1, n_qubits=2)
candidate = export_candidate_json(
    record,
    config=None,
    candidate_id="external-style-candidate",
)
validate_candidate_document(candidate)
CandidateRef(candidate_id=candidate["candidate_id"])
WorkflowConfig.from_mapping({
    "run_id": "external-style-import",
    "output_root": "outputs",
})
print(json.dumps({
    "schema_count": len(schema_names()),
    "candidate_schema": load_schema("candidate")["$id"],
    "candidate_id": candidate["candidate_id"],
}, sort_keys=True))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-verfeinert")
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=tmp,
                env=env,
                check=True,
                text=True,
                capture_output=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema_count"], 5)
        self.assertEqual(payload["candidate_id"], "external-style-candidate")
        self.assertTrue(payload["candidate_schema"].endswith("/candidate.schema.json"))

    def test_framework_schema_validation_uses_package_resources(self) -> None:
        forbidden_tokens = (
            'PROJECT_ROOT = Path(__file__).resolve().parents[2]',
            'SCHEMAS_ROOT = PROJECT_ROOT / "schemas"',
            'parents[3] / "schemas"',
        )
        checked = [
            FRAMEWORK_ROOT / "ansatz_generator" / "exporters" / "candidate_json.py",
            FRAMEWORK_ROOT / "ansatz_analyzer" / "validation.py",
            FRAMEWORK_ROOT / "ansatz_evolver" / "validation.py",
        ]
        violations = []
        for path in checked:
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token!r}")
        self.assertEqual(violations, [])

    def test_reproduction_scripts_do_not_bootstrap_package_root(self) -> None:
        scripts = [
            PROJECT_ROOT / "examples" / "CX01_reproduction" / "scripts" / "run_cx01_reproduction.py",
            PROJECT_ROOT / "examples" / "MIXT5G_reproduction" / "scripts" / "run_mixt5g_reproduction.py",
        ]
        violations = []
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            if "sys.path.insert" in text or "PROJECT_ROOT = Path(__file__).resolve().parents[3]" in text:
                violations.append(str(script.relative_to(PROJECT_ROOT)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

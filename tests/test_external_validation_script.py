"""Tests for the Phase 8.3 external validation script."""

from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from scripts.validate_external_install import (
    PUBLIC_IMPORT_CHECK,
    build_install_command,
    build_validation_steps,
    venv_python,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "validate_external_install.py"


class ExternalValidationScriptTests(unittest.TestCase):
    def test_install_command_targets_source_root_without_shell(self) -> None:
        command = build_install_command("/tmp/venv/bin/python", PROJECT_ROOT)

        self.assertEqual(command[:4], ("/tmp/venv/bin/python", "-m", "pip", "install"))
        self.assertEqual(command[-1], str(PROJECT_ROOT.resolve(strict=False)))

    def test_validation_steps_use_public_examples_and_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "outputs"
            steps = build_validation_steps(
                python_executable="/tmp/venv/bin/python",
                source_root=PROJECT_ROOT,
                output_root=output_root,
                work_root=Path(tmp) / "work",
            )

        self.assertEqual([step.name for step in steps], [
            "public-imports-and-packaged-schemas",
            "cx01-smoke-example",
            "mixt5g-smoke-example",
        ])
        commands = [" ".join(step.command) for step in steps]
        self.assertIn("run_cx01_reproduction.py", commands[1])
        self.assertIn("run_mixt5g_reproduction.py", commands[2])
        self.assertIn(str(output_root), commands[1])
        self.assertIn(str(output_root), commands[2])

    def test_venv_python_is_platform_specific_path(self) -> None:
        path = venv_python("/tmp/example-venv")

        self.assertTrue(str(path).endswith(("bin/python", "Scripts/python.exe")))

    def test_script_has_no_direct_framework_or_sys_path_bootstrap_imports(self) -> None:
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"), filename=str(SCRIPT_PATH))
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("verfeinert"):
                violations.append(node.module)
            if isinstance(node, ast.Import):
                violations.extend(alias.name for alias in node.names if alias.name.startswith("verfeinert"))
        self.assertEqual(violations, [])
        self.assertNotIn("sys.path.insert", SCRIPT_PATH.read_text(encoding="utf-8"))

    def test_public_import_check_uses_public_api_names(self) -> None:
        self.assertIn("from verfeinert.core import", PUBLIC_IMPORT_CHECK)
        self.assertIn("from verfeinert.ansatz_generator import", PUBLIC_IMPORT_CHECK)
        self.assertIn("from verfeinert.ansatz_analyzer import", PUBLIC_IMPORT_CHECK)
        self.assertIn("from verfeinert.ansatz_evolver import", PUBLIC_IMPORT_CHECK)
        self.assertIn("from verfeinert.workflow import", PUBLIC_IMPORT_CHECK)
        self.assertNotIn("._", PUBLIC_IMPORT_CHECK)


if __name__ == "__main__":
    unittest.main()

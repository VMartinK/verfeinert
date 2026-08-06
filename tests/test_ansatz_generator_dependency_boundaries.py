"""Dependency boundary tests for ansatz_generator."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_ROOT = PROJECT_ROOT / "verfeinert" / "ansatz_generator"

FORBIDDEN_IMPORTS = {
    "verfeinert.ansatz_analyzer",
    "verfeinert.ansatz_evolver",
    "ansatz_analyzer",
    "ansatz_evolver",
    "Thesis_Data_Processing",
    "matplotlib",
    "pennylane",
    "pandas",
    "notebook",
    "nbformat",
    "nbclient",
}

FORBIDDEN_PATH_TOKENS = (
    "Thesis_Data_Processing",
    "analysis_results",
    "analysis_exports",
    "/home/",
    "tmp/candidate_compilation_boundary",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class AnsatzGeneratorDependencyBoundaryTests(unittest.TestCase):
    def test_generator_does_not_import_forbidden_modules_or_paths(self) -> None:
        violations: list[str] = []
        for path in sorted(GENERATOR_ROOT.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for module in _imported_modules(path):
                if any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")
            for token in FORBIDDEN_PATH_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

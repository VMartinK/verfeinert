"""Dependency boundary tests for the lightweight core package."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = PROJECT_ROOT / "verfeinert" / "core"

FORBIDDEN_IMPORTS = {
    "verfeinert.ansatz_generator",
    "verfeinert.ansatz_analyzer",
    "verfeinert.ansatz_evolver",
    "pennylane",
    "matplotlib",
    "pandas",
    "numpy",
    "notebook",
    "nbformat",
    "nbclient",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class CoreDependencyBoundaryTests(unittest.TestCase):
    def test_core_does_not_import_scientific_or_heavy_modules(self) -> None:
        violations: list[str] = []
        for path in sorted(CORE_ROOT.rglob("*.py")):
            for module in _imported_modules(path):
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_IMPORTS
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {module}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

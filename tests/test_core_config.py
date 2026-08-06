"""Tests for Verfeinert core configuration models."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import yaml

from verfeinert.core.config import (
    ExecutionConfig,
    PathConfig,
    RunConfig,
    load_run_config_yaml,
)
from verfeinert.core.io.paths import PACKAGE_SOURCE_ROOT
from verfeinert.core.validation import CoreValidationError


class CoreConfigTests(unittest.TestCase):
    def test_python_and_yaml_configs_are_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            output_root = tmp_path / "outputs"
            yaml_path = tmp_path / "run.yaml"
            payload = {
                "schema_version": "verfeinert.run_config.v1",
                "run_id": "cx01-single-analysis",
                "random_seed": 123,
                "execution": {
                    "mode": "multiprocessing",
                    "parallelize_candidates": True,
                    "worker_count": 2,
                    "scope": "candidate",
                },
                "paths": {
                    "input_root": str(input_root),
                    "output_root": str(output_root),
                },
            }
            with yaml_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle)

            python_config = RunConfig(
                run_id="cx01-single-analysis",
                random_seed=123,
                execution=ExecutionConfig(
                    mode="multiprocessing",
                    parallelize_candidates=True,
                    worker_count=2,
                ),
                paths=PathConfig(input_root=input_root, output_root=output_root),
            )

            self.assertEqual(load_run_config_yaml(yaml_path), python_config)
            self.assertEqual(load_run_config_yaml(yaml_path).to_dict(), python_config.to_dict())

    def test_invalid_execution_config_is_rejected(self) -> None:
        with self.assertRaises(CoreValidationError):
            ExecutionConfig(mode="threading")  # type: ignore[arg-type]
        with self.assertRaises(CoreValidationError):
            ExecutionConfig(mode="sequential", parallelize_candidates=True)
        with self.assertRaises(CoreValidationError):
            ExecutionConfig(mode="sequential", worker_count=2)
        with self.assertRaises(CoreValidationError):
            ExecutionConfig(
                mode="multiprocessing",
                parallelize_candidates=False,
                worker_count=2,
            )

    def test_invalid_path_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaises(CoreValidationError):
                PathConfig.from_mapping({"input_root": str(tmp_path / "inputs")})
            with self.assertRaises(ValueError):
                PathConfig(input_root=tmp_path / "same", output_root=tmp_path / "same")
            with self.assertRaises(ValueError):
                PathConfig(
                    input_root=tmp_path / "inputs",
                    output_root=tmp_path / "inputs" / "outputs",
                )
            with self.assertRaises(ValueError):
                PathConfig(
                    input_root=tmp_path / "inputs",
                    output_root=PACKAGE_SOURCE_ROOT / "generated",
                )


if __name__ == "__main__":
    unittest.main()

"""Tests for the public Verfeinert CLI."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from verfeinert.cli import (
    CONFIG_ERROR_EXIT_CODE,
    WORKFLOW_ERROR_EXIT_CODE,
    main as cli_main,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-21T00:00:00Z"


def _workflow_mapping(
    output_root: Path,
    *,
    run_id: str,
    scientific_execution: tuple[str, ...] = ("generate", "analyze"),
    postprocessing: tuple[str, ...] = (),
    checkpoint: bool = False,
) -> dict:
    return {
        "run": {
            "run_id": run_id,
            "created_at": CREATED_AT,
            "random_seed": 23,
        },
        "paths": {
            "output_root": str(output_root),
        },
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": list(scientific_execution),
            "postprocessing": list(postprocessing),
            "checkpoint": {"enabled": checkpoint},
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "cli",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {
                "reference_bounds": {
                    "parameter_count": {"min": 0, "max": 16},
                    "depth": {"min": 0, "max": 32},
                    "two_qubit_operation_count": {"min": 0, "max": 8},
                },
            },
            "ranking": {
                "score_components": {"cost.structural_cost": 1.0},
                "combination": "weighted_sum",
                "ascending": True,
            },
        },
        "evolver": {
            "selection_mode": "fitness",
            "policy_id": "cli-selection",
            "metric_name": "structural_cost",
            "keep": 1,
            "direction": "minimize",
            "max_generations": 1,
        },
    }


def _write_config(path: Path, mapping: dict) -> Path:
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = cli_main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_help_lists_reproducible_workflow_commands(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        completed = subprocess.run(
            [sys.executable, "-m", "verfeinert.cli", "--help"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("validate", completed.stdout)
        self.assertIn("run", completed.stdout)
        self.assertIn("resume", completed.stdout)

    def test_validate_reports_deterministic_config_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = _write_config(
                root / "workflow.json",
                _workflow_mapping(root / "outputs", run_id="cli-validate", checkpoint=True),
            )

            exit_code, stdout, stderr = _run_cli(["validate", str(config_path)])

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["terminal_status"], "valid")
        self.assertEqual(payload["run_id"], "cli-validate")
        self.assertTrue(payload["checkpoint_enabled"])
        self.assertEqual(payload["scientific_execution"], ["generate", "analyze"])

    def test_invalid_config_returns_config_error_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = _workflow_mapping(root / "outputs", run_id="cli-invalid")
            mapping["generation"]["family"] = "campaign_specific"
            config_path = _write_config(root / "invalid.json", mapping)

            validate_exit, validate_stdout, validate_stderr = _run_cli(
                ["validate", str(config_path)],
            )
            run_exit, run_stdout, run_stderr = _run_cli(["run", str(config_path)])

        self.assertEqual(validate_exit, CONFIG_ERROR_EXIT_CODE)
        self.assertEqual(validate_stdout, "")
        self.assertIn("generation.family", validate_stderr)
        self.assertEqual(run_exit, WORKFLOW_ERROR_EXIT_CODE)
        self.assertEqual(run_stdout, "")
        self.assertIn("generation.family", run_stderr)

    def test_run_reports_terminal_status_and_artifact_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = _write_config(
                root / "workflow.json",
                _workflow_mapping(
                    root / "outputs",
                    run_id="cli-run",
                    postprocessing=("ranking", "report"),
                    checkpoint=True,
                ),
            )

            exit_code, stdout, stderr = _run_cli(["run", str(config_path)])
            payload = json.loads(stdout)
            inspect_exit, inspect_stdout, inspect_stderr = _run_cli(
                ["inspect", payload["report_json_path"]],
            )

            checkpoint_exists = Path(payload["checkpoint_path"]).is_file()
            report_json_exists = Path(payload["report_json_path"]).is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["terminal_status"], "completed")
        self.assertEqual(payload["run_id"], "cli-run")
        self.assertTrue(checkpoint_exists)
        self.assertTrue(report_json_exists)
        self.assertEqual(payload["executed_operations"], ["generate", "analyze", "ranking", "report"])
        self.assertEqual(inspect_exit, 0)
        self.assertEqual(inspect_stderr, "")
        self.assertIn("# Workflow Report: cli-run", inspect_stdout)

    def test_resume_uses_public_runner_checkpoint_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_config_path = _write_config(
                root / "generate.json",
                _workflow_mapping(
                    root / "outputs",
                    run_id="cli-resume",
                    scientific_execution=("generate",),
                    checkpoint=True,
                ),
            )
            generate_exit, generate_stdout, generate_stderr = _run_cli(
                ["run", str(generate_config_path)],
            )
            generated = json.loads(generate_stdout)
            checkpoint_path = generated["checkpoint_path"]

            resume_config_path = _write_config(
                root / "resume.json",
                _workflow_mapping(
                    root / "outputs",
                    run_id="cli-resume",
                    scientific_execution=("analyze",),
                ),
            )
            resume_exit, resume_stdout, resume_stderr = _run_cli(
                ["resume", checkpoint_path, "--config", str(resume_config_path)],
            )
            resumed = json.loads(resume_stdout)

        self.assertEqual(generate_exit, 0)
        self.assertEqual(generate_stderr, "")
        self.assertEqual(resume_exit, 0)
        self.assertEqual(resume_stderr, "")
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["resumed_from"], checkpoint_path)
        self.assertEqual(resumed["executed_operations"], ["analyze"])
        self.assertEqual(resumed["candidate_ids"], ["cli-a02-l1"])

    def test_resume_accepts_run_directory_without_explicit_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_config_path = _write_config(
                root / "generate.json",
                _workflow_mapping(
                    root / "outputs",
                    run_id="cli-resume-run-dir",
                    scientific_execution=("generate",),
                    checkpoint=True,
                ),
            )
            generate_exit, generate_stdout, generate_stderr = _run_cli(
                ["run", str(generate_config_path)],
            )
            generated = json.loads(generate_stdout)
            run_root = Path(generated["run_root"])
            checkpoint_path = str(run_root / "checkpoints" / "latest.json")

            resume_exit, resume_stdout, resume_stderr = _run_cli(["resume", str(run_root)])
            resumed = json.loads(resume_stdout)

        self.assertEqual(generate_exit, 0)
        self.assertEqual(generate_stderr, "")
        self.assertEqual(resume_exit, 0)
        self.assertEqual(resume_stderr, "")
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["resumed_from"], checkpoint_path)
        self.assertEqual(resumed["run_id"], "cli-resume-run-dir")

    def test_pyproject_defines_install_time_entry_point(self) -> None:
        pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(
            pyproject["project"]["scripts"]["verfeinert"],
            "verfeinert.cli:main",
        )


if __name__ == "__main__":
    unittest.main()

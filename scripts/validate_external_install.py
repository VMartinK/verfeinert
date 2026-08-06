"""Validate Verfeinert from an external user's installation perspective."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence


PUBLIC_IMPORT_CHECK = r"""
import json
from verfeinert.core import load_schema, schema_names
from verfeinert.ansatz_generator import build_sanz19_candidate_record, export_candidate_json
from verfeinert.ansatz_analyzer import validate_candidate_document
from verfeinert.ansatz_evolver import CandidateRef
from verfeinert.workflow import WorkflowConfig

record = build_sanz19_candidate_record("A02", 1, n_qubits=2)
candidate = export_candidate_json(record, candidate_id="external-validation-candidate")
validate_candidate_document(candidate)
ref = CandidateRef(candidate_id=candidate["candidate_id"])
workflow = WorkflowConfig.from_mapping({
    "run_id": "external-validation",
    "output_root": "external-validation-output",
})
print(json.dumps({
    "schema_count": len(schema_names()),
    "candidate_schema": load_schema("candidate")["$id"],
    "candidate_id": ref.candidate_id,
    "workflow_run_id": workflow.run_id,
}, sort_keys=True))
"""


class ExternalValidationError(RuntimeError):
    """Raised when external validation cannot complete successfully."""


@dataclass(frozen=True)
class ValidationStep:
    """One subprocess command in the external validation workflow."""

    name: str
    command: tuple[str, ...]
    cwd: Path

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe command description."""
        return {
            "name": self.name,
            "command": list(self.command),
            "cwd": str(self.cwd),
        }


@dataclass(frozen=True)
class ValidationStepResult:
    """Result of one external validation subprocess."""

    step: ValidationStep
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """Whether the subprocess completed successfully."""
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-safe result."""
        return {
            **self.step.to_dict(),
            "returncode": self.returncode,
            "passed": self.passed,
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
        }


def venv_python(venv_root: str | Path) -> Path:
    """Return the Python executable inside a virtual environment."""
    root = Path(venv_root)
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def build_install_command(
    python_executable: str | Path,
    source_root: str | Path,
) -> tuple[str, ...]:
    """Build the package install command for a validation venv."""
    return (
        str(python_executable),
        "-m",
        "pip",
        "install",
        str(Path(source_root).resolve(strict=False)),
    )


def build_validation_steps(
    *,
    python_executable: str | Path,
    source_root: str | Path,
    output_root: str | Path,
    work_root: str | Path,
) -> tuple[ValidationStep, ...]:
    """Build post-install external validation steps."""
    source = Path(source_root).resolve(strict=False)
    output = Path(output_root).resolve(strict=False)
    work = Path(work_root).resolve(strict=False)
    python = str(python_executable)
    return (
        ValidationStep(
            name="public-imports-and-packaged-schemas",
            command=(python, "-c", PUBLIC_IMPORT_CHECK),
            cwd=work,
        ),
        ValidationStep(
            name="cx01-smoke-example",
            command=(
                python,
                str(source / "examples" / "CX01_reproduction" / "scripts" / "run_cx01_reproduction.py"),
                "--profile",
                "smoke",
                "--output-root",
                str(output / "cx01_reproduction"),
            ),
            cwd=work,
        ),
        ValidationStep(
            name="mixt5g-smoke-example",
            command=(
                python,
                str(source / "examples" / "MIXT5G_reproduction" / "scripts" / "run_mixt5g_reproduction.py"),
                "--profile",
                "smoke",
                "--output-root",
                str(output / "mixt5g_reproduction"),
            ),
            cwd=work,
        ),
    )


def run_external_validation(
    *,
    source_root: str | Path,
    output_root: str | Path | None = None,
    work_root: str | Path | None = None,
    keep_work_root: bool = False,
    system_site_packages: bool = False,
) -> dict[str, Any]:
    """Run clean-environment installation and public workflow smoke validation."""
    source = Path(source_root).resolve(strict=False)
    if not (source / "pyproject.toml").is_file():
        raise ExternalValidationError(f"source_root does not contain pyproject.toml: {source}")

    owned_work_root = work_root is None
    work = Path(work_root).resolve(strict=False) if work_root is not None else Path(tempfile.mkdtemp(prefix="verfeinert-external-"))
    output = Path(output_root).resolve(strict=False) if output_root is not None else work / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    venv_root = work / "venv"
    report_path = output / "external_validation_summary.json"
    results: list[ValidationStepResult] = []
    status = "failed"
    try:
        _create_venv(venv_root, system_site_packages=system_site_packages)
        python = venv_python(venv_root)
        install_step = ValidationStep(
            name="install-package",
            command=build_install_command(python, source),
            cwd=work,
        )
        install_result = _run_step(install_step)
        results.append(install_result)
        if not install_result.passed:
            return _write_report(
                report_path,
                status=status,
                source_root=source,
                output_root=output,
                work_root=work,
                steps=results,
                blocker="package installation failed",
            )

        for step in build_validation_steps(
            python_executable=python,
            source_root=source,
            output_root=output,
            work_root=work,
        ):
            result = _run_step(step)
            results.append(result)
            if not result.passed:
                return _write_report(
                    report_path,
                    status=status,
                    source_root=source,
                    output_root=output,
                    work_root=work,
                    steps=results,
                    blocker=f"{step.name} failed",
                )
        status = "passed"
        return _write_report(
            report_path,
            status=status,
            source_root=source,
            output_root=output,
            work_root=work,
            steps=results,
            blocker=None,
        )
    finally:
        if owned_work_root and not keep_work_root:
            shutil.rmtree(work, ignore_errors=True)


def _create_venv(venv_root: Path, *, system_site_packages: bool) -> None:
    command = [sys.executable, "-m", "venv"]
    if system_site_packages:
        command.append("--system-site-packages")
    command.append(str(venv_root))
    subprocess.run(command, check=True)


def _run_step(step: ValidationStep) -> ValidationStepResult:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-verfeinert")
    completed = subprocess.run(
        step.command,
        cwd=step.cwd,
        env=env,
        text=True,
        capture_output=True,
    )
    return ValidationStepResult(
        step=step,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _write_report(
    report_path: Path,
    *,
    status: str,
    source_root: Path,
    output_root: Path,
    work_root: Path,
    steps: Sequence[ValidationStepResult],
    blocker: str | None,
) -> dict[str, Any]:
    report = {
        "schema_version": "verfeinert.external_validation.v1",
        "status": status,
        "source_root": str(source_root),
        "output_root": str(output_root),
        "work_root": str(work_root),
        "blocker": blocker,
        "steps": [step.to_dict() for step in steps],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the external validation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--work-root", default=None)
    parser.add_argument("--keep-work-root", action="store_true")
    parser.add_argument("--system-site-packages", action="store_true")
    args = parser.parse_args(argv)
    report = run_external_validation(
        source_root=args.source_root,
        output_root=args.output_root,
        work_root=args.work_root,
        keep_work_root=args.keep_work_root,
        system_site_packages=args.system_site_packages,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

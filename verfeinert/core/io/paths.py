"""Path guards for keeping source, experiment inputs, and outputs separate."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


class PathValidationError(ValueError):
    """Raised when a configured experiment path violates core I/O policy."""


PACKAGE_SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _as_path(value: str | Path, field_name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        if not value.strip():
            raise PathValidationError(f"{field_name} must not be empty.")
        path = Path(value)
    else:
        raise PathValidationError(f"{field_name} must be a path-like value.")
    return path.expanduser()


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_separate_roots(
    *,
    input_root: str | Path,
    output_root: str | Path,
    source_root: str | Path = PACKAGE_SOURCE_ROOT,
) -> tuple[Path, Path]:
    """Validate that source, input, and output roots are caller-owned regions."""
    input_path = _resolved(_as_path(input_root, "input_root"))
    output_path = _resolved(_as_path(output_root, "output_root"))
    source_path = _resolved(_as_path(source_root, "source_root"))

    if input_path == output_path:
        raise PathValidationError("input_root and output_root must be different paths.")
    if _is_relative_to(output_path, input_path) or _is_relative_to(input_path, output_path):
        raise PathValidationError("input_root and output_root must not be nested.")
    if _is_relative_to(output_path, source_path) or _is_relative_to(source_path, output_path):
        raise PathValidationError("output_root must be separate from package source.")
    return input_path, output_path


def ensure_output_root(
    output_root: str | Path,
    *,
    input_roots: Iterable[str | Path] = (),
    source_root: str | Path = PACKAGE_SOURCE_ROOT,
) -> Path:
    """Validate and create a caller-provided output root."""
    output_path = _resolved(_as_path(output_root, "output_root"))
    source_path = _resolved(_as_path(source_root, "source_root"))
    if _is_relative_to(output_path, source_path) or _is_relative_to(source_path, output_path):
        raise PathValidationError("output_root must be separate from package source.")
    for index, input_root in enumerate(input_roots):
        input_path = _resolved(_as_path(input_root, f"input_roots[{index}]"))
        if output_path == input_path:
            raise PathValidationError("output_root must not equal an input root.")
        if _is_relative_to(output_path, input_path) or _is_relative_to(input_path, output_path):
            raise PathValidationError("output_root must not be nested with input roots.")
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


__all__ = [
    "PACKAGE_SOURCE_ROOT",
    "PathValidationError",
    "ensure_output_root",
    "validate_separate_roots",
]

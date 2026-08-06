"""Visualization export helpers with lazy plotting dependencies."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

from verfeinert.core.io import ensure_output_root


class VisualizationDependencyError(ImportError):
    """Raised when an optional visualization dependency is unavailable."""


def require_pyplot():
    """Return matplotlib.pyplot or raise a clear optional-dependency error."""
    if importlib.util.find_spec("matplotlib") is None:
        raise VisualizationDependencyError(
            "Matplotlib is required for plotting. Install the 'visualization' extra.",
        )
    return importlib.import_module("matplotlib.pyplot")


def save_figure(
    figure,
    path: str | Path,
    *,
    input_roots=(),
    **savefig_kwargs,
) -> Path:
    """Save a figure under a caller-provided guarded output path."""
    target = Path(path).expanduser().resolve(strict=False)
    ensure_output_root(target.parent, input_roots=input_roots)
    figure.savefig(target, **savefig_kwargs)
    return target


__all__ = [
    "VisualizationDependencyError",
    "require_pyplot",
    "save_figure",
]

"""Visualization export helpers with lazy plotting dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
from pathlib import Path
from typing import Any

from verfeinert.core.io import ensure_output_root
from verfeinert.core.io.serialization import to_json_safe


class VisualizationDependencyError(ImportError):
    """Raised when an optional visualization dependency is unavailable."""


@dataclass(frozen=True)
class FigureExportConfig:
    """Generic figure export options."""

    dpi: int = 300
    bbox_inches: str = "tight"
    transparent: bool = False
    facecolor: str = "white"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe export payload."""
        return to_json_safe(self.__dict__)


def require_pyplot():
    """Return matplotlib.pyplot or raise a clear optional-dependency error."""
    try:
        matplotlib_spec = importlib.util.find_spec("matplotlib")
    except ModuleNotFoundError as exc:
        raise VisualizationDependencyError(
            "Matplotlib is required for plotting. Install the 'visualization' extra.",
        ) from exc
    if matplotlib_spec is None:
        raise VisualizationDependencyError(
            "Matplotlib is required for plotting. Install the 'visualization' extra.",
        )
    try:
        return importlib.import_module("matplotlib.pyplot")
    except ModuleNotFoundError as exc:
        raise VisualizationDependencyError(
            "Matplotlib is required for plotting. Install the 'visualization' extra.",
        ) from exc


def save_figure(
    figure,
    path: str | Path,
    *,
    config: FigureExportConfig | None = None,
    input_roots=(),
    **savefig_kwargs,
) -> Path:
    """Save a figure under a caller-provided guarded output path."""
    target = Path(path).expanduser().resolve(strict=False)
    ensure_output_root(target.parent, input_roots=input_roots)
    resolved = config or FigureExportConfig()
    options = resolved.to_dict()
    options.update(savefig_kwargs)
    figure.savefig(target, **options)
    return target


__all__ = [
    "FigureExportConfig",
    "VisualizationDependencyError",
    "require_pyplot",
    "save_figure",
]

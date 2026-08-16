"""Visualization export helpers with lazy plotting dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Iterable

from verfeinert.core.io import ensure_output_root
from verfeinert.core.io.serialization import to_json_safe

PUBLICATION_EXPORT_FORMATS = ("png", "pdf", "svg")
_PUBLICATION_EXPORT_FORMAT_SET = frozenset(PUBLICATION_EXPORT_FORMATS)


class VisualizationDependencyError(ImportError):
    """Raised when an optional visualization dependency is unavailable."""


@dataclass(frozen=True)
class FigureExportConfig:
    """Generic figure export options."""

    dpi: int = 600
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


def save_publication_figure(
    figure,
    basename: str | Path,
    *,
    formats: Iterable[str] = PUBLICATION_EXPORT_FORMATS,
    config: FigureExportConfig | None = None,
    input_roots=(),
    overwrite: bool = False,
    **savefig_kwargs,
) -> dict[str, Path]:
    """Save a publication figure to all requested formats after full preflight."""
    resolved_formats = _normalize_formats(formats)
    base = _resolve_publication_basename(basename)
    targets = {
        fmt: base.with_name(f"{base.name}.{fmt}")
        for fmt in resolved_formats
    }
    for parent in dict.fromkeys(path.parent for path in targets.values()):
        ensure_output_root(parent, input_roots=input_roots)
    if not overwrite:
        existing = [path for path in targets.values() if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing)
            raise FileExistsError(f"publication figure destination already exists: {names}")

    resolved = config or FigureExportConfig()
    base_options = resolved.to_dict()
    base_options.update(savefig_kwargs)
    written: dict[str, Path] = {}
    for fmt, target in targets.items():
        options = dict(base_options)
        options["format"] = fmt
        figure.savefig(target, **options)
        written[fmt] = target
    return written


def _resolve_publication_basename(basename: str | Path) -> Path:
    base = Path(basename).expanduser().resolve(strict=False)
    if not base.name:
        raise ValueError("basename must include a semantic file name.")
    if base.suffix or base.name.endswith("."):
        raise ValueError("publication figure basename must be supplied without a file extension.")
    return base


def _normalize_formats(formats: Iterable[str]) -> tuple[str, ...]:
    if isinstance(formats, (str, bytes, bytearray)):
        raise ValueError("formats must be an iterable of format names, not a single string.")
    resolved = []
    seen = set()
    for raw_format in formats:
        if not isinstance(raw_format, str):
            raise ValueError("publication export formats must be strings.")
        fmt = raw_format.strip().lower()
        if (
            not fmt
            or fmt.startswith(".")
            or "/" in fmt
            or "\\" in fmt
            or any(character.isspace() for character in fmt)
            or not fmt.isalnum()
        ):
            raise ValueError(f"malformed publication export format: {raw_format!r}")
        if fmt not in _PUBLICATION_EXPORT_FORMAT_SET:
            allowed = ", ".join(PUBLICATION_EXPORT_FORMATS)
            raise ValueError(f"unsupported publication export format: {fmt!r}; expected one of {allowed}")
        if fmt in seen:
            raise ValueError(f"duplicate publication export format: {fmt!r}")
        seen.add(fmt)
        resolved.append(fmt)
    if not resolved:
        raise ValueError("at least one publication export format is required.")
    return tuple(resolved)


__all__ = [
    "FigureExportConfig",
    "PUBLICATION_EXPORT_FORMATS",
    "VisualizationDependencyError",
    "require_pyplot",
    "save_figure",
    "save_publication_figure",
]

"""Neutral default plotting style for Verfeinert visualizations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verfeinert.core.io.serialization import to_json_safe


@dataclass(frozen=True)
class VisualizationStyle:
    """Central style configuration for analyzer visualizations."""

    font_family: str = "DejaVu Sans"
    font_size: int = 11
    title_size: int = 13
    label_size: int = 12
    legend_size: int = 10
    figure_size: tuple[float, float] = (13.60, 7.65)
    compact_figure_size: tuple[float, float] = (6.0, 4.0)
    wide_figure_size: tuple[float, float] = (18.0, 10.125)
    dpi: int = 300
    score_colormap: str = "plasma"
    palette: dict[str, str] = field(
        default_factory=lambda: {
            "frontier": "#111111",
            "dominated": "#7A7A7A",
            "reference": "#666666",
            "ranking": "#2F6F9F",
            "lineage": "#2A9D8F",
            "eligible": "#2F6F9F",
            "ineligible": "#A0A0A0",
        },
    )
    markers: dict[str, str] = field(
        default_factory=lambda: {
            "frontier": "o",
            "dominated": "x",
            "reference": "s",
            "ranking": "o",
        },
    )
    legend_frame: bool = False
    legend_location: str = "best"
    export_format: str = "png"
    bbox_inches: str = "tight"
    transparent: bool = False
    facecolor: str = "white"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe style payload."""
        return to_json_safe(self.__dict__)


DEFAULT_STYLE = VisualizationStyle()


__all__ = [
    "DEFAULT_STYLE",
    "VisualizationStyle",
]

"""Thesis-inspired centralized plotting style."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verfeinert.core.io.serialization import to_json_safe


@dataclass(frozen=True)
class VisualizationStyle:
    """Central style configuration for analyzer visualizations."""

    font_family: str = "DejaVu Sans"
    font_size: int = 10
    title_size: int = 12
    label_size: int = 10
    legend_size: int = 9
    figure_size: tuple[float, float] = (6.0, 4.0)
    dpi: int = 150
    palette: dict[str, str] = field(
        default_factory=lambda: {
            "frontier": "#1f77b4",
            "dominated": "#7f7f7f",
            "reference": "#2ca02c",
            "ranking": "#9467bd",
            "lineage": "#d62728",
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
    export_format: str = "png"
    bbox_inches: str = "tight"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe style payload."""
        return to_json_safe(self.__dict__)


THESIS_STYLE = VisualizationStyle()


__all__ = [
    "THESIS_STYLE",
    "VisualizationStyle",
]

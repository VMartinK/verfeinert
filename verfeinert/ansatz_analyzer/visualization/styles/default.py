"""Publication default plotting style for Verfeinert visualizations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verfeinert.core.io.serialization import to_json_safe


@dataclass(frozen=True)
class PublicationLayouts:
    """Frozen publication layout sizes for visualization suites."""

    standard: tuple[float, float] = (8.0, 4.5)
    generation_counts: tuple[float, float] = (13.0, 5.2)
    global_standard: tuple[float, float] = (12.8, 7.2)
    global_wide: tuple[float, float] = (13.6, 7.65)
    global_contribution: tuple[float, float] = (16.0, 9.0)
    global_lineage: tuple[float, float] = (18.0, 9.5)
    table_width: float = 12.8
    table_min_height: float = 1.2
    table_header_height: float = 0.45
    table_row_height: float = 0.32

    def table_figure_size(self, row_count: int) -> tuple[float, float]:
        """Return a deterministic dynamic table size for publication tables."""
        rows = max(0, int(row_count))
        height = max(self.table_min_height, self.table_header_height + rows * self.table_row_height)
        return (self.table_width, height)


@dataclass(frozen=True)
class SemanticRoleStyle:
    """Visual styling for a semantic role supplied by input data."""

    color: str
    marker: str = "o"
    size: float = 36.0
    alpha: float = 1.0
    linewidth: float = 1.0
    linestyle: str = "-"


@dataclass(frozen=True)
class VisualizationStyle:
    """Central publication style configuration for analyzer visualizations."""

    font_family: str = "DejaVu Sans"
    font_size: int = 11
    title_size: int = 13
    label_size: int = 12
    legend_size: int = 10
    figure_size: tuple[float, float] = (8.0, 4.5)
    compact_figure_size: tuple[float, float] = (6.0, 4.0)
    wide_figure_size: tuple[float, float] = (13.6, 7.65)
    dpi: int = 600
    score_colormap: str = "plasma"
    frontier_colors: tuple[str, ...] = ("#C62828", "#1565C0", "#1B5E20")
    reference_frontier_colors: tuple[str, ...] = ("#111111", "#666666", "#AAAAAA")
    layer_colors: tuple[str, ...] = ("#E69F00", "#0072B2", "#009E73")
    extra_layer_colors: tuple[str, ...] = ("#CC79A7", "#999999", "#D55E00", "#00796B")
    point_marker: str = "o"
    grid_alpha: float = 0.18
    palette: dict[str, str] = field(
        default_factory=lambda: {
            "frontier": "#C62828",
            "dominated": "#7A7A7A",
            "reference": "#666666",
            "ranking": "#1565C0",
            "lineage": "#0072B2",
            "eligible": "#1B5E20",
            "ineligible": "#A0A0A0",
            "discarded": "#BDBDBD",
            "expressibility_improvement": "#CC79A7",
            "trainability_improvement": "#56B4E9",
            "frontier_improvement": "#F1C40F",
            "new_pareto": "#F1C40F",
            "reference_frontier": "#111111",
            "primary_frontier": "#C62828",
            "global_frontier": "#1565C0",
        },
    )
    markers: dict[str, str] = field(
        default_factory=lambda: {
            "frontier": "o",
            "dominated": "x",
            "reference": "s",
            "ranking": "o",
            "discarded": "o",
            "expressibility_improvement": "o",
            "trainability_improvement": "o",
            "frontier_improvement": "*",
            "new_pareto": "*",
        },
    )
    role_styles: dict[str, SemanticRoleStyle] = field(
        default_factory=lambda: {
            "discarded": SemanticRoleStyle("#BDBDBD", marker="o", size=24, alpha=0.32),
            "expressibility_improvement": SemanticRoleStyle("#CC79A7", marker="o", size=42, alpha=0.82),
            "trainability_improvement": SemanticRoleStyle("#56B4E9", marker="o", size=42, alpha=0.82),
            "frontier_improvement": SemanticRoleStyle("#F1C40F", marker="*", size=78, alpha=0.98),
            "new_pareto": SemanticRoleStyle("#F1C40F", marker="*", size=78, alpha=0.98),
            "reference": SemanticRoleStyle("#666666", marker="s", size=38, alpha=0.9),
            "reference_frontier": SemanticRoleStyle("#111111", marker="o", size=46, alpha=0.95, linewidth=1.4),
            "primary_frontier": SemanticRoleStyle("#C62828", marker="o", size=46, alpha=0.95, linewidth=1.4),
            "global_frontier": SemanticRoleStyle("#1565C0", marker="o", size=54, alpha=0.95, linewidth=1.5),
            "frontier": SemanticRoleStyle("#C62828", marker="o", size=42, alpha=0.95),
            "dominated": SemanticRoleStyle("#7A7A7A", marker="x", size=34, alpha=0.55),
            "ranking": SemanticRoleStyle("#1565C0", marker="o", size=36, alpha=0.9),
            "lineage": SemanticRoleStyle("#0072B2", marker="o", size=36, alpha=0.9),
        },
    )
    layouts: PublicationLayouts = field(default_factory=PublicationLayouts)
    legend_frame: bool = True
    legend_location: str = "upper right"
    legend_edgecolor: str = "#B0B0B0"
    legend_framealpha: float = 0.95
    legend_fancybox: bool = False
    annotation_text_color: str = "0.15"
    export_format: str = "png"
    export_formats: tuple[str, ...] = ("png", "pdf", "svg")
    publication_export_formats: tuple[str, ...] = ("png", "pdf", "svg")
    bbox_inches: str = "tight"
    transparent: bool = False
    facecolor: str = "white"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe style payload."""
        return to_json_safe(self)


DEFAULT_STYLE = VisualizationStyle()


__all__ = [
    "DEFAULT_STYLE",
    "PublicationLayouts",
    "SemanticRoleStyle",
    "VisualizationStyle",
]

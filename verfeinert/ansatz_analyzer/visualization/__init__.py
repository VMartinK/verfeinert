"""Optional visualization layer for analyzer-derived outputs."""

from .comparison import comparison_plot_data, plot_comparison_objective_space
from .export import FigureExportConfig, VisualizationDependencyError, save_figure
from .lineage import lineage_plot_data, plot_lineage_summary
from .pareto import pareto_plot_data, plot_pareto_front
from .ranking import plot_ranking_scores, ranking_plot_data
from .styles import DEFAULT_STYLE, VisualizationStyle

__all__ = [
    "DEFAULT_STYLE",
    "FigureExportConfig",
    "VisualizationDependencyError",
    "VisualizationStyle",
    "comparison_plot_data",
    "lineage_plot_data",
    "pareto_plot_data",
    "plot_comparison_objective_space",
    "plot_lineage_summary",
    "plot_pareto_front",
    "plot_ranking_scores",
    "ranking_plot_data",
    "save_figure",
]

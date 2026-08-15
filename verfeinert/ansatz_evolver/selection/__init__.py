"""Selection policies over canonical AnalysisResult JSON."""

from .fitness import SelectionDecision, SelectionResult, select_by_fitness
from .multithreshold import select_multithreshold
from .pareto import ObjectiveSpec, dominates, non_dominated_ranks, select_pareto_front
from .strict_feedback import select_strict_pareto_feedback
from .strict_pareto import select_strict_pareto
from .thresholds import ThresholdRule, select_by_thresholds

__all__ = [
    "ObjectiveSpec",
    "SelectionDecision",
    "SelectionResult",
    "ThresholdRule",
    "dominates",
    "non_dominated_ranks",
    "select_by_fitness",
    "select_by_thresholds",
    "select_multithreshold",
    "select_pareto_front",
    "select_strict_pareto",
    "select_strict_pareto_feedback",
]

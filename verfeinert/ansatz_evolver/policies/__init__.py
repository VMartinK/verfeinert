"""Evolution policies that do not depend on scientific execution."""

from .stopping import StoppingDecision, StoppingPolicy, evaluate_stopping_conditions

__all__ = [
    "StoppingDecision",
    "StoppingPolicy",
    "evaluate_stopping_conditions",
]

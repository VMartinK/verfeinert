"""Evolution policies that do not depend on scientific execution."""

from .stopping import (
    StoppingDecision,
    StoppingPolicy,
    StoppingState,
    ThresholdPatienceState,
    evaluate_stopping_conditions,
)

__all__ = [
    "StoppingDecision",
    "StoppingPolicy",
    "StoppingState",
    "ThresholdPatienceState",
    "evaluate_stopping_conditions",
]

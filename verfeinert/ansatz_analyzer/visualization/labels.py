"""Canonical publication labels for visualization-only objective axes."""

from __future__ import annotations


PUBLICATION_TRAINABILITY_LABEL = (
    r"Trainability, "
    r"$T(H)=\frac{1}{|P(H)|}\sum_{k\in P(H)}"
    r"\mathrm{Var}\!\left[\partial_{\theta_k}\langle H\rangle\right]$"
)
PUBLICATION_EXPRESSIBILITY_LABEL = r"Expressibility, $E=-\log_{10}(D_{\mathrm{KL}})$"


def publication_objective_label(metric_name: str) -> str:
    """Return the canonical publication label for a known objective metric."""
    if metric_name == "trainability":
        return PUBLICATION_TRAINABILITY_LABEL
    if metric_name == "expressibility":
        return PUBLICATION_EXPRESSIBILITY_LABEL
    return metric_name.replace("_", " ").title()


__all__ = [
    "PUBLICATION_EXPRESSIBILITY_LABEL",
    "PUBLICATION_TRAINABILITY_LABEL",
    "publication_objective_label",
]

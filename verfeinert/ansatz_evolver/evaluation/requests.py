"""Explicit analyzer request records emitted by the evolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import CandidateRef, require_identifier, require_mapping


@dataclass(frozen=True)
class AnalysisRequest:
    """Request for external analysis of candidate references."""

    request_id: str
    candidate_refs: tuple[CandidateRef, ...]
    requested_metrics: tuple[str, ...] = ("structural_cost",)
    permissions: dict[str, Any] = field(default_factory=dict)
    output_uri: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", require_identifier(self.request_id, "request_id"))
        refs = tuple(self.candidate_refs)
        if any(not isinstance(ref, CandidateRef) for ref in refs):
            raise ValueError("candidate_refs must contain CandidateRef records.")
        object.__setattr__(self, "candidate_refs", refs)
        metrics = tuple(str(metric).strip() for metric in self.requested_metrics)
        if any(not metric for metric in metrics):
            raise ValueError("requested_metrics must not contain empty names.")
        object.__setattr__(self, "requested_metrics", metrics)
        object.__setattr__(self, "permissions", require_mapping(self.permissions, "permissions"))
        object.__setattr__(self, "provenance", require_mapping(self.provenance, "provenance"))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe request data."""
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "candidate_refs": [ref.to_ref_dict() for ref in self.candidate_refs],
            "requested_metrics": list(self.requested_metrics),
            "permissions": dict(self.permissions),
            "provenance": dict(self.provenance),
        }
        if self.output_uri is not None:
            payload["output_uri"] = self.output_uri
        return payload


__all__ = ["AnalysisRequest"]

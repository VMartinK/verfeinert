"""Execution-boundary helpers for optional analyzer metrics."""

from __future__ import annotations

import hashlib
import importlib.util
from typing import Any

from ..config import AnalyzerExecutionPermissions
from ..models import MetricRecord


class MetricRuntimeError(RuntimeError):
    """Raised when an optional metric cannot execute safely."""


def stable_metric_seed(base_seed: int | None, metric_name: str, candidate_id: str) -> int:
    """Derive a deterministic 64-bit seed from metric and candidate IDs."""
    seed = 0 if base_seed is None else int(base_seed)
    token = f"{seed}:{metric_name}:{candidate_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(token).digest()[:8], "big")


def optional_dependency_available(module_name: str) -> bool:
    """Return whether an optional runtime dependency can be imported."""
    return importlib.util.find_spec(module_name) is not None


def permission_denied_metric(
    *,
    metric_name: str,
    candidate_id: str,
    reason: str,
) -> MetricRecord:
    """Build a skipped metric record for a denied execution boundary."""
    return skipped_metric(
        metric_name=metric_name,
        candidate_id=candidate_id,
        reason=reason,
        metadata={
            "execution_boundary": "permission_denied",
            "expensive_metric": True,
            "qnodes_executed": False,
        },
    )


def skipped_metric(
    *,
    metric_name: str,
    candidate_id: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> MetricRecord:
    """Build a canonical skipped metric record."""
    return MetricRecord(
        metric_id=f"metric-{metric_name}-skipped-{candidate_id}",
        name=metric_name,
        status="skipped",
        value=None,
        metadata={
            "reason": reason,
            "expensive_metric": metric_name in {"expressibility", "trainability"},
            "qnodes_executed": False,
            **dict(metadata or {}),
        },
    )


def failed_metric(
    *,
    metric_name: str,
    candidate_id: str,
    error: str,
    metadata: dict[str, Any] | None = None,
) -> MetricRecord:
    """Build a canonical failed metric record."""
    return MetricRecord(
        metric_id=f"metric-{metric_name}-failed-{candidate_id}",
        name=metric_name,
        status="failed",
        value=None,
        error=str(error),
        metadata={
            "expensive_metric": metric_name in {"expressibility", "trainability"},
            "qnodes_executed": False,
            **dict(metadata or {}),
        },
    )


def permissions_allow_metric(
    permissions: AnalyzerExecutionPermissions,
    *,
    metric_name: str,
    requires_qnode_execution: bool,
) -> tuple[bool, str | None]:
    """Return whether permissions allow an optional metric execution."""
    if not permissions.allow_expensive_metrics:
        return False, "permissions.allow_expensive_metrics is false"
    if requires_qnode_execution and not permissions.allow_qnode_execution:
        return False, "permissions.allow_qnode_execution is false"
    return True, None


__all__ = [
    "MetricRuntimeError",
    "failed_metric",
    "optional_dependency_available",
    "permission_denied_metric",
    "permissions_allow_metric",
    "skipped_metric",
    "stable_metric_seed",
]

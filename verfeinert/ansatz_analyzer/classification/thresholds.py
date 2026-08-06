"""Threshold and eligibility classification policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from ..models import ClassificationRecord
from ..validation import validate_analysis_result_document


class ClassificationPolicyError(ValueError):
    """Raised when a classification policy cannot be evaluated."""


OPERATORS = ("le", "lt", "ge", "gt", "eq")


@dataclass(frozen=True)
class ThresholdRule:
    """Configurable threshold rule over one AnalysisResult field."""

    classification_id: str
    name: str
    field: str
    threshold: float
    operator: str = "le"
    pass_label: str = "passed"
    fail_label: str = "failed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("classification_id", "name", "field", "operator"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ClassificationPolicyError(f"{field_name} must be a non-empty string.")
            object.__setattr__(self, field_name, value.strip())
        if self.operator not in OPERATORS:
            raise ClassificationPolicyError(f"operator must be one of {OPERATORS}.")
        threshold = float(self.threshold)
        if not math.isfinite(threshold):
            raise ClassificationPolicyError("threshold must be finite.")
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))


def classify_threshold(
    result_document: Mapping[str, Any],
    rule: ThresholdRule,
) -> ClassificationRecord:
    """Classify one AnalysisResult document with a configured threshold rule."""
    document = validate_analysis_result_document(result_document)
    value = _resolve_field(document, rule.field)
    return classify_threshold_value(
        value,
        rule,
        candidate_id=document["candidate_ref"]["candidate_id"],
    )


def classify_threshold_value(
    value: float | int | None,
    rule: ThresholdRule,
    *,
    candidate_id: str | None = None,
) -> ClassificationRecord:
    """Classify a raw numeric value with a configured threshold rule."""
    passed = False
    numeric: float | None = None
    if type(value) in {int, float}:
        numeric = float(value)
        if math.isfinite(numeric):
            passed = _compare(numeric, rule.threshold, rule.operator)
    label = rule.pass_label if passed else rule.fail_label
    metadata = {
        **rule.metadata,
        "field": rule.field,
        "operator": rule.operator,
        "value": numeric,
        "passed": passed,
        "classification_policy": "threshold",
    }
    if candidate_id is not None:
        metadata["candidate_id"] = candidate_id
    return ClassificationRecord(
        classification_id=_classification_id(rule.classification_id, candidate_id),
        name=rule.name,
        label=label,
        threshold=rule.threshold,
        confidence=1.0,
        metadata=metadata,
    )


def classify_cost_eligibility(
    result_document: Mapping[str, Any],
    *,
    threshold: float,
    cost_field: str = "structural_cost",
) -> ClassificationRecord:
    """Classify whether a result is eligible under a structural-cost threshold."""
    document = validate_analysis_result_document(result_document)
    rule = ThresholdRule(
        classification_id=f"cost-eligibility-{_threshold_token(threshold)}",
        name="cost_eligibility",
        field=f"cost.{cost_field}",
        threshold=threshold,
        operator="le",
        pass_label="eligible",
        fail_label="ineligible",
        metadata={"cost_field": cost_field},
    )
    return classify_threshold(document, rule)


def classify_invalid(
    *,
    candidate_id: str,
    reason: str,
    rejected: bool = True,
    name: str = "validity",
) -> ClassificationRecord:
    """Return a deterministic invalid/rejected classification record."""
    if not reason:
        raise ClassificationPolicyError("reason must not be empty.")
    label = "rejected" if rejected else "invalid"
    return ClassificationRecord(
        classification_id=f"{name}-{candidate_id}",
        name=name,
        label=label,
        confidence=1.0,
        metadata={
            "candidate_id": candidate_id,
            "reason": str(reason),
            "classification_policy": "validity",
        },
    )


def _resolve_field(document: Mapping[str, Any], field: str) -> float | None:
    parts = field.split(".")
    if parts[0] == "cost":
        current: Any = document.get("cost", {})
        for part in parts[1:]:
            if not isinstance(current, Mapping):
                return None
            current = current.get(part)
        return _finite_float_or_none(current)
    if parts[0] == "metric" and len(parts) >= 2:
        metric_name = parts[1]
        metric = next(
            (
                item
                for item in document.get("metrics", [])
                if item.get("name") == metric_name and item.get("status") == "computed"
            ),
            None,
        )
        if metric is None:
            return None
        current = metric.get("value")
        for part in parts[2:]:
            if part == "value":
                continue
            if not isinstance(current, Mapping):
                return None
            current = current.get(part)
        return _finite_float_or_none(current)
    raise ClassificationPolicyError(
        "field must start with 'cost.' or 'metric.<metric_name>'.",
    )


def _compare(value: float, threshold: float, operator: str) -> bool:
    if operator == "le":
        return value <= threshold
    if operator == "lt":
        return value < threshold
    if operator == "ge":
        return value >= threshold
    if operator == "gt":
        return value > threshold
    if operator == "eq":
        return math.isclose(value, threshold)
    raise ClassificationPolicyError(f"Unsupported operator: {operator!r}")


def _finite_float_or_none(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _classification_id(base_id: str, candidate_id: str | None) -> str:
    return f"{base_id}-{candidate_id}" if candidate_id else base_id


def _threshold_token(value: float) -> str:
    return str(float(value)).replace("-", "m").replace(".", "p")


__all__ = [
    "ClassificationPolicyError",
    "ThresholdRule",
    "classify_cost_eligibility",
    "classify_invalid",
    "classify_threshold",
    "classify_threshold_value",
]

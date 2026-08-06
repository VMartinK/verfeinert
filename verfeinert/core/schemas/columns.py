"""Column names and schema labels shared by future framework modules."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from verfeinert.core.validation import CoreValidationError


RUN_CONFIG_SCHEMA_VERSION = "verfeinert.run_config.v1"
RUN_METADATA_SCHEMA_VERSION = "verfeinert.run_metadata.v1"
INPUT_HASH_SCHEMA_VERSION = "verfeinert.input_hashes.v1"

RUN_ID_COLUMN = "run_id"
CANDIDATE_ID_COLUMN = "candidate_id"
PARENT_CANDIDATE_ID_COLUMN = "parent_candidate_id"
GENERATION_COLUMN = "generation"
OPERATION_COUNT_COLUMN = "operation_count"
STRUCTURAL_COST_COLUMN = "structural_cost"
METRIC_NAME_COLUMN = "metric_name"
METRIC_VALUE_COLUMN = "metric_value"
METRIC_STATUS_COLUMN = "metric_status"
THRESHOLD_COLUMN = "threshold"
PARETO_STATUS_COLUMN = "pareto_status"

CANDIDATE_TABLE_COLUMNS = (
    RUN_ID_COLUMN,
    CANDIDATE_ID_COLUMN,
    PARENT_CANDIDATE_ID_COLUMN,
    GENERATION_COLUMN,
    OPERATION_COUNT_COLUMN,
)

METRIC_TABLE_COLUMNS = (
    RUN_ID_COLUMN,
    CANDIDATE_ID_COLUMN,
    METRIC_NAME_COLUMN,
    METRIC_VALUE_COLUMN,
    METRIC_STATUS_COLUMN,
)

COST_TABLE_COLUMNS = (
    RUN_ID_COLUMN,
    CANDIDATE_ID_COLUMN,
    STRUCTURAL_COST_COLUMN,
)

PARETO_TABLE_COLUMNS = (
    RUN_ID_COLUMN,
    CANDIDATE_ID_COLUMN,
    THRESHOLD_COLUMN,
    PARETO_STATUS_COLUMN,
)


def threshold_label(threshold: int | float | str) -> str:
    """Return a filesystem- and column-safe label for a positive threshold."""
    try:
        number = Decimal(str(threshold))
    except (InvalidOperation, ValueError) as exc:
        raise CoreValidationError("threshold must be a positive finite number.") from exc
    if not number.is_finite() or number <= 0:
        raise CoreValidationError("threshold must be a positive finite number.")

    raw = str(threshold).strip().lower()
    if "e" in raw:
        raw = format(number.normalize(), "f")
    return raw.replace("-", "m").replace(".", "p")


__all__ = [
    "CANDIDATE_ID_COLUMN",
    "CANDIDATE_TABLE_COLUMNS",
    "COST_TABLE_COLUMNS",
    "GENERATION_COLUMN",
    "INPUT_HASH_SCHEMA_VERSION",
    "METRIC_TABLE_COLUMNS",
    "PARETO_TABLE_COLUMNS",
    "PARENT_CANDIDATE_ID_COLUMN",
    "RUN_CONFIG_SCHEMA_VERSION",
    "RUN_ID_COLUMN",
    "RUN_METADATA_SCHEMA_VERSION",
    "STRUCTURAL_COST_COLUMN",
    "THRESHOLD_COLUMN",
    "threshold_label",
]

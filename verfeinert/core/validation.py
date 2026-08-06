"""Small validation helpers shared across Verfeinert core."""

from __future__ import annotations

import math
import re
from typing import Iterable, TypeVar


class CoreValidationError(ValueError):
    """Raised when a core configuration or schema value is invalid."""


T = TypeVar("T")

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def require_mapping(value: object, field_name: str) -> dict[str, object]:
    """Return a plain dict when ``value`` is a mapping-like configuration."""
    if not isinstance(value, dict):
        raise CoreValidationError(f"{field_name} must be a mapping.")
    return dict(value)


def require_non_empty_text(value: object, field_name: str) -> str:
    """Validate a non-empty string field."""
    if not isinstance(value, str):
        raise CoreValidationError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise CoreValidationError(f"{field_name} must not be empty.")
    return normalized


def require_identifier(value: object, field_name: str) -> str:
    """Validate a portable identifier for records, runs, and candidates."""
    identifier = require_non_empty_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise CoreValidationError(
            f"{field_name} must contain only letters, numbers, '_', '-', or '.'."
        )
    return identifier


def require_bool(value: object, field_name: str) -> bool:
    """Validate a boolean without accepting integers as bool-like values."""
    if type(value) is not bool:
        raise CoreValidationError(f"{field_name} must be a boolean.")
    return value


def require_positive_int(value: object, field_name: str) -> int:
    """Validate a positive integer without accepting booleans."""
    if type(value) is not int:
        raise CoreValidationError(f"{field_name} must be an integer.")
    if value < 1:
        raise CoreValidationError(f"{field_name} must be greater than or equal to 1.")
    return value


def require_non_negative_int_or_none(value: object, field_name: str) -> int | None:
    """Validate an optional non-negative integer field."""
    if value is None:
        return None
    if type(value) is not int:
        raise CoreValidationError(f"{field_name} must be an integer or null.")
    if value < 0:
        raise CoreValidationError(f"{field_name} must be greater than or equal to 0.")
    return value


def require_supported_value(value: object, field_name: str, allowed: Iterable[T]) -> T:
    """Validate that ``value`` is one of the explicitly supported values."""
    allowed_tuple = tuple(allowed)
    if value not in allowed_tuple:
        allowed_text = ", ".join(repr(item) for item in allowed_tuple)
        raise CoreValidationError(f"{field_name} must be one of: {allowed_text}.")
    return value  # type: ignore[return-value]


def require_positive_finite_float(value: object, field_name: str) -> float:
    """Validate a positive finite numeric threshold."""
    if type(value) not in {int, float}:
        raise CoreValidationError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise CoreValidationError(f"{field_name} must be positive and finite.")
    return number


__all__ = [
    "CoreValidationError",
    "require_bool",
    "require_identifier",
    "require_mapping",
    "require_non_empty_text",
    "require_non_negative_int_or_none",
    "require_positive_finite_float",
    "require_positive_int",
    "require_supported_value",
]

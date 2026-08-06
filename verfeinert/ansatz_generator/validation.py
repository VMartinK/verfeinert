"""Validation result records for ansatz generation."""

from __future__ import annotations

from dataclasses import dataclass

from verfeinert.core.validation import CoreValidationError


class GeneratorValidationError(ValueError):
    """Raised when a generator-specific record is invalid."""


@dataclass(frozen=True)
class ValidationResult:
    """Small validation outcome used by generator APIs."""

    is_valid: bool
    messages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.is_valid) is not bool:
            raise GeneratorValidationError("is_valid must be a boolean.")
        object.__setattr__(self, "messages", tuple(str(item) for item in self.messages))


__all__ = [
    "CoreValidationError",
    "GeneratorValidationError",
    "ValidationResult",
]

"""External input/output helpers for caller-owned experiment roots."""

from .paths import PathValidationError, ensure_output_root, validate_separate_roots
from .serialization import (
    SerializationError,
    read_json,
    read_yaml,
    to_json_safe,
    write_json,
    write_yaml,
)

__all__ = [
    "PathValidationError",
    "SerializationError",
    "ensure_output_root",
    "read_json",
    "read_yaml",
    "to_json_safe",
    "validate_separate_roots",
    "write_json",
    "write_yaml",
]

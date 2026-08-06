"""JSON/YAML serialization helpers for reproducible records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any

import yaml


class SerializationError(TypeError):
    """Raised when a value cannot be converted to a JSON-safe representation."""


def to_json_safe(value: Any) -> Any:
    """Convert common scientific-record values into JSON-safe Python objects."""
    if value is None or isinstance(value, str):
        return value
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise SerializationError("Floating-point values must be finite.")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return to_json_safe(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): to_json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        return [to_json_safe(item) for item in sorted(value, key=repr)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [to_json_safe(item) for item in value]

    item = getattr(value, "item", None)
    if callable(item):
        return to_json_safe(item())
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return to_json_safe(tolist())

    raise SerializationError(f"Value of type {type(value).__name__!r} is not JSON-safe.")


def read_json(path: str | Path) -> Any:
    """Read JSON from a caller-provided path."""
    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: Any) -> Path:
    """Write a JSON-safe payload with deterministic key ordering."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(to_json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return target


def read_yaml(path: str | Path) -> Any:
    """Read YAML from a caller-provided path using ``yaml.safe_load``."""
    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: str | Path, payload: Any) -> Path:
    """Write a JSON-safe payload as YAML."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(to_json_safe(payload), handle, sort_keys=True)
    return target


__all__ = [
    "SerializationError",
    "read_json",
    "read_yaml",
    "to_json_safe",
    "write_json",
    "write_yaml",
]

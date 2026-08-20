"""Access packaged Verfeinert JSON Schema resources."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
import json
from typing import Any, Iterable

from referencing import Registry, Resource

from .validation import CoreValidationError


SCHEMA_RESOURCE_PACKAGE = "verfeinert.schemas"
SCHEMA_FILENAMES = {
    "analysis_result": "analysis_result.schema.json",
    "candidate": "candidate.schema.json",
    "comparison_result": "comparison_result.schema.json",
    "evolution_run": "evolution_run.schema.json",
    "experiment": "experiment.schema.json",
    "staged_package": "staged_package.schema.json",
}


def schema_names() -> tuple[str, ...]:
    """Return canonical packaged schema names."""
    return tuple(sorted(SCHEMA_FILENAMES))


def schema_filename(schema_name: str) -> str:
    """Return the resource filename for a canonical schema name."""
    key = _normalize_schema_name(schema_name)
    try:
        return SCHEMA_FILENAMES[key]
    except KeyError as exc:
        allowed = ", ".join(schema_names())
        raise CoreValidationError(f"Unknown schema {schema_name!r}; expected one of: {allowed}.") from exc


def read_schema_text(schema_name: str) -> str:
    """Read one packaged schema resource as UTF-8 text."""
    filename = schema_filename(schema_name)
    return resources.files(SCHEMA_RESOURCE_PACKAGE).joinpath(filename).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    """Load one packaged schema resource as JSON."""
    try:
        payload = json.loads(read_schema_text(schema_name))
    except json.JSONDecodeError as exc:
        raise CoreValidationError(f"Packaged schema {schema_name!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CoreValidationError(f"Packaged schema {schema_name!r} must be a JSON object.")
    return payload


def schema_store(schema_names_to_load: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """Return a JSON Schema resolver store for packaged schemas."""
    names = tuple(schema_names_to_load) if schema_names_to_load is not None else schema_names()
    loaded = {name: load_schema(name) for name in names}
    store = {schema["$id"]: schema for schema in loaded.values()}
    store.update({schema_filename(name): schema for name, schema in loaded.items()})
    return store


def schema_registry(schema_names_to_load: Iterable[str] | None = None) -> Registry:
    """Return a referencing registry for packaged JSON Schemas."""
    store = schema_store(schema_names_to_load)
    return Registry().with_resources(
        (uri, Resource.from_contents(schema))
        for uri, schema in store.items()
    )


def _normalize_schema_name(schema_name: str) -> str:
    value = str(schema_name).strip()
    if value.endswith(".schema.json"):
        value = value.removesuffix(".schema.json")
    return value


__all__ = [
    "SCHEMA_FILENAMES",
    "SCHEMA_RESOURCE_PACKAGE",
    "load_schema",
    "read_schema_text",
    "schema_registry",
    "schema_filename",
    "schema_names",
    "schema_store",
]

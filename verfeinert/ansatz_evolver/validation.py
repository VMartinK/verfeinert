"""Schema-backed validation for JSON-first evolver documents."""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any, Mapping

from jsonschema import Draft202012Validator, ValidationError

from verfeinert.core.schema_resources import load_schema as load_packaged_schema
from verfeinert.core.schema_resources import schema_registry as packaged_schema_registry


class EvolverValidationError(ValueError):
    """Raised when an evolver document fails canonical validation."""


SCHEMA_NAMES = ("candidate", "staged_package", "analysis_result", "evolution_run")


def validate_candidate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical Candidate document."""
    return _validate("candidate", document)


def validate_staged_package_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical StagedPackage document."""
    return _validate("staged_package", document)


def validate_analysis_result_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical AnalysisResult document."""
    return _validate("analysis_result", document)


def validate_evolution_run_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical EvolutionRun document."""
    return _validate("evolution_run", document)


def validate_input_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a supported evolver input document by schema_version."""
    if not isinstance(document, Mapping):
        raise EvolverValidationError("Evolver input must be a mapping.")
    schema_version = document.get("schema_version")
    if schema_version == "verfeinert.candidate.v1":
        return validate_candidate_document(document)
    if schema_version == "verfeinert.staged_package.v1":
        return validate_staged_package_document(document)
    if schema_version == "verfeinert.analysis_result.v1":
        return validate_analysis_result_document(document)
    if schema_version == "verfeinert.evolution_run.v1":
        return validate_evolution_run_document(document)
    raise EvolverValidationError(f"Unsupported evolver schema_version: {schema_version!r}.")


def _validate(schema_name: str, document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise EvolverValidationError(f"{schema_name} document must be a mapping.")
    payload = json.loads(json.dumps(document))
    try:
        _validator(schema_name).validate(payload)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        location = path or "<root>"
        raise EvolverValidationError(
            f"{schema_name} document failed schema validation at {location}: {exc.message}",
        ) from exc
    return payload


@lru_cache(maxsize=None)
def _load_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in SCHEMA_NAMES:
        raise EvolverValidationError(f"Unknown evolver schema: {schema_name!r}.")
    return load_packaged_schema(schema_name)


@lru_cache(maxsize=1)
def _schema_registry():
    return packaged_schema_registry(SCHEMA_NAMES)


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    schema = _load_schema(schema_name)
    return Draft202012Validator(schema, registry=_schema_registry())


__all__ = [
    "EvolverValidationError",
    "SCHEMA_NAMES",
    "validate_analysis_result_document",
    "validate_candidate_document",
    "validate_evolution_run_document",
    "validate_input_document",
    "validate_staged_package_document",
]

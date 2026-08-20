"""Schema-backed validation for analyzer foundation documents."""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any, Mapping

from jsonschema import Draft202012Validator, ValidationError

from verfeinert.core.schema_resources import load_schema as load_packaged_schema
from verfeinert.core.schema_resources import schema_registry as packaged_schema_registry


class AnalyzerValidationError(ValueError):
    """Raised when canonical analyzer input or output validation fails."""


SCHEMA_NAMES = ("candidate", "staged_package", "analysis_result")


def validate_candidate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical Candidate document."""
    return _validate("candidate", document)


def validate_staged_package_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical StagedPackage document."""
    return _validate("staged_package", document)


def validate_analysis_result_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical AnalysisResult document."""
    return _validate("analysis_result", document)


def validate_analyzer_input_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one analyzer input document by its schema version."""
    if not isinstance(document, Mapping):
        raise AnalyzerValidationError("Analyzer input must be a mapping.")
    schema_version = document.get("schema_version")
    if schema_version == "verfeinert.candidate.v1":
        return validate_candidate_document(document)
    if schema_version == "verfeinert.staged_package.v1":
        return validate_staged_package_document(document)
    raise AnalyzerValidationError(
        "Analyzer input must use schema_version "
        "'verfeinert.candidate.v1' or 'verfeinert.staged_package.v1'.",
    )


def _validate(schema_name: str, document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise AnalyzerValidationError(f"{schema_name} document must be a mapping.")
    payload = json.loads(json.dumps(document))
    try:
        _validator(schema_name).validate(payload)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        location = path or "<root>"
        raise AnalyzerValidationError(
            f"{schema_name} document failed schema validation at {location}: "
            f"{exc.message}",
        ) from exc
    return payload


@lru_cache(maxsize=None)
def _load_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in SCHEMA_NAMES:
        raise AnalyzerValidationError(f"Unknown analyzer schema: {schema_name!r}.")
    return load_packaged_schema(schema_name)


@lru_cache(maxsize=1)
def _schema_registry():
    return packaged_schema_registry(SCHEMA_NAMES)


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    schema = _load_schema(schema_name)
    return Draft202012Validator(schema, registry=_schema_registry())


__all__ = [
    "AnalyzerValidationError",
    "SCHEMA_NAMES",
    "validate_analysis_result_document",
    "validate_analyzer_input_document",
    "validate_candidate_document",
    "validate_staged_package_document",
]

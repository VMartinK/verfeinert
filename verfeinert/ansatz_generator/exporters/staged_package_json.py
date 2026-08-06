"""Export generated candidate collections as canonical StagedPackage JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from verfeinert import __version__
from verfeinert.core import current_git_commit, ensure_output_root, hash_file, to_json_safe, write_json
from verfeinert.core.validation import CoreValidationError, require_identifier, require_non_empty_text

from ..validation import GeneratorValidationError
from .candidate_json import (
    CANDIDATE_SCHEMA_VERSION,
    CandidateJsonExportConfig,
    _canonical_candidate_id,
    _package_source_root,
    _read_schema,
    _record_mapping,
    _source_id,
    _utc_timestamp,
    export_candidate_json,
    validate_candidate_json,
)


STAGED_PACKAGE_SCHEMA_VERSION = "verfeinert.staged_package.v1"
DEFAULT_PACKAGE_PRODUCER = "verfeinert.ansatz_generator"


@dataclass(frozen=True)
class StagedPackageJsonExportConfig:
    """Options for exporting a canonical staged candidate package."""

    package_id: str
    output_root: str | Path | None = None
    candidate_export: CandidateJsonExportConfig = field(default_factory=CandidateJsonExportConfig)
    created_at: str | None = None
    producer: str = DEFAULT_PACKAGE_PRODUCER
    software_version: str = __version__
    git_commit: str | None = None
    discover_git_commit: bool = True
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    input_roots: Sequence[str | Path] = ()
    write_individual_candidates: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_id", _require_identifier(self.package_id, "package_id"))
        object.__setattr__(self, "producer", require_non_empty_text(self.producer, "producer"))
        object.__setattr__(self, "software_version", require_non_empty_text(self.software_version, "software_version"))
        object.__setattr__(self, "input_hashes", _hash_mapping(self.input_hashes))
        object.__setattr__(self, "input_roots", tuple(self.input_roots))
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))
        if type(self.write_individual_candidates) is not bool:
            raise GeneratorValidationError("write_individual_candidates must be a boolean.")


@dataclass(frozen=True)
class StagedPackageJsonExportResult:
    """Paths and documents produced by staged-package export."""

    package: dict[str, Any]
    candidates: tuple[dict[str, Any], ...]
    output_root: Path | None = None
    package_root: Path | None = None
    staged_package_path: Path | None = None
    candidate_paths: tuple[Path, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary for examples and tests."""
        return {
            "package": self.package,
            "candidate_count": len(self.candidates),
            "output_root": str(self.output_root) if self.output_root is not None else None,
            "package_root": str(self.package_root) if self.package_root is not None else None,
            "staged_package_path": str(self.staged_package_path) if self.staged_package_path is not None else None,
            "candidate_paths": [str(path) for path in self.candidate_paths],
        }


def export_staged_package_json(
    records: Sequence[Mapping[str, Any] | Any],
    *,
    config: StagedPackageJsonExportConfig,
) -> dict[str, Any]:
    """Return a schema-validated canonical StagedPackage JSON document."""
    sources = _record_sources(records)
    candidate_ids = _candidate_ids(sources, config.candidate_export)
    id_map = _candidate_id_map(sources, candidate_ids)
    candidates = [
        export_candidate_json(
            source,
            config=_candidate_config(config),
            candidate_id=candidate_id,
            id_map=id_map,
        )
        for source, candidate_id in zip(sources, candidate_ids, strict=True)
    ]
    package = _package_document(
        config,
        candidates=candidates,
        artifacts=[],
        created_at=_created_at(config),
    )
    return validate_staged_package_json(package)


def write_staged_package_json(
    records: Sequence[Mapping[str, Any] | Any],
    *,
    config: StagedPackageJsonExportConfig,
) -> StagedPackageJsonExportResult:
    """Write a canonical staged package and optional candidate JSON files."""
    if config.output_root is None:
        raise GeneratorValidationError("output_root is required when writing a staged package.")
    output_root = ensure_output_root(
        config.output_root,
        input_roots=config.input_roots,
        source_root=_package_source_root(),
    )
    package_root = output_root / config.package_id
    package_root.mkdir(parents=True, exist_ok=True)

    base_package = export_staged_package_json(records, config=config)
    candidates = tuple(validate_candidate_json(candidate) for candidate in base_package["candidates"])
    candidate_paths: list[Path] = []
    artifacts: list[dict[str, Any]] = []
    if config.write_individual_candidates:
        candidate_root = package_root / "candidates"
        candidate_root.mkdir(parents=True, exist_ok=True)
        for candidate in candidates:
            path = write_json(candidate_root / f"{candidate['candidate_id']}.json", candidate)
            candidate_paths.append(path)
            artifacts.append(
                {
                    "artifact_id": _require_identifier(f"candidate-{candidate['candidate_id']}", "artifact_id"),
                    "kind": "metadata",
                    "uri": path.relative_to(package_root).as_posix(),
                    "format": "json",
                    "hash": hash_file(path),
                }
            )

    package = _package_document(
        config,
        candidates=list(candidates),
        artifacts=artifacts,
        created_at=base_package["manifest"]["created_at"],
    )
    staged_package = validate_staged_package_json(package)
    staged_package_path = write_json(package_root / "staged_package.json", staged_package)
    return StagedPackageJsonExportResult(
        package=staged_package,
        candidates=candidates,
        output_root=output_root,
        package_root=package_root,
        staged_package_path=staged_package_path,
        candidate_paths=tuple(candidate_paths),
    )


def validate_staged_package_json(package: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a canonical StagedPackage JSON mapping."""
    payload = to_json_safe(dict(package))
    _staged_package_validator().validate(payload)
    return payload


def _record_sources(records: Sequence[Mapping[str, Any] | Any]) -> list[dict[str, Any]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise TypeError("records must be a sequence of candidate records.")
    return [_record_mapping(record) for record in records]


def _candidate_ids(
    sources: Sequence[Mapping[str, Any]],
    candidate_config: CandidateJsonExportConfig,
) -> list[str]:
    candidate_ids = [_canonical_candidate_id(source, candidate_config) for source in sources]
    duplicates = sorted({candidate_id for candidate_id in candidate_ids if candidate_ids.count(candidate_id) > 1})
    if duplicates:
        raise GeneratorValidationError(f"duplicate canonical candidate_id values: {', '.join(duplicates)}")
    return candidate_ids


def _candidate_id_map(
    sources: Sequence[Mapping[str, Any]],
    candidate_ids: Sequence[str],
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for source, candidate_id in zip(sources, candidate_ids, strict=True):
        for key in ("circuit_id", "child_id", "candidate_id", "id"):
            value = source.get(key)
            if value is not None:
                id_map[str(value)] = candidate_id
        lineage = source.get("lineage")
        if isinstance(lineage, Mapping) and lineage.get("circuit_id") is not None:
            id_map[str(lineage["circuit_id"])] = candidate_id
    return id_map


def _candidate_config(config: StagedPackageJsonExportConfig) -> CandidateJsonExportConfig:
    candidate = config.candidate_export
    return replace(
        candidate,
        created_at=candidate.created_at or config.created_at,
        software_version=candidate.software_version or config.software_version,
        git_commit=candidate.git_commit if candidate.git_commit is not None else config.git_commit,
        discover_git_commit=candidate.discover_git_commit and config.discover_git_commit,
        input_hashes=candidate.input_hashes or config.input_hashes,
    )


def _package_document(
    config: StagedPackageJsonExportConfig,
    *,
    candidates: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    git_commit = config.git_commit
    if git_commit is None and config.discover_git_commit:
        git_commit = current_git_commit()
    package = {
        "schema_version": STAGED_PACKAGE_SCHEMA_VERSION,
        "package_id": config.package_id,
        "manifest": {
            "package_kind": "candidate_package",
            "created_at": created_at,
            "producer": config.producer,
            "candidate_count": len(candidates),
            "schema_versions": {
                "candidate": CANDIDATE_SCHEMA_VERSION,
            },
            "execution_flags": {
                "qnodes_executed": False,
                "scientific_metrics_executed": False,
                "generated_callables_imported": False,
            },
        },
        "candidates": [validate_candidate_json(candidate) for candidate in candidates],
        "artifacts": [to_json_safe(dict(artifact)) for artifact in artifacts],
        "provenance": {
            "created_at": created_at,
            "source": config.producer,
            "software_version": config.software_version,
            "git_commit": git_commit,
            "input_hashes": dict(config.input_hashes),
        },
    }
    if config.metadata:
        package["metadata"] = dict(config.metadata)
    return package


def _created_at(config: StagedPackageJsonExportConfig) -> str:
    return config.created_at or config.candidate_export.created_at or _utc_timestamp()


def _staged_package_validator() -> Draft202012Validator:
    schema = _read_schema("staged_package")
    candidate_schema = _read_schema("candidate")
    Draft202012Validator.check_schema(schema)
    resolver = RefResolver.from_schema(
        schema,
        store={
            schema["$id"]: schema,
            candidate_schema["$id"]: candidate_schema,
        },
    )
    return Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())


def _hash_mapping(value: Mapping[str, str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, digest in dict(value).items():
        payload[_require_identifier(str(key), "input_hashes key")] = require_non_empty_text(str(digest), "input_hashes value")
    return payload


def _require_identifier(value: str, field_name: str) -> str:
    try:
        return require_identifier(value, field_name)
    except CoreValidationError as exc:
        raise GeneratorValidationError(str(exc)) from exc


__all__ = [
    "STAGED_PACKAGE_SCHEMA_VERSION",
    "StagedPackageJsonExportConfig",
    "StagedPackageJsonExportResult",
    "export_staged_package_json",
    "validate_staged_package_json",
    "write_staged_package_json",
]

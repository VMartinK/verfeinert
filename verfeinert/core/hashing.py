"""Stable hashing primitives for reproducibility metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from verfeinert.core.io.serialization import to_json_safe
from verfeinert.core.schemas import INPUT_HASH_SCHEMA_VERSION
from verfeinert.core.validation import require_identifier


def stable_hash(value: Any, *, algorithm: str = "sha256") -> str:
    """Hash a JSON-safe representation with deterministic key ordering."""
    encoded = json.dumps(
        to_json_safe(value),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    hasher = hashlib.new(algorithm)
    hasher.update(encoded)
    return hasher.hexdigest()


def hash_file(path: str | Path, *, algorithm: str = "sha256") -> str:
    """Hash one existing file using streamed reads."""
    target = Path(path).expanduser()
    hasher = hashlib.new(algorithm)
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_path(path: str | Path, *, algorithm: str = "sha256") -> str:
    """Hash an existing file or directory tree deterministically."""
    target = Path(path).expanduser()
    if target.is_file():
        return hash_file(target, algorithm=algorithm)
    if target.is_dir():
        file_hashes = {
            str(file.relative_to(target)): hash_file(file, algorithm=algorithm)
            for file in sorted(item for item in target.rglob("*") if item.is_file())
        }
        return stable_hash(
            {
                "schema_version": INPUT_HASH_SCHEMA_VERSION,
                "files": file_hashes,
            },
            algorithm=algorithm,
        )
    raise FileNotFoundError(f"Input path does not exist: {target}")


def hash_inputs(
    inputs: Mapping[str, str | Path],
    *,
    algorithm: str = "sha256",
) -> dict[str, str]:
    """Hash named input files or directories for run provenance."""
    return {
        require_identifier(name, "input name"): hash_path(path, algorithm=algorithm)
        for name, path in sorted(inputs.items(), key=lambda item: item[0])
    }


__all__ = ["hash_file", "hash_inputs", "hash_path", "stable_hash"]

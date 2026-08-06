"""Lightweight shared infrastructure for Verfeinert."""

from .config import ExecutionConfig, PathConfig, RunConfig, load_run_config_yaml
from .execution import (
    Executor,
    MultiprocessingExecutor,
    SequentialExecutor,
    build_executor,
)
from .hashing import hash_file, hash_inputs, hash_path, stable_hash
from .io import (
    PathValidationError,
    SerializationError,
    ensure_output_root,
    read_json,
    read_yaml,
    to_json_safe,
    validate_separate_roots,
    write_json,
    write_yaml,
)
from .metadata import (
    ExecutionFlags,
    RunMetadata,
    collect_run_metadata,
    current_git_commit,
)
from .schema_resources import (
    load_schema,
    read_schema_text,
    schema_filename,
    schema_names,
    schema_store,
)
from .validation import CoreValidationError

__all__ = [
    "CoreValidationError",
    "ExecutionConfig",
    "ExecutionFlags",
    "Executor",
    "MultiprocessingExecutor",
    "PathConfig",
    "PathValidationError",
    "RunConfig",
    "RunMetadata",
    "SequentialExecutor",
    "SerializationError",
    "build_executor",
    "collect_run_metadata",
    "current_git_commit",
    "ensure_output_root",
    "hash_file",
    "hash_inputs",
    "hash_path",
    "load_run_config_yaml",
    "load_schema",
    "read_json",
    "read_schema_text",
    "read_yaml",
    "schema_filename",
    "schema_names",
    "schema_store",
    "stable_hash",
    "to_json_safe",
    "validate_separate_roots",
    "write_json",
    "write_yaml",
]

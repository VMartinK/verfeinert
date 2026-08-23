"""Executor abstractions for Verfeinert scientific workflows."""

from .executors import (
    Executor,
    ExecutionError,
    MultiprocessingExecutor,
    SequentialExecutor,
    build_executor,
)

__all__ = [
    "Executor",
    "ExecutionError",
    "MultiprocessingExecutor",
    "SequentialExecutor",
    "build_executor",
]

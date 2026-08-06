"""Executor abstractions for Verfeinert scientific workflows."""

from .executors import (
    Executor,
    MultiprocessingExecutor,
    SequentialExecutor,
    build_executor,
)

__all__ = [
    "Executor",
    "MultiprocessingExecutor",
    "SequentialExecutor",
    "build_executor",
]

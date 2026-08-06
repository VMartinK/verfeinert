"""Shared execution boundary for deterministic candidate-level work."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import multiprocessing
from typing import Protocol, TypeVar

from verfeinert.core.config import ExecutionConfig
from verfeinert.core.validation import CoreValidationError, require_positive_int


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class Executor(Protocol):
    """Minimal ordered-map protocol used by scientific modules."""

    def map(
        self,
        function: Callable[[InputT], OutputT],
        items: Iterable[InputT],
    ) -> list[OutputT]:
        """Apply ``function`` to ``items`` and return results in input order."""


@dataclass(frozen=True)
class SequentialExecutor:
    """Executor that runs candidate work in the current process."""

    def map(
        self,
        function: Callable[[InputT], OutputT],
        items: Iterable[InputT],
    ) -> list[OutputT]:
        """Apply ``function`` serially and preserve input order."""
        return [function(item) for item in items]


@dataclass(frozen=True)
class MultiprocessingExecutor:
    """Executor that owns multiprocessing pool creation for candidate work."""

    worker_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "worker_count",
            require_positive_int(self.worker_count, "worker_count"),
        )

    def map(
        self,
        function: Callable[[InputT], OutputT],
        items: Iterable[InputT],
    ) -> list[OutputT]:
        """Apply ``function`` in a process pool and preserve input order."""
        item_list = list(items)
        if not item_list:
            return []
        with multiprocessing.Pool(processes=self.worker_count) as pool:
            return list(pool.map(function, item_list))


def build_executor(config: ExecutionConfig) -> Executor:
    """Build the executor selected by a validated execution configuration."""
    if not isinstance(config, ExecutionConfig):
        raise CoreValidationError("config must be an ExecutionConfig.")
    if config.mode == "sequential":
        return SequentialExecutor()
    if config.mode == "multiprocessing":
        return MultiprocessingExecutor(worker_count=config.worker_count)
    raise CoreValidationError(f"Unsupported execution mode: {config.mode!r}.")


__all__ = [
    "Executor",
    "MultiprocessingExecutor",
    "SequentialExecutor",
    "build_executor",
]

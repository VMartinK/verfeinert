"""Shared execution boundary for deterministic candidate-level work."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import multiprocessing
from typing import Any, Protocol, TypeVar

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


class ExecutionError(RuntimeError):
    """Raised when an executor cannot truthfully complete requested work."""

    def __init__(
        self,
        message: str,
        *,
        mode: str,
        reason: str = "execution_failed",
        worker_count: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.mode = mode
        self.reason = reason
        self.worker_count = worker_count
        self.error_type = error_type
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe failure metadata without traceback internals."""
        return {
            "mode": self.mode,
            "reason": self.reason,
            "worker_count": self.worker_count,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


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
        try:
            with multiprocessing.Pool(processes=self.worker_count) as pool:
                return list(pool.map(function, item_list))
        except Exception as exc:
            raise ExecutionError(
                "multiprocessing execution failed without sequential fallback: "
                f"{type(exc).__name__}: {exc}",
                mode="multiprocessing",
                reason="multiprocessing_execution_failed",
                worker_count=self.worker_count,
                error_type=type(exc).__name__,
                error_message=str(exc),
            ) from exc


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
    "ExecutionError",
    "MultiprocessingExecutor",
    "SequentialExecutor",
    "build_executor",
]

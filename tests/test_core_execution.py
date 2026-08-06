"""Tests for Verfeinert core executors."""

from __future__ import annotations

import unittest

from verfeinert.core.config import ExecutionConfig
from verfeinert.core.execution import (
    MultiprocessingExecutor,
    SequentialExecutor,
    build_executor,
)


def _square(value: int) -> int:
    return value * value


class CoreExecutionTests(unittest.TestCase):
    def test_sequential_executor_preserves_order(self) -> None:
        config = ExecutionConfig()
        executor = build_executor(config)

        self.assertIsInstance(executor, SequentialExecutor)
        self.assertEqual(executor.map(_square, [3, 1, 2, 0]), [9, 1, 4, 0])

    def test_multiprocessing_executor_preserves_order(self) -> None:
        config = ExecutionConfig(
            mode="multiprocessing",
            parallelize_candidates=True,
            worker_count=2,
        )
        executor = build_executor(config)

        self.assertIsInstance(executor, MultiprocessingExecutor)
        self.assertEqual(executor.map(_square, [3, 1, 2, 0]), [9, 1, 4, 0])


if __name__ == "__main__":
    unittest.main()

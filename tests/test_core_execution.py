"""Tests for Verfeinert core executors."""

from __future__ import annotations

import os
import unittest

from verfeinert.core.config import ExecutionConfig
from verfeinert.core.execution import (
    ExecutionError,
    MultiprocessingExecutor,
    SequentialExecutor,
    build_executor,
)


def _square(value: int) -> int:
    return value * value


def _pid(_: int) -> int:
    return os.getpid()


def _raise_on_two(value: int) -> int:
    if value == 2:
        raise ValueError("worker boom")
    return value


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

    def test_multiprocessing_executor_uses_child_processes(self) -> None:
        executor = build_executor(
            ExecutionConfig(
                mode="multiprocessing",
                parallelize_candidates=True,
                worker_count=2,
            ),
        )

        worker_pids = executor.map(_pid, [0, 1])

        self.assertTrue(set(worker_pids))
        self.assertNotEqual(set(worker_pids), {os.getpid()})

    def test_multiprocessing_executor_supports_one_worker(self) -> None:
        executor = build_executor(
            ExecutionConfig(
                mode="multiprocessing",
                parallelize_candidates=True,
                worker_count=1,
            ),
        )

        self.assertEqual(executor.map(_square, [4, 5]), [16, 25])

    def test_multiprocessing_worker_failure_is_fail_closed(self) -> None:
        executor = build_executor(
            ExecutionConfig(
                mode="multiprocessing",
                parallelize_candidates=True,
                worker_count=2,
            ),
        )

        with self.assertRaises(ExecutionError) as raised:
            executor.map(_raise_on_two, [1, 2, 3])

        self.assertEqual(raised.exception.reason, "multiprocessing_execution_failed")
        self.assertEqual(raised.exception.error_type, "ValueError")
        self.assertIn("worker boom", raised.exception.error_message or "")

    def test_multiprocessing_unpicklable_callable_is_not_run_sequentially(self) -> None:
        executor = build_executor(
            ExecutionConfig(
                mode="multiprocessing",
                parallelize_candidates=True,
                worker_count=2,
            ),
        )

        def local_square(value: int) -> int:
            return value * value

        with self.assertRaises(ExecutionError) as raised:
            executor.map(local_square, [2])

        self.assertEqual(raised.exception.reason, "multiprocessing_execution_failed")


if __name__ == "__main__":
    unittest.main()

"""Tests for Verfeinert core I/O, hashing, and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
import tempfile
import unittest

from verfeinert.core.config import ExecutionConfig, PathConfig, RunConfig
from verfeinert.core.hashing import hash_inputs, hash_path, stable_hash
from verfeinert.core.io import (
    ensure_output_root,
    read_json,
    read_yaml,
    to_json_safe,
    write_json,
    write_yaml,
)
from verfeinert.core.metadata import ExecutionFlags, collect_run_metadata


class ExampleEnum(Enum):
    OPTION = "option"


@dataclass(frozen=True)
class ExamplePayload:
    path: Path
    day: date
    created_at: datetime
    option: ExampleEnum
    values: set[int]


class CoreIoMetadataTests(unittest.TestCase):
    def test_json_safe_serialization_handles_shared_record_values(self) -> None:
        payload = ExamplePayload(
            path=Path("inputs/candidate.json"),
            day=date(2026, 8, 4),
            created_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
            option=ExampleEnum.OPTION,
            values={3, 1, 2},
        )

        self.assertEqual(
            to_json_safe(payload),
            {
                "path": "inputs/candidate.json",
                "day": "2026-08-04",
                "created_at": "2026-08-04T12:00:00+00:00",
                "option": "option",
                "values": [1, 2, 3],
            },
        )

    def test_json_yaml_roundtrip_and_output_root_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_root = tmp_path / "inputs"
            output_root = tmp_path / "outputs"
            input_root.mkdir()

            created_output_root = ensure_output_root(
                output_root,
                input_roots=[input_root],
            )
            self.assertEqual(created_output_root, output_root.resolve(strict=False))
            self.assertTrue(created_output_root.is_dir())

            json_path = output_root / "record.json"
            yaml_path = output_root / "record.yaml"
            payload = {"b": 2, "a": [1, 3]}
            write_json(json_path, payload)
            write_yaml(yaml_path, payload)

            self.assertEqual(read_json(json_path), payload)
            self.assertEqual(read_yaml(yaml_path), payload)

    def test_stable_hashing_and_input_hashes_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_file = tmp_path / "input.json"
            input_file.write_text('{"candidate": "cx01"}\n', encoding="utf-8")
            first_dir = tmp_path / "first"
            second_dir = tmp_path / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            (first_dir / "same.txt").write_text("same content\n", encoding="utf-8")
            (second_dir / "same.txt").write_text("same content\n", encoding="utf-8")

            self.assertEqual(
                stable_hash({"b": 2, "a": [1, 3]}),
                stable_hash({"a": [1, 3], "b": 2}),
            )
            self.assertEqual(hash_path(first_dir), hash_path(second_dir))
            self.assertEqual(
                hash_inputs({"input": input_file}),
                hash_inputs({"input": input_file}),
            )

    def test_provenance_generation_succeeds_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = RunConfig(
                run_id="metadata-test",
                random_seed=7,
                execution=ExecutionConfig(),
                paths=PathConfig(
                    input_root=tmp_path / "inputs",
                    output_root=tmp_path / "outputs",
                ),
            )

            metadata = collect_run_metadata(
                config,
                git_root=tmp_path / "not-a-repo",
                version="0.test",
                clock=lambda: datetime(2026, 8, 4, 12, 30, tzinfo=timezone.utc),
                execution_flags=ExecutionFlags(),
            )

            record = metadata.to_dict()
            self.assertEqual(record["git_commit"], None)
            self.assertEqual(record["verfeinert_version"], "0.test")
            self.assertEqual(record["execution_mode"], "sequential")
            self.assertEqual(record["worker_count"], 1)
            self.assertEqual(record["input_hashes"], {})
            self.assertFalse(record["execution_flags"]["qnodes_executed"])
            self.assertFalse(record["execution_flags"]["plots_generated"])


if __name__ == "__main__":
    unittest.main()

"""Workflow observability tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from verfeinert.workflow import (
    WorkflowConfig,
    WorkflowConfigError,
    WorkflowEvent,
    WorkflowRunner,
    read_workflow_event_log,
)


CREATED_AT = "2026-08-06T00:00:00Z"


def _workflow_mapping(output_root: Path, *, run_id: str = "observability") -> dict:
    return {
        "run": {
            "run_id": run_id,
            "created_at": CREATED_AT,
            "random_seed": 23,
        },
        "paths": {"output_root": str(output_root)},
        "workflow": {
            "campaign_type": "individual",
            "scientific_execution": ["generate"],
            "postprocessing": [],
        },
        "generation": {
            "family": "sanz19",
            "template_ids": ["A02"],
            "layers": [1],
            "n_qubits": 4,
            "candidate_id_prefix": "observed",
        },
        "analyzer": {
            "selected_metrics": ["structural_cost"],
            "structural_cost": {
                "reference_bounds": {
                    "parameter_count": {"min": 0, "max": 8},
                    "depth": {"min": 0, "max": 20},
                    "two_qubit_operation_count": {"min": 0, "max": 6},
                },
            },
        },
    }


class WorkflowObservabilityTests(unittest.TestCase):
    def test_event_log_records_lifecycle_and_checkpoint_event_order(self) -> None:
        with TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(Path(tmp) / "out")
            mapping["workflow"]["checkpoint"] = {"enabled": True}
            mapping["workflow"]["observability"] = {"event_log": {"enabled": True}}

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run()

            self.assertTrue(result.event_log_path.is_file())
            events = read_workflow_event_log(result.event_log_path)
            self.assertEqual([event["sequence"] for event in events], list(range(len(events))))
            self.assertEqual(
                [event["event_type"] for event in events],
                [
                    "run_started",
                    "stage_started",
                    "stage_completed",
                    "checkpoint_written",
                    "run_completed",
                ],
            )
            self.assertEqual(events[1]["stage"], "generate")
            self.assertEqual(events[-1]["status"], "completed")
            self.assertIn(
                "workflow_event_log",
                {artifact["kind"] for artifact in result.produced_artifacts},
            )

    def test_failure_event_is_persisted(self) -> None:
        with TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(Path(tmp) / "out", run_id="observed-failure")
            mapping["workflow"]["scientific_execution"] = ["analyze"]
            mapping["workflow"]["observability"] = {"event_log": {"enabled": True}}
            config = WorkflowConfig.from_mapping(mapping)

            with self.assertRaises(WorkflowConfigError):
                WorkflowRunner(config).run()

            event_log = Path(config.output_root) / config.run_id / "observability" / "events.jsonl"
            events = read_workflow_event_log(event_log)
            self.assertEqual(events[-1]["event_type"], "run_failed")
            self.assertEqual(events[-1]["metadata"]["error_type"], "WorkflowConfigError")

    def test_event_sink_receives_workflow_events(self) -> None:
        with TemporaryDirectory() as tmp:
            received: list[WorkflowEvent] = []
            mapping = _workflow_mapping(Path(tmp) / "out", run_id="observed-sink")

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run(
                event_sink=received.append,
            )

            self.assertIsNone(result.event_log_path)
            self.assertEqual(received[0].event_type, "run_started")
            self.assertIn("stage_completed", [event.event_type for event in received])
            self.assertEqual(received[-1].event_type, "run_completed")

    def test_observer_raise_policy_fails_truthfully(self) -> None:
        with TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(Path(tmp) / "out", run_id="observer-raise")
            mapping["workflow"]["observability"] = {"event_log": {"enabled": True}}
            config = WorkflowConfig.from_mapping(mapping)

            def sink(event: WorkflowEvent) -> None:
                if event.event_type == "stage_started":
                    raise RuntimeError("observer unavailable")

            with self.assertRaisesRegex(RuntimeError, "observer unavailable"):
                WorkflowRunner(config).run(event_sink=sink)

            event_log = Path(config.output_root) / config.run_id / "observability" / "events.jsonl"
            events = read_workflow_event_log(event_log)
            self.assertEqual(events[-1]["event_type"], "run_failed")
            self.assertEqual(events[-1]["metadata"]["error_type"], "RuntimeError")

    def test_observer_record_warning_policy_does_not_fail_run(self) -> None:
        with TemporaryDirectory() as tmp:
            mapping = _workflow_mapping(Path(tmp) / "out", run_id="observer-warning")
            mapping["workflow"]["observability"] = {
                "event_log": {"enabled": True},
                "observer_error_policy": "record_warning",
            }

            def sink(event: WorkflowEvent) -> None:
                if event.event_type == "run_started":
                    raise RuntimeError("observer unavailable")

            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run(event_sink=sink)

            self.assertIn("workflow observer failed", " ".join(result.warnings))
            events = read_workflow_event_log(result.event_log_path)
            self.assertIn("observer_error", [event["event_type"] for event in events])
            self.assertEqual(events[-1]["event_type"], "run_completed")


if __name__ == "__main__":
    unittest.main()

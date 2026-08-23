"""Structured workflow observability events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from verfeinert.core.io.serialization import to_json_safe

from .config import WorkflowConfigError


WORKFLOW_EVENT_SCHEMA_VERSION = "verfeinert.workflow_event.v1"
SUPPORTED_OBSERVER_ERROR_POLICIES = ("raise", "record_warning")


@dataclass(frozen=True)
class WorkflowEvent:
    """One JSON-safe workflow lifecycle event."""

    sequence: int
    event_type: str
    run_id: str
    stage: str | None = None
    status: str | None = None
    reason: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = WORKFLOW_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKFLOW_EVENT_SCHEMA_VERSION:
            raise WorkflowConfigError(
                f"workflow event schema_version must be {WORKFLOW_EVENT_SCHEMA_VERSION!r}.",
            )
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise WorkflowConfigError("workflow event_type must be a non-empty string.")
        object.__setattr__(self, "event_type", self.event_type.strip())
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise WorkflowConfigError("workflow event run_id must be a non-empty string.")
        object.__setattr__(self, "run_id", self.run_id.strip())
        object.__setattr__(self, "metadata", to_json_safe(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "metadata": dict(self.metadata),
        }
        for key in ("stage", "status", "reason", "message"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return to_json_safe(payload)


class WorkflowEventRecorder:
    """Emit workflow events to a callback and/or deterministic JSONL log."""

    def __init__(
        self,
        *,
        run_id: str,
        event_sink: Callable[[WorkflowEvent], Any] | None = None,
        event_log_path: str | Path | None = None,
        observer_error_policy: str = "raise",
    ) -> None:
        if observer_error_policy not in SUPPORTED_OBSERVER_ERROR_POLICIES:
            raise WorkflowConfigError(
                "observability.observer_error_policy must be raise or record_warning.",
            )
        self.run_id = run_id
        self.event_sink = event_sink
        self.event_log_path = Path(event_log_path).expanduser() if event_log_path is not None else None
        self.observer_error_policy = observer_error_policy
        self._sequence = 0
        self._warnings: list[str] = []
        self._observer_error_recorded = False
        if self.event_log_path is not None:
            self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.event_log_path.write_text("", encoding="utf-8")

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def emit(
        self,
        event_type: str,
        *,
        stage: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            sequence=self._sequence,
            event_type=event_type,
            run_id=self.run_id,
            stage=stage,
            status=status,
            reason=reason,
            message=message,
            metadata=dict(metadata or {}),
        )
        self._sequence += 1
        self._write_event(event)
        self._notify_sink(event)
        return event

    def _write_event(self, event: WorkflowEvent) -> None:
        if self.event_log_path is None:
            return
        with self.event_log_path.open("a", encoding="utf-8") as handle:
            json.dump(event.to_dict(), handle, sort_keys=True)
            handle.write("\n")

    def _notify_sink(self, event: WorkflowEvent) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event)
        except Exception as exc:
            if self.observer_error_policy == "raise":
                raise
            self._record_observer_warning(exc)

    def _record_observer_warning(self, exc: Exception) -> None:
        warning = f"workflow observer failed: {type(exc).__name__}: {exc}"
        self._warnings.append(warning)
        if self._observer_error_recorded:
            return
        self._observer_error_recorded = True
        self.emit(
            "observer_error",
            status="warning",
            reason="observer_error",
            message=warning,
            metadata={"error_type": type(exc).__name__},
        )


def read_workflow_event_log(path: str | Path) -> tuple[dict[str, Any], ...]:
    """Read a JSONL workflow event log."""
    events: list[dict[str, Any]] = []
    for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return tuple(events)


__all__ = [
    "SUPPORTED_OBSERVER_ERROR_POLICIES",
    "WORKFLOW_EVENT_SCHEMA_VERSION",
    "WorkflowEvent",
    "WorkflowEventRecorder",
    "read_workflow_event_log",
]

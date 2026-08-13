"""Workflow-level provenance helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from verfeinert import __version__
from verfeinert.core.metadata import current_git_commit


def workflow_provenance(
    *,
    run_id: str,
    config_snapshot: Mapping[str, Any],
    created_at: str | None = None,
    git_commit: str | None = None,
    execution_flags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe workflow provenance record."""
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return {
        "created_at": timestamp,
        "runner": "verfeinert.workflow",
        "software_version": __version__,
        "git_commit": current_git_commit() if git_commit is None else git_commit,
        "run_id": run_id,
        "config": dict(config_snapshot),
        "execution": {
            "notebooks_executed": False,
            "plots_generated_by_runner": False,
            "campaign_specific_logic_in_framework": False,
            **dict(execution_flags or {}),
        },
    }


__all__ = ["workflow_provenance"]

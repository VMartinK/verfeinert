"""Deterministic workflow report builders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from verfeinert.ansatz_analyzer import AnalysisResultCollection
from verfeinert.ansatz_evolver import read_evolution_run_json
from verfeinert.core.hashing import stable_hash
from verfeinert.core.io import read_json, write_json
from verfeinert.core.io.serialization import to_json_safe

from .config import WorkflowConfig


WORKFLOW_REPORT_SCHEMA_VERSION = "verfeinert.workflow_report.v1"


def build_workflow_report_document(
    *,
    config: WorkflowConfig,
    run_root: Path,
    executed_operations: Sequence[str],
    candidate_ids: Sequence[str],
    analysis_result_ids: Sequence[str],
    survivor_candidate_ids: Sequence[str],
    rejected_candidate_ids: Sequence[str],
    analysis_collection: AnalysisResultCollection | None,
    evolution_source: str | Path | Mapping[str, Any] | None,
    ranking_json_path: Path | None,
    pareto_json_path: Path | None,
    artifact_paths: Mapping[str, Any],
    warnings: Sequence[str],
    final_stopping_reason: str | None,
) -> dict[str, Any]:
    """Build a deterministic factual workflow report document."""
    config_snapshot = config.to_dict()
    evolution = _evolution_summary(evolution_source)
    ranking = _ranking_summary(ranking_json_path)
    pareto = _pareto_summary(pareto_json_path)
    analysis_rows = _analysis_rows(
        analysis_collection,
        selected_metrics=config.analyzer.selected_metrics,
    )
    return to_json_safe(
        {
            "schema_version": WORKFLOW_REPORT_SCHEMA_VERSION,
            "run_id": config.run_id,
            "summary": {
                "campaign_type": config.campaign_type,
                "run_root": str(run_root),
                "completed_operations": list(dict.fromkeys(executed_operations)),
                "candidate_count": len(tuple(candidate_ids)),
                "analysis_result_count": len(tuple(analysis_result_ids)),
                "survivor_count": len(tuple(survivor_candidate_ids)),
                "rejected_count": len(tuple(rejected_candidate_ids)),
                "warning_count": len(tuple(dict.fromkeys(warnings))),
                "final_stopping_reason": final_stopping_reason,
            },
            "config": {
                "hash": stable_hash(config_snapshot),
                "requested_scientific_execution": list(config.scientific_execution),
                "requested_postprocessing": list(config.postprocessing),
            },
            "analysis": {
                "selected_metrics": list(config.analyzer.selected_metrics),
                "rows": analysis_rows,
            },
            "ranking": ranking,
            "pareto": pareto,
            "evolution": evolution,
            "artifacts": dict(artifact_paths),
            "warnings": list(dict.fromkeys(warnings)),
        },
    )


def write_workflow_report_json(document: Mapping[str, Any], output_root: Path) -> Path:
    """Write the machine-readable workflow report."""
    return write_json(output_root / "workflow_report.json", document)


def write_workflow_report_markdown(document: Mapping[str, Any], output_root: Path) -> Path:
    """Write the human-readable workflow report."""
    target = output_root / "workflow_report.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_workflow_report_markdown(document), encoding="utf-8")
    return target


def render_workflow_report_markdown(document: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown report from a report document."""
    summary = dict(document.get("summary", {}))
    config = dict(document.get("config", {}))
    analysis = dict(document.get("analysis", {}))
    ranking = dict(document.get("ranking", {}))
    pareto = dict(document.get("pareto", {}))
    evolution = dict(document.get("evolution", {}))
    artifacts = dict(document.get("artifacts", {}))
    warnings = tuple(document.get("warnings", ()))

    lines = [
        f"# Workflow Report: {document.get('run_id')}",
        "",
        "## Summary",
        f"- Campaign type: {summary.get('campaign_type')}",
        f"- Completed operations: {_join(summary.get('completed_operations', ())) or 'none'}",
        f"- Candidates: {summary.get('candidate_count', 0)}",
        f"- Analysis results: {summary.get('analysis_result_count', 0)}",
        f"- Survivors: {summary.get('survivor_count', 0)}",
        f"- Rejected: {summary.get('rejected_count', 0)}",
        f"- Final stopping reason: {summary.get('final_stopping_reason') or 'none'}",
        f"- Warnings: {summary.get('warning_count', 0)}",
        "",
        "## Configuration",
        f"- Config hash: {config.get('hash')}",
        f"- Scientific execution: {_join(config.get('requested_scientific_execution', ())) or 'none'}",
        f"- Postprocessing: {_join(config.get('requested_postprocessing', ())) or 'none'}",
        "",
        "## Analysis",
        f"- Selected metrics: {_join(analysis.get('selected_metrics', ())) or 'none'}",
        f"- Rows: {len(tuple(analysis.get('rows', ())))}",
    ]
    for row in analysis.get("rows", ()):
        row_map = dict(row)
        lines.append(
            "- "
            f"{row_map.get('candidate_id')}: "
            f"analysis={row_map.get('analysis_result_id')}, "
            f"metrics={_metric_status_summary(row_map.get('metrics', {})) or 'none'}, "
            f"structural_cost={_display(row_map.get('structural_cost'))}"
        )

    lines.extend(
        [
            "",
            "## Ranking",
            f"- Path: {ranking.get('path') or 'none'}",
            f"- Ranked candidates: {ranking.get('ranked_count', 0)}",
            f"- Top ranked candidate: {ranking.get('top_ranked_candidate_id') or 'none'}",
            "",
            "## Pareto",
            f"- Path: {pareto.get('path') or 'none'}",
            f"- Frontier candidates: {pareto.get('frontier_count', 0)}",
            f"- Dominated candidates: {pareto.get('dominated_count', 0)}",
            "",
            "## Evolution",
            f"- Path: {evolution.get('path') or 'none'}",
            f"- Status: {evolution.get('status') or 'none'}",
            f"- Generations: {evolution.get('generation_count', 0)}",
            f"- Latest generation: {_display(evolution.get('latest_generation'))}",
            f"- Final stopping reason: {evolution.get('final_stopping_reason') or 'none'}",
            "",
            "## Artifacts",
        ],
    )
    for key in sorted(artifacts):
        lines.append(f"- {key}: {_display(artifacts[key])}")

    lines.extend(["", "## Warnings"])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _analysis_rows(
    collection: AnalysisResultCollection | None,
    *,
    selected_metrics: Sequence[str],
) -> list[dict[str, Any]]:
    if collection is None:
        return []
    rows: list[dict[str, Any]] = []
    for document in collection.documents:
        metrics = _metrics_by_name(document)
        rows.append(
            {
                "candidate_id": document["candidate_ref"]["candidate_id"],
                "analysis_result_id": document["analysis_result_id"],
                "structural_cost": dict(document.get("cost", {})).get("structural_cost"),
                "metrics": metrics,
                "missing_configured_metrics": [
                    metric for metric in selected_metrics if metric not in metrics
                ],
            },
        )
    return rows


def _metrics_by_name(document: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for metric in document.get("metrics", ()):
        if not isinstance(metric, Mapping):
            continue
        name = str(metric.get("name", "")).strip()
        if not name:
            continue
        metrics[name] = {
            "status": metric.get("status"),
            "value": metric.get("value") if metric.get("status") == "computed" else None,
            "error": metric.get("error"),
        }
    return metrics


def _ranking_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "ranked_count": 0, "top_ranked_candidate_id": None}
    document = read_json(path)
    ranked = [
        dict(item)
        for item in document.get("ranked_candidates", ())
        if dict(item).get("rank") is not None
    ]
    ranked.sort(key=lambda item: int(item["rank"]))
    return {
        "path": str(path),
        "ranked_count": len(ranked),
        "top_ranked_candidate_id": ranked[0]["candidate_id"] if ranked else None,
        "top_rank": ranked[0]["rank"] if ranked else None,
    }


def _pareto_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "frontier_count": 0, "dominated_count": 0}
    document = read_json(path)
    return {
        "path": str(path),
        "frontier_count": len(tuple(document.get("frontier_candidate_ids", ()))),
        "dominated_count": len(tuple(document.get("dominated_candidate_ids", ()))),
        "frontier_candidate_ids": list(document.get("frontier_candidate_ids", ())),
    }


def _evolution_summary(
    evolution_source: str | Path | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if evolution_source is None:
        return {
            "path": None,
            "status": None,
            "generation_count": 0,
            "latest_generation": None,
            "final_stopping_reason": None,
        }
    if isinstance(evolution_source, Mapping):
        document = dict(evolution_source)
        path = None
    else:
        path = str(Path(evolution_source).expanduser())
        document = read_evolution_run_json(evolution_source)
    generations = tuple(document.get("generations", ()))
    latest = dict(generations[-1]) if generations else {}
    decision = dict(dict(document.get("metadata", {})).get("workflow", {})).get("final_stopping_decision")
    return {
        "path": path,
        "status": dict(document.get("run_metadata", {})).get("status"),
        "generation_count": len(generations),
        "latest_generation": latest.get("generation_index"),
        "latest_survivor_count": len(tuple(latest.get("survivor_refs", ()))),
        "latest_archive_count": len(tuple(latest.get("archive_refs", ()))),
        "latest_rejected_count": len(tuple(latest.get("rejected_refs", ()))),
        "final_stopping_reason": (
            decision.get("reason") if isinstance(decision, Mapping) else None
        ),
    }


def _join(values: Any) -> str:
    if isinstance(values, (str, bytes, bytearray)):
        return str(values)
    if not isinstance(values, Sequence):
        return ""
    return ", ".join(str(value) for value in values)


def _metric_status_summary(metrics: Any) -> str:
    if not isinstance(metrics, Mapping):
        return ""
    return ", ".join(
        f"{name}:{dict(record).get('status')}"
        for name, record in sorted(metrics.items())
    )


def _display(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_display(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {_display(value[key])}" for key in sorted(value)) + "}"
    return str(value)


__all__ = [
    "WORKFLOW_REPORT_SCHEMA_VERSION",
    "build_workflow_report_document",
    "render_workflow_report_markdown",
    "write_workflow_report_json",
    "write_workflow_report_markdown",
]

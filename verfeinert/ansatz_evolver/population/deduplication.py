"""Deduplication policies for candidate references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..models import CandidateRef, require_identifier


DedupKey = Literal["candidate_id", "structural_hash", "lineage_hash"]
DedupKeep = Literal["first", "last"]


@dataclass(frozen=True)
class DeduplicationReport:
    """Audit report for population deduplication."""

    key: str
    keep: str
    input_count: int
    kept_count: int
    duplicate_count: int
    kept_candidate_ids: tuple[str, ...]
    removed_candidate_ids: tuple[str, ...]
    missing_key_candidate_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe report data."""
        return {
            "key": self.key,
            "keep": self.keep,
            "input_count": self.input_count,
            "kept_count": self.kept_count,
            "duplicate_count": self.duplicate_count,
            "kept_candidate_ids": list(self.kept_candidate_ids),
            "removed_candidate_ids": list(self.removed_candidate_ids),
            "missing_key_candidate_ids": list(self.missing_key_candidate_ids),
        }


def deduplicate_candidate_refs(
    refs: tuple[CandidateRef, ...] | list[CandidateRef],
    *,
    key: DedupKey = "structural_hash",
    keep: DedupKeep = "first",
) -> tuple[tuple[CandidateRef, ...], DeduplicationReport]:
    """Return ordered refs plus an audit report after deduplication."""
    if key not in {"candidate_id", "structural_hash", "lineage_hash"}:
        raise ValueError("key must be candidate_id, structural_hash, or lineage_hash.")
    if keep not in {"first", "last"}:
        raise ValueError("keep must be first or last.")
    ordered = tuple(refs)
    if any(not isinstance(ref, CandidateRef) for ref in ordered):
        raise ValueError("refs must contain CandidateRef objects.")

    missing = tuple(ref.candidate_id for ref in ordered if getattr(ref, key) is None)
    selected_by_value: dict[str, CandidateRef] = {}
    order_by_value: list[str] = []
    removed: list[str] = []
    sequence = ordered if keep == "first" else tuple(reversed(ordered))
    for ref in sequence:
        value = getattr(ref, key)
        if value is None:
            value = f"missing:{ref.candidate_id}"
        value = require_identifier(str(value), "deduplication key value")
        if value in selected_by_value:
            removed.append(ref.candidate_id)
            continue
        selected_by_value[value] = ref
        order_by_value.append(value)

    kept = tuple(selected_by_value[value] for value in order_by_value)
    if keep == "last":
        kept = tuple(reversed(kept))
    kept_ids = tuple(ref.candidate_id for ref in kept)
    removed_ids = tuple(ref.candidate_id for ref in ordered if ref.candidate_id not in kept_ids)
    report = DeduplicationReport(
        key=key,
        keep=keep,
        input_count=len(ordered),
        kept_count=len(kept),
        duplicate_count=len(ordered) - len(kept),
        kept_candidate_ids=kept_ids,
        removed_candidate_ids=removed_ids,
        missing_key_candidate_ids=missing,
    )
    return kept, report


__all__ = ["DedupKey", "DedupKeep", "DeduplicationReport", "deduplicate_candidate_refs"]

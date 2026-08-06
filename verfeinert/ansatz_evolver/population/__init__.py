"""Population references, snapshots, and deduplication helpers."""

from .deduplication import DeduplicationReport, deduplicate_candidate_refs
from .refs import candidate_ref_from_document
from .snapshots import PopulationSnapshot

__all__ = [
    "DeduplicationReport",
    "PopulationSnapshot",
    "candidate_ref_from_document",
    "deduplicate_candidate_refs",
]

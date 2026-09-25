"""Evidence selection: decides which retrieved chunks may support an answer."""

from src.evidence.selection import (
    Evidence,
    EvidenceSelector,
    EvidenceSet,
    ExcludedEvidence,
)

__all__ = [
    "Evidence",
    "EvidenceSelector",
    "EvidenceSet",
    "ExcludedEvidence",
]

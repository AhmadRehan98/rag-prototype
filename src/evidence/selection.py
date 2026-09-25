"""Deterministic evidence selection.

Trust is decided from document metadata by code, never by the LLM:

1. Relevance: chunks below MIN_EVIDENCE_SIMILARITY are dropped.
2. Status: only statuses in STATUS_AUTHORITY can support an answer. Retired and Unverified documents, and any status we don't recognise, are excluded (fail closed) and reported back so the user can see what was not used.
3. Supersession: if several versions of the same document_id remain, only the newest (by effective date, then version) is used.

Excluded documents are never passed to the LLM, so e.g. instructions embedded in an unverified article cannot reach the model at all.
"""

from dataclasses import dataclass
from typing import Literal

from src.config.settings import settings
from src.retrieval.retriever import RetrievedChunk

Authority = Literal["authoritative", "advisory"]
ExclusionReason = Literal["retired", "unverified", "unrecognized_status", "superseded"]

# Keys are lower-cased document statuses from the corpus metadata.
STATUS_AUTHORITY: dict[str, Authority] = {
    "current": "authoritative",
    "active": "authoritative",
    "open": "authoritative",
    "active advisory": "advisory",  # An advisory memo qualifies a policy but never overrides it.
}

STATUS_EXCLUSION: dict[str, ExclusionReason] = {
    "retired": "retired",
    "unverified": "unverified",
}


@dataclass(frozen=True)
class Evidence:
    """A trusted, relevant chunk that may be shown to the LLM and cited."""

    chunk: RetrievedChunk
    authority: Authority


@dataclass(frozen=True)
class ExcludedEvidence:
    """A relevant chunk that was deliberately not used, and why."""

    chunk: RetrievedChunk
    reason: ExclusionReason


@dataclass(frozen=True)
class EvidenceSet:
    evidence: list[Evidence]
    excluded: list[ExcludedEvidence]

    @property
    def is_sufficient(self) -> bool:
        return bool(self.evidence)


def _version_key(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _recency_key(chunk: RetrievedChunk) -> tuple[str, tuple[int, ...]]:
    return (chunk.effective_date or "", _version_key(chunk.version))


class EvidenceSelector:
    def __init__(self, min_similarity: float | None = None) -> None:
        self.min_similarity = (
            settings.MIN_EVIDENCE_SIMILARITY
            if min_similarity is None
            else min_similarity
        )

    def select(self, chunks: list[RetrievedChunk]) -> EvidenceSet:
        relevant = [
            chunk
            for chunk in chunks
            if chunk.vector_similarity is not None
            and chunk.vector_similarity >= self.min_similarity
        ]

        trusted: list[Evidence] = []
        excluded: list[ExcludedEvidence] = []

        for chunk in relevant:
            status = chunk.status.strip().lower()
            if status in STATUS_AUTHORITY:
                trusted.append(
                    Evidence(chunk=chunk, authority=STATUS_AUTHORITY[status])
                )
            else:
                reason = STATUS_EXCLUSION.get(status, "unrecognized_status")
                excluded.append(ExcludedEvidence(chunk=chunk, reason=reason))

        # Keep only the newest trusted version of each document.
        newest: dict[str, RetrievedChunk] = {}
        for item in trusted:
            current = newest.get(item.chunk.document_id)
            if current is None or _recency_key(item.chunk) > _recency_key(current):
                newest[item.chunk.document_id] = item.chunk

        evidence: list[Evidence] = []
        for item in trusted:
            if newest[item.chunk.document_id] is item.chunk:
                evidence.append(item)
            else:
                excluded.append(ExcludedEvidence(chunk=item.chunk, reason="superseded"))

        # Authoritative sources first, then by relevance. This order becomes the prompt order and the [n] citation numbers.
        evidence.sort(
            key=lambda item: (
                item.authority != "authoritative",
                -(item.chunk.vector_similarity or 0.0),
            )
        )

        return EvidenceSet(evidence=evidence, excluded=excluded)

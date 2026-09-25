"""Shared test helpers. Unit tests need no database and no LLM."""

import pytest

from src.retrieval.retriever import RetrievedChunk


@pytest.fixture
def make_chunk():
    """Factory for RetrievedChunk with sensible defaults."""

    counter = iter(range(1, 10_000))

    def _make(
        document_id: str = "DOC-1",
        *,
        version: str = "1.0",
        status: str = "Current",
        effective_date: str | None = "2026-01-01",
        content: str = "Some content.",
        similarity: float | None = 0.8,
        title: str = "Title",
    ) -> RetrievedChunk:
        chunk_id = next(counter)
        return RetrievedChunk(
            chunk_id=chunk_id,
            document_db_id=chunk_id,
            document_id=document_id,
            document_title=title,
            version=version,
            status=status,
            classification="INTERNAL",
            effective_date=effective_date,
            content=content,
            section_title=None,
            score=0.0,
            vector_similarity=similarity,
        )

    return _make

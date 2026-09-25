"""HybridRetriever: rank fusion and the empty authorized scope."""

from types import SimpleNamespace as NS

import pytest

from src.retrieval.retriever import HybridRetriever, reciprocal_rank_fusion


def chunk(chunk_id, *, with_document=True):
    document = NS(
        document_id=f"DOC-{chunk_id}", title="t", version="1.0", status="Current",
        classification="INTERNAL", effective_date=None,
    )
    return NS(
        id=chunk_id, document_db_id=chunk_id, content="c", section_title=None,
        document=document if with_document else None,
    )


def by_id(results):
    return {item.chunk_id: item for item in results}


def test_vector_similarity_is_one_minus_cosine_distance():
    results = by_id(reciprocal_rank_fusion([(chunk(1), 0.2)], [(chunk(2), 0.5)]))
    assert results[1].vector_similarity == pytest.approx(0.8)
    # A keyword-only match has no similarity, so it can't pass the relevance gate.
    assert results[2].vector_similarity is None
    assert results[2].keyword_score == 0.5


def test_chunk_found_by_both_searches_ranks_first():
    a, b, c = chunk(1), chunk(2), chunk(3)
    results = reciprocal_rank_fusion([(a, 0.1), (b, 0.2)], [(b, 0.9), (c, 0.8)])
    assert [item.chunk_id for item in results] == [2, 1, 3]


def test_chunk_without_a_document_fails_instead_of_inventing_metadata():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([(chunk(1, with_document=False), 0.1)], [])


class Untouchable:
    """Fails the test if retrieval embeds or searches anything."""

    def __getattr__(self, name):
        raise AssertionError(f"{name} called with no authorized documents")


@pytest.mark.asyncio
async def test_no_authorized_documents_means_no_search():
    retriever = HybridRetriever(session=None, embedder=Untouchable())
    retriever.chunk_repo = Untouchable()
    assert await retriever.retrieve(question="q", allowed_document_ids=[]) == []

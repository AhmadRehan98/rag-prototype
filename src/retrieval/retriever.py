from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ChunkModel
from src.database.repositories.chunks import ChunkRepository
from src.retrieval.embeddings import EmbeddingService, embedding_service


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_db_id: int
    document_id: str
    document_title: str
    version: str
    status: str
    classification: str
    effective_date: str | None
    content: str
    section_title: str | None
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    # Raw scores. RRF `score` only reflects rank positions, so the evidence
    # stage uses these to judge absolute relevance.
    vector_similarity: float | None = None
    keyword_score: float | None = None


def reciprocal_rank_fusion(
    vector_results: list[tuple[ChunkModel, float]],
    keyword_results: list[tuple[ChunkModel, float]],
    rrf_k: int = 60,
    vector_weight: float = 1.0,
    keyword_weight: float = 1.0,
) -> list[RetrievedChunk]:
    """Combine vector and keyword search results using Reciprocal Rank Fusion (RRF).

    Formula: RRF_score(chunk) = (w_vec / (k + rank_vec)) + (w_kw / (k + rank_kw))
    """
    scores: dict[int, float] = {}
    chunk_map: dict[int, ChunkModel] = {}
    vector_ranks: dict[int, int] = {}
    keyword_ranks: dict[int, int] = {}
    vector_similarities: dict[int, float] = {}
    keyword_scores: dict[int, float] = {}

    for rank, (chunk, distance) in enumerate(vector_results, start=1):
        chunk_map[chunk.id] = chunk
        vector_ranks[chunk.id] = rank
        vector_similarities[chunk.id] = 1.0 - distance
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (vector_weight / (rrf_k + rank))

    for rank, (chunk, keyword_score) in enumerate(keyword_results, start=1):
        chunk_map[chunk.id] = chunk
        keyword_ranks[chunk.id] = rank
        keyword_scores[chunk.id] = keyword_score
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (keyword_weight / (rrf_k + rank))

    # Sort candidates by combined RRF score descending
    sorted_chunk_ids = sorted(
        scores.keys(),
        key=lambda cid: scores[cid],
        reverse=True,
    )

    retrieved: list[RetrievedChunk] = []
    for cid in sorted_chunk_ids:
        chunk = chunk_map[cid]
        doc = chunk.document
        # The FK makes this impossible; if it ever happens, fail loudly rather than inventing metadata (e.g. a default classification).
        if doc is None:
            raise ValueError(f"Chunk {chunk.id} has no parent document.")
        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_db_id=chunk.document_db_id,
                document_id=doc.document_id,
                document_title=doc.title,
                version=doc.version,
                status=doc.status,
                classification=doc.classification,
                effective_date=(
                    doc.effective_date.isoformat() if doc.effective_date else None
                ),
                content=chunk.content,
                section_title=chunk.section_title,
                score=scores[cid],
                vector_rank=vector_ranks.get(cid),
                keyword_rank=keyword_ranks.get(cid),
                vector_similarity=vector_similarities.get(cid),
                keyword_score=keyword_scores.get(cid),
            )
        )

    return retrieved


class HybridRetriever:
    """Hybrid Retriever combining dense vector similarity and keyword search.

    Operates purely over a provided set of authorized document IDs.
    All identity and authorization resolution occurs before this component is called.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder or embedding_service
        self.chunk_repo = ChunkRepository(session)

    async def retrieve(
        self,
        *,
        question: str,
        allowed_document_ids: Sequence[int],
        top_k: int = 5,
        vector_candidates: int = 15,
        keyword_candidates: int = 15,
        rrf_k: int = 60,
    ) -> list[RetrievedChunk]:
        """Perform hybrid retrieval strictly scoped to the provided allowed_document_ids.

        If allowed_document_ids is empty, returns [] immediately without querying the index.
        """
        # If caller provided no allowed documents, do not touch index or generate embedding
        if not allowed_document_ids:
            return []

        doc_ids_list = list(allowed_document_ids)

        # 1. Dense vector candidate retrieval
        query_vector = self.embedder.embed_text(question)
        vector_results = await self.chunk_repo.vector_search(
            query_vector=query_vector,
            allowed_document_ids=doc_ids_list,
            limit=vector_candidates,
        )

        # 2. Lexical / keyword candidate retrieval
        keyword_results = await self.chunk_repo.keyword_search(
            query_text=question,
            allowed_document_ids=doc_ids_list,
            limit=keyword_candidates,
        )

        # 3. Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion(
            vector_results=vector_results,
            keyword_results=keyword_results,
            rrf_k=rrf_k,
        )

        return fused[:top_k]

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.chunks import ChunkRepository
from src.retrieval.embeddings import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)


class ChunkIndexer:
    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder or embedding_service
        self.chunk_repo = ChunkRepository(session)

    async def index_unindexed_chunks(self, batch_size: int = 32) -> int:
        """Finds any chunks lacking embeddings or tsvectors and indexes them."""
        unindexed = await self.chunk_repo.list_unindexed()
        if not unindexed:
            logger.info("All chunks are already indexed.")
            return 0

        logger.info(
            "Found %d unindexed chunks. Generating embeddings...", len(unindexed)
        )
        indexed_count = 0

        for i in range(0, len(unindexed), batch_size):
            batch = unindexed[i : i + batch_size]
            texts = [c.content for c in batch]
            embeddings = self.embedder.embed_batch(texts)

            for chunk, emb in zip(batch, embeddings):
                await self.chunk_repo.update_index_data(
                    chunk_id=chunk.id,
                    embedding=emb,
                    content_for_fts=chunk.content,
                )
                indexed_count += 1

            await self.session.commit()
            logger.info("Indexed %d/%d chunks.", indexed_count, len(unindexed))

        return indexed_count

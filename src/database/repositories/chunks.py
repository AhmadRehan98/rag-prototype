from collections.abc import Sequence
from typing import Any

from sqlalchemy import Text, cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import ChunkModel, DocumentModel


class ChunkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        chunk_id: int,
    ) -> ChunkModel | None:
        result = await self.session.execute(
            select(ChunkModel)
            .options(selectinload(ChunkModel.document))
            .where(ChunkModel.id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def get_for_document(
        self,
        document_db_id: int,
    ) -> Sequence[ChunkModel]:
        result = await self.session.execute(
            select(ChunkModel)
            .where(ChunkModel.document_db_id == document_db_id)
            .order_by(ChunkModel.chunk_index)
        )
        return result.scalars().all()

    async def list_unindexed(self) -> Sequence[ChunkModel]:
        """Fetch all chunks lacking either an embedding or a search_vector."""
        result = await self.session.execute(
            select(ChunkModel).where(
                (ChunkModel.embedding.is_(None)) | (ChunkModel.search_vector.is_(None))
            )
        )
        return result.scalars().all()

    async def create(
        self,
        *,
        document_db_id: int,
        chunk_index: int,
        content: str,
        section_title: str | None = None,
        embedding: list[float] | None = None,
        metadata_json: dict | None = None,
    ) -> ChunkModel:
        chunk = ChunkModel(
            document_db_id=document_db_id,
            chunk_index=chunk_index,
            content=content,
            section_title=section_title,
            embedding=embedding,
            search_vector=func.to_tsvector("english", content),
            metadata_json=metadata_json or {},
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def create_many(
        self,
        *,
        document_db_id: int,
        chunks: list[dict],
    ) -> list[ChunkModel]:
        models = [
            ChunkModel(
                document_db_id=document_db_id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                section_title=chunk.get("section_title"),
                embedding=chunk.get("embedding"),
                search_vector=func.to_tsvector("english", chunk["content"]),
                metadata_json=chunk.get("metadata_json", {}),
            )
            for chunk in chunks
        ]
        self.session.add_all(models)
        await self.session.flush()
        return models

    async def update_index_data(
        self,
        chunk_id: int,
        embedding: list[float],
        content_for_fts: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"embedding": embedding}
        if content_for_fts is not None:
            values["search_vector"] = func.to_tsvector("english", content_for_fts)
        await self.session.execute(
            update(ChunkModel).where(ChunkModel.id == chunk_id).values(**values)
        )
        await self.session.flush()

    async def vector_search(
        self,
        query_vector: list[float],
        allowed_document_ids: list[int],
        limit: int = 10,
    ) -> list[tuple[ChunkModel, float]]:
        """Dense vector search using pgvector cosine distance.

        Enforces pre-retrieval authorization: only chunks belonging to allowed_document_ids can be matched or scored.
        """
        if not allowed_document_ids:
            return []

        distance = ChunkModel.embedding.cosine_distance(query_vector).label("distance")
        query = (
            select(ChunkModel, distance)
            .options(selectinload(ChunkModel.document))
            .where(
                ChunkModel.document_db_id.in_(allowed_document_ids),
                ChunkModel.embedding.is_not(None),
            )
            .order_by(distance.asc())
            .limit(limit)
        )

        result = await self.session.execute(query)
        # Return pairs of (ChunkModel, cosine_distance)
        return [(row[0], float(row[1])) for row in result.all()]

    async def keyword_search(
        self,
        query_text: str,
        allowed_document_ids: list[int],
        limit: int = 10,
    ) -> list[tuple[ChunkModel, float]]:
        """PostgreSQL Full-Text Search using an OR-ed tsquery and ts_rank_cd.

        plainto_tsquery ANDs every term, so a natural-language question only matches chunks containing all of its words. Its '&' operators are rewritten to '|' so any term can match; ts_rank_cd still ranks chunks matching more terms higher. Casting the text straight to tsquery keeps the already-stemmed lexemes as they are.

        Enforces pre-retrieval authorization: only chunks belonging to allowed_document_ids can be matched or scored.
        """
        if not allowed_document_ids or not query_text.strip():
            return []

        tsquery = cast(
            func.replace(
                cast(func.plainto_tsquery("english", query_text), Text),
                "&",
                "|",
            ),
            TSQUERY,
        )
        effective_tsv = func.coalesce(
            ChunkModel.search_vector,
            func.to_tsvector("english", ChunkModel.content),
        )
        rank = func.ts_rank_cd(effective_tsv, tsquery).label("rank")

        query = (
            select(ChunkModel, rank)
            .options(selectinload(ChunkModel.document))
            .where(
                ChunkModel.document_db_id.in_(allowed_document_ids),
                effective_tsv.op("@@")(tsquery),
            )
            .order_by(rank.desc())
            .limit(limit)
        )

        result = await self.session.execute(query)
        # Return pairs of (ChunkModel, rank)
        return [(row[0], float(row[1])) for row in result.all()]

    async def delete_for_document(
        self,
        document_db_id: int,
    ) -> int:
        result = await self.session.execute(
            delete(ChunkModel).where(
                ChunkModel.document_db_id == document_db_id,
            )
        )
        await self.session.flush()
        return result.rowcount

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    DocumentModel,
    DocumentOverrideGroupModel,
    DocumentOverrideModel,
)


class DocumentRepository:
    """Database operations for documents and their access rules."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(
        self,
        *,
        status: str | None = None,
    ) -> Sequence[DocumentModel]:
        query = (
            select(DocumentModel)
            .options(
                selectinload(DocumentModel.override).selectinload(
                    DocumentOverrideModel.groups
                ),
            )
            .order_by(DocumentModel.document_id)
        )

        if status is not None:
            query = query.where(DocumentModel.status == status)

        result = await self.session.execute(query)

        return result.scalars().all()

    async def create(
        self,
        *,
        document_id: str,
        title: str,
        version: str,
        status: str,
        classification: str,
        effective_date,
        content_hash: str,
        source_path: str | None = None,
        permissions: list[tuple[str, bool]] | None = None,
    ) -> DocumentModel:
        """Create a document with its group permissions: (group, allowed) pairs.

        The override and its groups are built as new objects together with the
        document, so no relationship has to be loaded (lazy loading isn't
        possible with an async session).
        """
        override = None
        if permissions:
            override = DocumentOverrideModel(
                groups=[
                    DocumentOverrideGroupModel(group=group, allowed=allowed)
                    for group, allowed in permissions
                ]
            )

        document = DocumentModel(
            document_id=document_id,
            title=title,
            version=version,
            status=status,
            classification=classification,
            effective_date=effective_date,
            content_hash=content_hash,
            source_path=source_path,
            override=override,
        )

        self.session.add(document)
        await self.session.flush()

        return document

    async def delete_all(self) -> None:
        """Delete every document. The database cascades the delete to their
        overrides, override groups and chunks."""
        await self.session.execute(delete(DocumentModel))

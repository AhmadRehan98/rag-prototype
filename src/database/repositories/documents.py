from collections.abc import Sequence

from sqlalchemy import select
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

    async def get_by_id(
        self,
        document_db_id: int,
    ) -> DocumentModel | None:
        result = await self.session.execute(
            select(DocumentModel)
            .options(
                selectinload(DocumentModel.override).selectinload(
                    DocumentOverrideModel.groups
                ),
            )
            .where(DocumentModel.id == document_db_id)
        )

        return result.scalar_one_or_none()

    async def get_by_document_id(
        self,
        document_id: str,
    ) -> Sequence[DocumentModel]:
        result = await self.session.execute(
            select(DocumentModel)
            .options(
                selectinload(DocumentModel.override).selectinload(
                    DocumentOverrideModel.groups
                ),
            )
            .where(DocumentModel.document_id == document_id)
            .order_by(DocumentModel.effective_date.desc().nullslast())
        )

        return result.scalars().all()

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
    ) -> DocumentModel:
        document = DocumentModel(
            document_id=document_id,
            title=title,
            version=version,
            status=status,
            classification=classification,
            effective_date=effective_date,
            content_hash=content_hash,
            source_path=source_path,
        )

        self.session.add(document)
        await self.session.flush()

        return document

    async def create_override(
        self,
        document: DocumentModel,
    ) -> DocumentOverrideModel:
        if document.override is not None:
            return document.override

        override = DocumentOverrideModel(
            document=document,
        )

        self.session.add(override)
        await self.session.flush()

        return override

    async def set_group_permission(
        self,
        document: DocumentModel,
        group: str,
        allowed: bool,
    ) -> DocumentOverrideGroupModel:
        override = await self.create_override(document)

        existing = next(
            (item for item in override.groups if item.group == group),
            None,
        )

        if existing is not None:
            existing.allowed = allowed
            await self.session.flush()
            return existing

        permission = DocumentOverrideGroupModel(
            override=override,
            group=group,
            allowed=allowed,
        )

        self.session.add(permission)
        await self.session.flush()

        return permission

    async def remove_group_permission(
        self,
        document: DocumentModel,
        group: str,
    ) -> bool:
        if document.override is None:
            return False

        existing = next(
            (item for item in document.override.groups if item.group == group),
            None,
        )

        if existing is None:
            return False

        await self.session.delete(existing)
        await self.session.flush()

        return True

    async def delete(self, document: DocumentModel) -> None:
        await self.session.delete(document)
        await self.session.flush()

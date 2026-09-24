from sqlalchemy.ext.asyncio import AsyncSession

from src.authorization.policy import AuthorizationPolicy
from src.database.models import DocumentModel, UserModel
from src.database.repositories.documents import DocumentRepository
from src.database.repositories.users import UserRepository


class AuthorizationService:
    def __init__(
        self,
        session: AsyncSession,
        policy: AuthorizationPolicy | None = None,
    ) -> None:
        self.policy = policy or AuthorizationPolicy()
        self.user_repo = UserRepository(session)
        self.document_repo = DocumentRepository(session)

    async def get_authorized_document_ids(
        self,
        user: UserModel | str,
    ) -> list[int]:
        user_model = await self._resolve_user(user)
        if user_model is None:
            return []

        documents = await self.document_repo.list_all()
        return [
            document.id
            for document in documents
            if self.policy.evaluate_access(
                user_model,
                document,
            ).is_allowed
        ]

    async def get_authorized_documents(
        self,
        user: UserModel | str,
    ) -> list[DocumentModel]:
        user_model = await self._resolve_user(user)
        if user_model is None:
            return []

        documents = await self.document_repo.list_all()
        return [
            document
            for document in documents
            if self.policy.evaluate_access(
                user_model,
                document,
            ).is_allowed
        ]

    async def _resolve_user(
        self,
        user: UserModel | str,
    ) -> UserModel | None:
        if isinstance(user, UserModel):
            return user
        # Grab user by id if str is supplied
        return await self.user_repo.get_by_user_id(user)

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    UserGroupModel,
    UserModel,
    UserRoleModel,
)


class UserRepository:
    """Database operations for users and their authorization attributes."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> UserModel | None:
        result = await self.session.execute(
            select(UserModel)
            .options(
                selectinload(UserModel.roles),
                selectinload(UserModel.groups),
            )
            .where(UserModel.user_id == user_id)
        )

        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[UserModel]:
        result = await self.session.execute(
            select(UserModel)
            .options(
                selectinload(UserModel.roles),
                selectinload(UserModel.groups),
            )
            .order_by(UserModel.user_id)
        )

        return result.scalars().all()

    async def create(
        self,
        *,
        user_id: str,
        display_name: str,
        department: str,
        roles: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> UserModel:
        user = UserModel(
            user_id=user_id,
            display_name=display_name,
            department=department,
        )

        user.roles = [UserRoleModel(role=role) for role in (roles or [])]

        user.groups = [UserGroupModel(group=group) for group in (groups or [])]

        self.session.add(user)
        await self.session.flush()

        return user

    async def delete_all(self) -> None:
        """Delete every user. The database cascades the delete to their roles and groups."""
        await self.session.execute(delete(UserModel))

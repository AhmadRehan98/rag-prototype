from collections.abc import Sequence

from sqlalchemy import select
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

    async def add_role(
        self,
        user: UserModel,
        role: str,
    ) -> UserRoleModel:
        user_role = UserRoleModel(
            user=user,
            role=role,
        )

        self.session.add(user_role)
        await self.session.flush()

        return user_role

    async def remove_role(
        self,
        user: UserModel,
        role: str,
    ) -> bool:
        result = await self.session.execute(
            select(UserRoleModel).where(
                UserRoleModel.user_id == user.id,
                UserRoleModel.role == role,
            )
        )

        user_role = result.scalar_one_or_none()

        if user_role is None:
            return False

        await self.session.delete(user_role)
        await self.session.flush()

        return True

    async def add_group(
        self,
        user: UserModel,
        group: str,
    ) -> UserGroupModel:
        user_group = UserGroupModel(
            user=user,
            group=group,
        )

        self.session.add(user_group)
        await self.session.flush()

        return user_group

    async def remove_group(
        self,
        user: UserModel,
        group: str,
    ) -> bool:
        result = await self.session.execute(
            select(UserGroupModel).where(
                UserGroupModel.user_id == user.id,
                UserGroupModel.group == group,
            )
        )

        user_group = result.scalar_one_or_none()

        if user_group is None:
            return False

        await self.session.delete(user_group)
        await self.session.flush()

        return True

    async def delete(self, user: UserModel) -> None:
        await self.session.delete(user)
        await self.session.flush()

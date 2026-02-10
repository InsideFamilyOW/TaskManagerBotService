"""Запросы для выдачи доступа баерам к чатам."""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from db.models import Chat, buyer_chat_access
from log import logger


class ChatAccessQueries:
    """Работа с доступами баеров к чатам."""

    @staticmethod
    async def grant_access(
        session: AsyncSession,
        buyer_id: int,
        chat_db_id: int,
        created_by_id: int | None = None,
    ) -> bool:
        """Выдать доступ баеру к чату."""
        try:
            if await ChatAccessQueries.has_access(session, buyer_id, chat_db_id):
                return True

            stmt = buyer_chat_access.insert().values(
                buyer_id=buyer_id,
                chat_id=chat_db_id,
                created_by_id=created_by_id,
            )
            await session.execute(stmt)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при выдаче доступа buyer={buyer_id} chat={chat_db_id}: {e}")
            return False

    @staticmethod
    async def revoke_access(session: AsyncSession, buyer_id: int, chat_db_id: int) -> bool:
        """Забрать доступ баера к чату."""
        try:
            stmt = delete(buyer_chat_access).where(
                buyer_chat_access.c.buyer_id == buyer_id,
                buyer_chat_access.c.chat_id == chat_db_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(getattr(result, "rowcount", 0))
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при отзыве доступа buyer={buyer_id} chat={chat_db_id}: {e}")
            return False

    @staticmethod
    async def has_access(session: AsyncSession, buyer_id: int, chat_db_id: int) -> bool:
        """Проверить доступ."""
        result = await session.execute(
            select(buyer_chat_access.c.buyer_id).where(
                buyer_chat_access.c.buyer_id == buyer_id,
                buyer_chat_access.c.chat_id == chat_db_id,
            )
        )
        return result.first() is not None

    @staticmethod
    async def count_accessible_chats(session: AsyncSession, buyer_id: int) -> int:
        """Количество чатов, доступных баеру."""
        from sqlalchemy import func as sql_func

        result = await session.execute(
            select(sql_func.count(Chat.id))
            .select_from(Chat)
            .join(buyer_chat_access, buyer_chat_access.c.chat_id == Chat.id)
            .where(
                buyer_chat_access.c.buyer_id == buyer_id,
                Chat.bot_status.in_(["member", "administrator"]),
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_accessible_chats(
        session: AsyncSession,
        buyer_id: int,
        page: int = 1,
        per_page: int = 10,
    ) -> List[Chat]:
        """Список чатов, доступных баеру."""
        result = await session.execute(
            select(Chat)
            .join(buyer_chat_access, buyer_chat_access.c.chat_id == Chat.id)
            .where(
                buyer_chat_access.c.buyer_id == buyer_id,
                Chat.bot_status.in_(["member", "administrator"]),
            )
            .order_by(Chat.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all())


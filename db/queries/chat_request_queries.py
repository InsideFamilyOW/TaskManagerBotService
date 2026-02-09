"""Запросы для запросов баера в чат (сообщения с кнопкой 'Выполнено')."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from db.models import ChatRequest
from log import logger


class ChatRequestQueries:
    """Работа с ChatRequest."""

    @staticmethod
    async def create_request(
        session: AsyncSession,
        *,
        chat_db_id: int | None,
        chat_telegram_id: int,
        chat_title: str | None,
        sender_id: int,
        content_type: str,
        content_preview: str | None,
    ) -> ChatRequest:
        request = ChatRequest(
            chat_db_id=chat_db_id,
            chat_telegram_id=chat_telegram_id,
            chat_title=chat_title,
            sender_id=sender_id,
            content_type=content_type,
            content_preview=content_preview,
            is_completed=False,
        )
        session.add(request)
        await session.flush()  # чтобы получить request.id
        return request

    @staticmethod
    async def set_chat_message_id(session: AsyncSession, request_id: int, message_id: int) -> bool:
        try:
            await session.execute(
                update(ChatRequest)
                .where(ChatRequest.id == request_id)
                .values(chat_message_id=message_id)
            )
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при обновлении message_id chat_request={request_id}: {e}")
            return False

    @staticmethod
    async def get_by_id(session: AsyncSession, request_id: int) -> Optional[ChatRequest]:
        result = await session.execute(select(ChatRequest).where(ChatRequest.id == request_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_completed(
        session: AsyncSession,
        request_id: int,
        *,
        completed_by_telegram_id: int,
        completed_by_user_id: int | None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Пометить запрос выполненным (только если еще не выполнен)."""
        try:
            completed_at = completed_at or datetime.now(timezone.utc)
            result = await session.execute(
                update(ChatRequest)
                .where(ChatRequest.id == request_id, ChatRequest.is_completed == False)
                .values(
                    is_completed=True,
                    completed_by_telegram_id=completed_by_telegram_id,
                    completed_by_user_id=completed_by_user_id,
                    completed_at=completed_at,
                )
            )
            await session.commit()
            return bool(getattr(result, "rowcount", 0))
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при завершении chat_request={request_id}: {e}")
            return False

    @staticmethod
    async def count_by_sender(
        session: AsyncSession,
        sender_id: int,
        *,
        start_date=None,
    ) -> tuple[int, int]:
        """(completed, not_completed) для баера."""
        from sqlalchemy import func as sql_func
        completed_query = select(sql_func.count(ChatRequest.id)).where(
            ChatRequest.sender_id == sender_id,
            ChatRequest.is_completed == True,
        )
        total_query = select(sql_func.count(ChatRequest.id)).where(ChatRequest.sender_id == sender_id)
        if start_date is not None:
            completed_query = completed_query.where(ChatRequest.created_at >= start_date)
            total_query = total_query.where(ChatRequest.created_at >= start_date)

        completed_result = await session.execute(completed_query)
        completed = completed_result.scalar() or 0

        total_result = await session.execute(total_query)
        total = total_result.scalar() or 0
        return completed, max(total - completed, 0)

    @staticmethod
    async def count_global(
        session: AsyncSession,
        *,
        start_date=None,
    ) -> tuple[int, int]:
        """(completed, not_completed) по всем запросам."""
        from sqlalchemy import func as sql_func

        total_query = select(sql_func.count(ChatRequest.id))
        completed_query = select(sql_func.count(ChatRequest.id)).where(ChatRequest.is_completed == True)
        if start_date is not None:
            total_query = total_query.where(ChatRequest.created_at >= start_date)
            completed_query = completed_query.where(ChatRequest.created_at >= start_date)

        total = (await session.execute(total_query)).scalar() or 0
        completed = (await session.execute(completed_query)).scalar() or 0
        return completed, max(total - completed, 0)

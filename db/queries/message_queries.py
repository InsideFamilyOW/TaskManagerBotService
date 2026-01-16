"""Запросы для работы с сообщениями"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional

from db.models import Message, MessageType
from log import logger


class MessageQueries:
    """Запросы для работы с сообщениями"""
    
    @staticmethod
    async def create_message(
        session: AsyncSession,
        task_id: int,
        sender_id: int,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        file_id: int = None
    ) -> Message:
        """Создать сообщение"""
        message = Message(
            task_id=task_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            file_id=file_id
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        
        logger.info(f"Создано сообщение от {sender_id} для задачи {task_id}")
        return message
    
    @staticmethod
    async def get_task_messages(
        session: AsyncSession,
        task_id: int,
        limit: int = None
    ) -> List[Message]:
        """Получить сообщения по задаче"""
        query = select(Message).options(
            selectinload(Message.sender)
        ).where(
            Message.task_id == task_id
        ).order_by(Message.created_at)
        
        if limit:
            query = query.limit(limit)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_unread_messages(
        session: AsyncSession,
        task_id: int,
        exclude_user_id: int = None
    ) -> List[Message]:
        """Получить непрочитанные сообщения"""
        query = select(Message).where(
            Message.task_id == task_id,
            Message.is_read == False
        )
        
        if exclude_user_id:
            query = query.where(Message.sender_id != exclude_user_id)
        
        result = await session.execute(query.order_by(Message.created_at))
        return result.scalars().all()
    
    @staticmethod
    async def mark_messages_as_read(
        session: AsyncSession,
        task_id: int,
        user_id: int
    ):
        """Отметить сообщения как прочитанные"""
        from datetime import datetime, timezone
        
        messages = await MessageQueries.get_unread_messages(session, task_id, user_id)
        
        for message in messages:
            message.is_read = True
            message.read_at = datetime.now(timezone.utc)
        
        await session.commit()
        logger.info(f"Отмечено {len(messages)} сообщений как прочитанные для задачи {task_id}")
    
    @staticmethod
    async def get_message_by_id(
        session: AsyncSession,
        message_id: int
    ) -> Optional[Message]:
        """Получить сообщение по ID"""
        result = await session.execute(
            select(Message).options(
                selectinload(Message.sender)
            ).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()


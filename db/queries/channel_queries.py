"""Запросы для работы с каналами"""
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from db.models import Channel
from log import logger


class ChannelQueries:
    """Класс для работы с каналами в БД"""
    
    @staticmethod
    async def add_channel(
        session: AsyncSession,
        channel_id: int,
        created_by_id: int,
        channel_name: str = None
    ) -> Optional[Channel]:
        """Добавить новый канал"""
        try:
            # Проверяем, существует ли уже такой канал
            result = await session.execute(
                select(Channel).where(Channel.channel_id == channel_id)
            )
            existing_channel = result.scalar_one_or_none()
            
            if existing_channel:
                # Если канал существует, но был деактивирован, активируем его
                if not existing_channel.is_active:
                    existing_channel.is_active = True
                    await session.commit()
                    await session.refresh(existing_channel)
                    logger.info(f"Канал {channel_id} реактивирован")
                    return existing_channel
                else:
                    logger.warning(f"Канал {channel_id} уже существует")
                    return None
            
            # Создаем новый канал
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_name,
                created_by_id=created_by_id,
                is_active=True
            )
            
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            logger.info(f"Добавлен новый канал {channel_id}")
            return channel
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении канала: {e}")
            return None
    
    @staticmethod
    async def get_all_active_channels(session: AsyncSession) -> List[Channel]:
        """Получить все активные каналы"""
        try:
            result = await session.execute(
                select(Channel)
                .where(Channel.is_active == True)
                .order_by(Channel.created_at.desc())
            )
            channels = result.scalars().all()
            return list(channels)
        except Exception as e:
            logger.error(f"Ошибка при получении каналов: {e}")
            return []
    
    @staticmethod
    async def get_channel_by_id(session: AsyncSession, channel_id: int) -> Optional[Channel]:
        """Получить канал по его Telegram ID"""
        try:
            result = await session.execute(
                select(Channel).where(Channel.channel_id == channel_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка при получении канала {channel_id}: {e}")
            return None
    
    @staticmethod
    async def delete_channel(session: AsyncSession, channel_id: int) -> bool:
        """Удалить канал (деактивировать)"""
        try:
            result = await session.execute(
                update(Channel)
                .where(Channel.channel_id == channel_id)
                .values(is_active=False)
            )
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"Канал {channel_id} деактивирован")
                return True
            return False
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при удалении канала: {e}")
            return False
    
    @staticmethod
    async def permanently_delete_channel(session: AsyncSession, channel_id: int) -> bool:
        """Полностью удалить канал из БД"""
        try:
            result = await session.execute(
                delete(Channel).where(Channel.channel_id == channel_id)
            )
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"Канал {channel_id} полностью удален из БД")
                return True
            return False
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при полном удалении канала: {e}")
            return False


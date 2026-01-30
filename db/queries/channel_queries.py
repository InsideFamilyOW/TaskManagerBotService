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
        """Добавить новый канал (старый метод для совместимости)"""
        return await ChannelQueries.add_or_update_channel(
            session=session,
            channel_id=channel_id,
            channel_name=channel_name,
            created_by_id=created_by_id
        )
    
    @staticmethod
    async def add_or_update_channel(
        session: AsyncSession,
        channel_id: int,
        channel_name: str = None,
        created_by_id: int = None,
        bot_status: str = None,
        can_post_messages: bool = False,
        can_edit_messages: bool = False,
        can_delete_messages: bool = False,
        can_restrict_members: bool = False,
        can_promote_members: bool = False,
        can_change_info: bool = False,
        can_invite_users: bool = False,
        can_pin_messages: bool = False,
        can_manage_chat: bool = False,
        can_manage_video_chats: bool = False,
    ) -> Optional[Channel]:
        """Добавить или обновить канал"""
        try:
            result = await session.execute(
                select(Channel).where(Channel.channel_id == channel_id)
            )
            existing_channel = result.scalar_one_or_none()
            
            if existing_channel:
                # Обновляем существующий канал
                if channel_name:
                    existing_channel.channel_name = channel_name
                if bot_status:
                    existing_channel.bot_status = bot_status
                if created_by_id:
                    existing_channel.created_by_id = created_by_id
                existing_channel.is_active = True
                existing_channel.can_post_messages = can_post_messages
                existing_channel.can_edit_messages = can_edit_messages
                existing_channel.can_delete_messages = can_delete_messages
                existing_channel.can_restrict_members = can_restrict_members
                existing_channel.can_promote_members = can_promote_members
                existing_channel.can_change_info = can_change_info
                existing_channel.can_invite_users = can_invite_users
                existing_channel.can_pin_messages = can_pin_messages
                existing_channel.can_manage_chat = can_manage_chat
                existing_channel.can_manage_video_chats = can_manage_video_chats
                
                await session.commit()
                await session.refresh(existing_channel)
                logger.info(f"Обновлен канал {channel_id} ({channel_name})")
                return existing_channel
            
            # Создаем новый канал
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_name,
                created_by_id=created_by_id,
                is_active=True,
                bot_status=bot_status or "administrator",
                can_post_messages=can_post_messages,
                can_edit_messages=can_edit_messages,
                can_delete_messages=can_delete_messages,
                can_restrict_members=can_restrict_members,
                can_promote_members=can_promote_members,
                can_change_info=can_change_info,
                can_invite_users=can_invite_users,
                can_pin_messages=can_pin_messages,
                can_manage_chat=can_manage_chat,
                can_manage_video_chats=can_manage_video_chats,
            )
            
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            logger.info(f"Добавлен новый канал {channel_id} ({channel_name})")
            return channel
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении/обновлении канала: {e}")
            return None
    
    @staticmethod
    async def get_all_active_channels(session: AsyncSession) -> List[Channel]:
        """Получить все активные каналы (старый метод для совместимости)"""
        return await ChannelQueries.get_all_channels(session, active_only=True)
    
    @staticmethod
    async def get_all_channels(session: AsyncSession, active_only: bool = True, page: int = 1, per_page: int = 10) -> List[Channel]:
        """Получить все каналы с пагинацией"""
        try:
            query = select(Channel)
            if active_only:
                query = query.where(Channel.is_active == True)
            query = query.order_by(Channel.created_at.desc())
            query = query.offset((page - 1) * per_page).limit(per_page)
            
            result = await session.execute(query)
            channels = result.scalars().all()
            return list(channels)
        except Exception as e:
            logger.error(f"Ошибка при получении каналов: {e}")
            return []
    
    @staticmethod
    async def count_channels(session: AsyncSession, active_only: bool = True) -> int:
        """Подсчитать количество каналов"""
        try:
            query = select(Channel)
            if active_only:
                query = query.where(Channel.is_active == True)
            result = await session.execute(query)
            channels = result.scalars().all()
            return len(list(channels))
        except Exception as e:
            logger.error(f"Ошибка при подсчете каналов: {e}")
            return 0
    
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
    async def get_channel_by_db_id(session: AsyncSession, db_id: int) -> Optional[Channel]:
        """Получить канал по ID в БД"""
        try:
            result = await session.execute(
                select(Channel).where(Channel.id == db_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка при получении канала по БД ID {db_id}: {e}")
            return None
    
    @staticmethod
    async def update_channel_status(
        session: AsyncSession,
        channel_id: int,
        bot_status: str
    ) -> bool:
        """Обновить статус бота в канале"""
        try:
            result = await session.execute(
                update(Channel)
                .where(Channel.channel_id == channel_id)
                .values(bot_status=bot_status)
            )
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"Статус канала {channel_id} обновлен на {bot_status}")
                return True
            return False
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при обновлении статуса канала: {e}")
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


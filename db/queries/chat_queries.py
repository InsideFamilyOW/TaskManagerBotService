"""Запросы для работы с чатами"""
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from db.models import Chat
from log import logger


class ChatQueries:
    """Класс для работы с чатами в БД"""
    
    @staticmethod
    async def add_or_update_chat(
        session: AsyncSession,
        chat_id: int,
        chat_type: str,
        chat_title: str = None,
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
    ) -> Optional[Chat]:
        """Добавить или обновить чат"""
        try:
            # Проверяем, существует ли уже такой чат
            result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            existing_chat = result.scalar_one_or_none()
            
            if existing_chat:
                # Обновляем существующий чат
                existing_chat.chat_type = chat_type
                existing_chat.chat_title = chat_title
                if bot_status:
                    existing_chat.bot_status = bot_status
                existing_chat.can_post_messages = can_post_messages
                existing_chat.can_edit_messages = can_edit_messages
                existing_chat.can_delete_messages = can_delete_messages
                existing_chat.can_restrict_members = can_restrict_members
                existing_chat.can_promote_members = can_promote_members
                existing_chat.can_change_info = can_change_info
                existing_chat.can_invite_users = can_invite_users
                existing_chat.can_pin_messages = can_pin_messages
                existing_chat.can_manage_chat = can_manage_chat
                existing_chat.can_manage_video_chats = can_manage_video_chats
                
                await session.commit()
                await session.refresh(existing_chat)
                logger.info(f"Обновлен чат {chat_id} ({chat_title})")
                return existing_chat
            
            # Создаем новый чат
            chat = Chat(
                chat_id=chat_id,
                chat_type=chat_type,
                chat_title=chat_title,
                bot_status=bot_status or "member",
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
            
            session.add(chat)
            await session.commit()
            await session.refresh(chat)
            logger.info(f"Добавлен новый чат {chat_id} ({chat_title})")
            return chat
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении/обновлении чата: {e}")
            return None
    
    @staticmethod
    async def get_all_chats(session: AsyncSession, page: int = 1, per_page: int = 10) -> List[Chat]:
        """Получить все чаты с пагинацией"""
        try:
            result = await session.execute(
                select(Chat)
                .where(Chat.bot_status.in_(["member", "administrator"]))  # Только активные чаты
                .order_by(Chat.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            chats = result.scalars().all()
            return list(chats)
        except Exception as e:
            logger.error(f"Ошибка при получении чатов: {e}")
            return []
    
    @staticmethod
    async def count_chats(session: AsyncSession) -> int:
        """Подсчитать количество активных чатов"""
        try:
            result = await session.execute(
                select(Chat)
                .where(Chat.bot_status.in_(["member", "administrator"]))
            )
            chats = result.scalars().all()
            return len(list(chats))
        except Exception as e:
            logger.error(f"Ошибка при подсчете чатов: {e}")
            return 0
    
    @staticmethod
    async def get_chat_by_id(session: AsyncSession, chat_id: int) -> Optional[Chat]:
        """Получить чат по его Telegram ID"""
        try:
            result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка при получении чата {chat_id}: {e}")
            return None
    
    @staticmethod
    async def get_chat_by_db_id(session: AsyncSession, db_id: int) -> Optional[Chat]:
        """Получить чат по ID в БД"""
        try:
            result = await session.execute(
                select(Chat).where(Chat.id == db_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка при получении чата по БД ID {db_id}: {e}")
            return None
    
    @staticmethod
    async def delete_chat(session: AsyncSession, chat_id: int) -> bool:
        """Удалить чат из БД"""
        try:
            result = await session.execute(
                delete(Chat).where(Chat.chat_id == chat_id)
            )
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"Чат {chat_id} удален из БД")
                return True
            return False
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при удалении чата: {e}")
            return False
    
    @staticmethod
    async def update_chat_status(
        session: AsyncSession,
        chat_id: int,
        bot_status: str
    ) -> bool:
        """Обновить статус бота в чате"""
        try:
            result = await session.execute(
                update(Chat)
                .where(Chat.chat_id == chat_id)
                .values(bot_status=bot_status)
            )
            await session.commit()
            
            if result.rowcount > 0:
                logger.info(f"Статус чата {chat_id} обновлен на {bot_status}")
                return True
            return False
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при обновлении статуса чата: {e}")
            return False

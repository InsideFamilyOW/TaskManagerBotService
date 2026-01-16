"""Запросы для работы с пользователями"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_
from typing import List, Optional

from db.models import User, UserRole, DirectionType, executor_buyer_assignments
from log import logger


class UserQueries:
    """Запросы для работы с пользователями"""
    
    @staticmethod
    async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int, active_only: bool = True) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        query = select(User).where(and_(User.telegram_id == telegram_id))
        if active_only:
            query = query.where(and_(User.is_active == True))
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(
        session: AsyncSession,
        telegram_id: int,
        role: UserRole = None,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        direction: DirectionType = None
    ) -> User:
        """Создать нового пользователя"""
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            direction=direction,
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        role_text = role.value if role else "без роли"
        logger.info(f"Создан новый пользователь: {telegram_id}, роль: {role_text}")
        return user
    
    @staticmethod
    async def get_all_users(session: AsyncSession, role: UserRole = None, active_only: bool = True, page: int = 1, per_page: int = 10) -> List[User]:
        """Получить всех пользователей с пагинацией"""
        query = select(User)
        if active_only:
            query = query.where(User.is_active == True)
        if role:
            query = query.where(and_(User.role == role))
        query = query.order_by(User.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        return list(result.scalars())

    @staticmethod
    async def get_executors_by_direction(session: AsyncSession, direction: DirectionType, limit: int = None) -> List[User]:
        """Получить исполнителей по направлению (оптимизировано с опциональным лимитом)"""
        query = select(User).where(
            User.role == UserRole.EXECUTOR,
            User.direction == direction,
            User.is_active == True
        ).order_by(User.current_load)
        
        # Добавляем лимит если указан (для быстрой загрузки топ исполнителей)
        if limit:
            query = query.limit(limit)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def update_user_load(session: AsyncSession, user_id: int, increment: int = 1):
        """Обновить загрузку исполнителя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            user.current_load += increment
            user.current_load = max(0, user.current_load)  # Не меньше 0
            await session.commit()
            logger.info(f"Обновлена загрузка пользователя {user_id}: {user.current_load}")
    
    @staticmethod
    async def deactivate_user(session: AsyncSession, user_id: int):
        """Деактивировать пользователя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            user.is_active = False
            await session.commit()
            logger.info(f"Пользователь {user_id} деактивирован")
    
    @staticmethod
    async def update_user_role(session: AsyncSession, user_id: int, new_role: UserRole):
        """Обновить роль пользователя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user and new_role is not None:
            old_role = user.role
            user.role = new_role
            # Если новая роль не исполнитель, удаляем направление
            if new_role != UserRole.EXECUTOR and user.direction is not None:
                old_direction = user.direction
                user.direction = None
                logger.info(f"Направление пользователя {user_id} удалено при смене роли: {old_direction.value}")
            await session.commit()
            old_role_text = old_role.value if old_role else "без роли"
            new_role_text = new_role.value if new_role else "без роли"
            logger.info(f"Роль пользователя {user_id} изменена: {old_role_text} -> {new_role_text}")
        elif user and new_role is None:
            logger.warning(f"Попытка установить роль пользователя {user_id} в None - операция пропущена")
    
    @staticmethod
    async def update_user_direction(session: AsyncSession, user_id: int, new_direction: DirectionType):
        """Обновить направление исполнителя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            user.direction = new_direction
            await session.commit()
            logger.info(f"Направление пользователя {user_id} изменено: {new_direction.value}")
    
    @staticmethod
    async def activate_user(session: AsyncSession, user_id: int):
        """Активировать пользователя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            user.is_active = True
            await session.commit()
            logger.info(f"Пользователь {user_id} активирован")
            return user
        return None
    
    @staticmethod
    async def delete_user(session: AsyncSession, user_id: int):
        """Физически удалить пользователя из базы данных"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            telegram_id = user.telegram_id
            await session.delete(user)
            await session.commit()
            logger.info(f"Пользователь {telegram_id} (ID: {user_id}) удален из базы данных")
            return True
        return False
    
    @staticmethod
    async def update_user_name(session: AsyncSession, user_id: int, first_name: str, last_name: str = None):
        """Обновить имя пользователя"""
        user = await UserQueries.get_user_by_id(session, user_id)
        if user:
            old_first_name = user.first_name
            old_last_name = user.last_name
            user.first_name = first_name
            user.last_name = last_name
            await session.commit()
            logger.info(f"Имя пользователя {user_id} изменено: '{old_first_name} {old_last_name or ''}' -> '{first_name} {last_name or ''}'")
            return user
        return None
    
    # ============ ФУНКЦИИ ДЛЯ РАБОТЫ С НАЗНАЧЕНИЯМИ ИСПОЛНИТЕЛЕЙ И БАЕРОВ ============
    
    @staticmethod
    async def assign_executor_to_buyer(
        session: AsyncSession,
        executor_id: int,
        buyer_id: int,
        created_by_id: int = None
    ) -> bool:
        """Назначить исполнителя баеру"""
        # Проверяем, что пользователи существуют и имеют правильные роли
        executor = await UserQueries.get_user_by_id(session, executor_id)
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not executor or executor.role != UserRole.EXECUTOR:
            logger.warning(f"Попытка назначить неисполнителя {executor_id} баеру")
            return False
        
        if not buyer or buyer.role != UserRole.BUYER:
            logger.warning(f"Попытка назначить исполнителя небаеру {buyer_id}")
            return False
        
        # Проверяем, не назначен ли уже
        if await UserQueries.is_executor_assigned_to_buyer(session, executor_id, buyer_id):
            logger.info(f"Исполнитель {executor_id} уже назначен баеру {buyer_id}")
            return False
        
        # Добавляем назначение
        stmt = executor_buyer_assignments.insert().values(
            executor_id=executor_id,
            buyer_id=buyer_id,
            created_by_id=created_by_id
        )
        await session.execute(stmt)
        await session.commit()
        
        logger.info(f"Исполнитель {executor_id} назначен баеру {buyer_id}")
        return True
    
    @staticmethod
    async def remove_executor_from_buyer(
        session: AsyncSession,
        executor_id: int,
        buyer_id: int
    ) -> bool:
        """Удалить назначение исполнителя баеру"""
        try:
            stmt = delete(executor_buyer_assignments).where(and_([
                executor_buyer_assignments.c.executor_id == executor_id,
                executor_buyer_assignments.c.buyer_id == buyer_id
            ]))
            result = await session.execute(stmt)
            await session.commit()
            
            if hasattr(result, 'rowcount') and result.rowcount > 0:
                logger.info(f"Назначение исполнителя {executor_id} баеру {buyer_id} удалено")
                return True
            else:
                logger.warning(f"Назначение исполнителя {executor_id} баеру {buyer_id} не найдено для удаления")
                return False
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при удалении назначения исполнителя {executor_id} баеру {buyer_id}: {e}")
            return False
    
    @staticmethod
    async def is_executor_assigned_to_buyer(
        session: AsyncSession,
        executor_id: int,
        buyer_id: int
    ) -> bool:
        """Проверить, назначен ли исполнитель баеру"""
        stmt = select(executor_buyer_assignments).where(
            executor_buyer_assignments.c.executor_id == executor_id,
            executor_buyer_assignments.c.buyer_id == buyer_id
        )
        result = await session.execute(stmt)
        return result.first() is not None
    
    @staticmethod
    async def get_buyers_for_executor(
        session: AsyncSession,
        executor_id: int
    ) -> List[User]:
        """Получить всех баеров, назначенных исполнителю"""
        stmt = select(User).join(
            executor_buyer_assignments,
            User.id == executor_buyer_assignments.c.buyer_id
        ).where(
            executor_buyer_assignments.c.executor_id == executor_id,
            User.is_active == True
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_executors_for_buyer(
        session: AsyncSession,
        buyer_id: int,
        direction: DirectionType = None
    ) -> List[User]:
        """Получить всех исполнителей, назначенных баеру"""
        stmt = select(User).join(
            executor_buyer_assignments,
            User.id == executor_buyer_assignments.c.executor_id
        ).where(
            executor_buyer_assignments.c.buyer_id == buyer_id,
            User.is_active == True,
            User.role == UserRole.EXECUTOR
        )
        
        if direction:
            stmt = stmt.where(User.direction == direction)
        
        stmt = stmt.order_by(User.current_load)
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_all_assignments(session: AsyncSession) -> List[dict]:
        """Получить все назначения (для админа)"""
        stmt = select(
            executor_buyer_assignments.c.executor_id,
            executor_buyer_assignments.c.buyer_id,
            executor_buyer_assignments.c.created_at
        )
        result = await session.execute(stmt)
        rows = result.all()
        # Преобразуем Row объекты в словари
        assignments = []
        for row in rows:
            assignments.append({
                'executor_id': row.executor_id,
                'buyer_id': row.buyer_id,
                'created_at': row.created_at
            })
        return assignments
    
    @staticmethod
    async def count_users_by_role(session: AsyncSession, role: UserRole = None, active_only: bool = True) -> int:
        """Быстрый подсчет пользователей по роли"""
        from sqlalchemy import func as sql_func
        query = select(sql_func.count(User.id))
        if active_only:
            query = query.where(User.is_active == True)
        if role:
            query = query.where(User.role == role)
        result = await session.execute(query)
        return result.scalar() or 0

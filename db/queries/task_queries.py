"""Запросы для работы с задачами"""
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timezone

from db.models import Task, TaskStatus, DirectionType, TaskRejection, executor_buyer_assignments
from db.queries.user_queries import UserQueries
from log import logger


class TaskQueries:
    """Запросы для работы с задачами"""
    
    @staticmethod
    async def create_task(
        session: AsyncSession,
        title: str,
        description: str,
        direction: DirectionType,
        priority: int,
        created_by_id: int,
        executor_id: int = None,
        deadline: datetime = None
    ) -> Task:
        """Создать новую задачу"""
        # Генерируем номер задачи - находим максимальный существующий номер
        # Получаем все номера задач и находим максимальный числовой номер
        all_tasks_result = await session.execute(
            select(Task.task_number)
        )
        all_task_numbers = [row[0] for row in all_tasks_result.fetchall()]
        
        # Находим максимальный числовой номер
        # Поддерживаем оба формата: старый TASK-xxxx и новый T-x
        max_number = 0
        for task_num in all_task_numbers:
            if not task_num:
                continue
            try:
                # Проверяем новый формат T-x
                if task_num.startswith("T-"):
                    num = int(task_num.split('-')[1])
                    max_number = max(max_number, num)
                # Проверяем старый формат TASK-xxxx (для обратной совместимости)
                elif task_num.startswith("TASK-"):
                    num = int(task_num.split('-')[1])
                    max_number = max(max_number, num)
            except (ValueError, IndexError):
                continue
        
        # Следующий номер
        next_number = max_number + 1
        max_retries = 10
        
        # Пытаемся создать задачу с уникальным номером
        for attempt in range(max_retries):
            task_number = f"T-{next_number}"
            
            # Проверяем, что номер не существует
            existing_task = await TaskQueries.get_task_by_number(session, task_number)
            if existing_task:
                next_number += 1
                continue
            
            task = Task(
                task_number=task_number,
                title=title,
                description=description,
                direction=direction,
                priority=priority,
                created_by_id=created_by_id,
                executor_id=executor_id,
                deadline=deadline,
                status=TaskStatus.PENDING
            )
            session.add(task)
            
            try:
                await session.commit()
                await session.refresh(task)
                break  # Успешно создано
            except IntegrityError as e:
                # Если произошла ошибка уникальности (race condition), откатываем и пробуем следующий номер
                await session.rollback()
                if "task_number" in str(e) or "ix_tasks_task_number" in str(e):
                    next_number += 1
                    if attempt == max_retries - 1:
                        logger.error(f"Не удалось создать задачу после {max_retries} попыток из-за конфликтов номеров")
                        raise ValueError("Не удалось сгенерировать уникальный номер задачи после нескольких попыток")
                    continue
                else:
                    # Другая ошибка целостности - пробрасываем дальше
                    raise
        else:
            # Если цикл завершился без break
            raise ValueError("Не удалось сгенерировать уникальный номер задачи")
        
        # Загрузка исполнителя НЕ увеличивается при создании задачи
        # Она увеличится только когда исполнитель примет задачу (PENDING -> IN_PROGRESS)
        
        logger.info(f"Создана задача {task_number} от пользователя {created_by_id}")
        return task
    
    @staticmethod
    async def get_task_by_id(session: AsyncSession, task_id: int) -> Optional[Task]:
        """Получить задачу по ID"""
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.creator))
            .options(selectinload(Task.executor))
            .where(Task.id == task_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_task_by_number(session: AsyncSession, task_number: str) -> Optional[Task]:
        """Получить задачу по номеру"""
        result = await session.execute(
            select(Task)
            .options(selectinload(Task.creator))
            .options(selectinload(Task.executor))
            .where(Task.task_number == task_number)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_tasks_by_creator(
        session: AsyncSession,
        creator_id: int,
        status: TaskStatus = None,
        page: int = None,
        per_page: int = None
    ) -> List[Task]:
        """Получить задачи по создателю с пагинацией"""
        query = select(Task).where(Task.created_by_id == creator_id)
        if status:
            query = query.where(Task.status == status)
        query = query.order_by(Task.created_at.desc())
        
        # Применяем пагинацию на уровне SQL
        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
        
        # Всегда загружаем executor для избежания lazy loading в async контексте
        query = query.options(selectinload(Task.executor))
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_tasks_by_executor(
        session: AsyncSession,
        executor_id: int,
        status: TaskStatus = None,
        page: int = None,
        per_page: int = None
    ) -> List[Task]:
        """Получить задачи по исполнителю с пагинацией"""
        query = select(Task).where(Task.executor_id == executor_id)
        if status:
            query = query.where(Task.status == status)
        query = query.order_by(Task.created_at.desc())
        
        # Применяем пагинацию на уровне SQL
        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
        
        # Всегда загружаем creator для избежания lazy loading в async контексте
        query = query.options(selectinload(Task.creator))
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_available_tasks_for_executor(
        session: AsyncSession,
        executor_id: int,
        status: TaskStatus = None,
        page: int = None,
        per_page: int = None
    ) -> List[Task]:
        """Получить доступные задачи для исполнителя с учетом назначений баеров и пагинацией"""
        from sqlalchemy import or_
        
        # Получаем назначенных баеров для исполнителя
        assigned_buyers_stmt = select(executor_buyer_assignments.c.buyer_id).where(
            executor_buyer_assignments.c.executor_id == executor_id
        )
        assigned_buyers_result = await session.execute(assigned_buyers_stmt)
        assigned_buyer_ids = [row[0] for row in assigned_buyers_result.all()]
        
        # Если есть назначенные баеры, фильтруем задачи
        if assigned_buyer_ids:
            if status == TaskStatus.PENDING or status is None:
                # Для PENDING или всех задач показываем:
                # 1. Задачи, назначенные исполнителю
                # 2. ИЛИ задачи в статусе PENDING от назначенных баеров (еще не назначенные)
                conditions = [
                    Task.executor_id == executor_id
                ]
                if status == TaskStatus.PENDING or status is None:
                    conditions.append(
                        (Task.status == TaskStatus.PENDING) & 
                        (Task.created_by_id.in_(assigned_buyer_ids)) &
                        (Task.executor_id.is_(None))
                    )
                
                query = select(Task).where(or_(*conditions))
                if status == TaskStatus.PENDING:
                    query = query.where(Task.status == TaskStatus.PENDING)
            else:
                # Для других статусов показываем только назначенные задачи
                query = select(Task).where(
                    Task.executor_id == executor_id,
                    Task.status == status
                )
        else:
            # Если нет назначенных баеров, показываем все задачи (обратная совместимость)
            conditions = [Task.executor_id == executor_id]
            if status == TaskStatus.PENDING or status is None:
                conditions.append(
                    (Task.status == TaskStatus.PENDING) & (Task.executor_id.is_(None))
                )
            
            query = select(Task).where(or_(*conditions))
            if status and status != TaskStatus.PENDING:
                # Для конкретного статуса (не PENDING) фильтруем только назначенные
                query = query.where(
                    (Task.executor_id == executor_id) & (Task.status == status)
                )
            elif status == TaskStatus.PENDING:
                query = query.where(Task.status == TaskStatus.PENDING)
        
        query = query.order_by(Task.created_at.desc())
        
        # Применяем пагинацию на уровне SQL
        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
        
        # Всегда загружаем creator для избежания lazy loading в async контексте
        query = query.options(selectinload(Task.creator))
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_tasks_by_direction(
        session: AsyncSession,
        direction: DirectionType,
        status: TaskStatus = None
    ) -> List[Task]:
        """Получить задачи по направлению"""
        query = select(Task).where(Task.direction == direction)
        if status:
            query = query.where(Task.status == status)
        # Всегда загружаем связанные объекты для избежания lazy loading в async контексте
        query = query.options(selectinload(Task.creator), selectinload(Task.executor))
        result = await session.execute(query.order_by(Task.created_at.desc()))
        return result.scalars().all()
    
    @staticmethod
    async def update_task_status(
        session: AsyncSession,
        task_id: int,
        new_status: TaskStatus,
        user_id: int = None,
        comment: str = None
    ) -> Task:
        """Обновить статус задачи"""
        task = await TaskQueries.get_task_by_id(session, task_id)
        if not task:
            return None
        
        old_status = task.status
        task.status = new_status
        
        # Обновляем временные метки
        if new_status == TaskStatus.IN_PROGRESS and not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.APPROVED]:
            task.completed_at = datetime.now(timezone.utc)
        
        # Обновляем загрузку исполнителя при смене статуса
        if task.executor_id:
            # Увеличиваем загрузку при принятии задачи (PENDING -> IN_PROGRESS)
            if old_status == TaskStatus.PENDING and new_status == TaskStatus.IN_PROGRESS:
                await UserQueries.update_user_load(session, task.executor_id, 1)
            # Уменьшаем загрузку при завершении/одобрении задачи (IN_PROGRESS -> COMPLETED/APPROVED)
            elif old_status == TaskStatus.IN_PROGRESS and new_status in [TaskStatus.COMPLETED, TaskStatus.APPROVED]:
                await UserQueries.update_user_load(session, task.executor_id, -1)
        
        # Записываем лог изменения
        from db.models import TaskLog
        log = TaskLog(
            task_id=task_id,
            user_id=user_id,
            action="status_change",
            old_status=old_status,
            new_status=new_status,
            details={"comment": comment} if comment else None
        )
        session.add(log)
        
        await session.commit()
        await session.refresh(task)
        
        logger.info(f"Задача {task.task_number}: статус {old_status.value} -> {new_status.value}")
        return task
    
    @staticmethod
    async def assign_executor(session: AsyncSession, task_id: int, executor_id: int) -> Task:
        """Назначить исполнителя на задачу"""
        task = await TaskQueries.get_task_by_id(session, task_id)
        if not task:
            return None
        
        old_executor_id = task.executor_id
        task.executor_id = executor_id
        
        # Обновляем загрузку исполнителей
        if old_executor_id:
            await UserQueries.update_user_load(session, old_executor_id, -1)
        if executor_id:
            await UserQueries.update_user_load(session, executor_id, 1)
        
        await session.commit()
        await session.refresh(task)
        
        logger.info(f"Задача {task.task_number}: назначен исполнитель {executor_id}")
        return task
    
    @staticmethod
    async def update_task_rating(session: AsyncSession, task_id: int, rating: int):
        """Обновить оценку задачи"""
        task = await TaskQueries.get_task_by_id(session, task_id)
        if task:
            task.rating = rating
            await session.commit()
            logger.info(f"Задача {task.task_number}: оценка {rating}/5")
    
    @staticmethod
    async def cancel_task(session: AsyncSession, task_id: int, user_id: int):
        """Отменить и полностью удалить задачу со всей информацией"""
        task = await TaskQueries.get_task_by_id(session, task_id)
        if not task:
            return None
        
        task_number = task.task_number
        
        # Если задача была в работе, уменьшаем загрузку исполнителя
        if task.status == TaskStatus.IN_PROGRESS and task.executor_id:
            await UserQueries.update_user_load(session, task.executor_id, -1)
        
        # Используем SQL DELETE для удаления задачи, чтобы база данных
        # обработала CASCADE удаление связанных записей (messages, files, logs и т.д.)
        # Это избегает проблемы с SQLAlchemy, который пытается nullify foreign keys
        await session.execute(
            delete(Task).where(Task.id == task_id)
        )
        await session.commit()
        
        logger.info(f"Задача {task_number} полностью удалена пользователем {user_id}")
        return None

    @staticmethod
    async def has_executor_rejected(session: AsyncSession, task_id: int, executor_id: int) -> bool:
        """Проверить, отказывался ли уже этот исполнитель от задачи"""
        result = await session.execute(
            select(TaskRejection).where(
                TaskRejection.task_id == task_id,
                TaskRejection.executor_id == executor_id,
            )
        )
        return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def count_tasks_by_creator(
        session: AsyncSession,
        creator_id: int,
        status: TaskStatus = None
    ) -> int:
        """Быстрый подсчет задач по создателю без загрузки данных"""
        query = select(func.count(Task.id)).where(Task.created_by_id == creator_id)
        if status:
            query = query.where(Task.status == status)
        result = await session.execute(query)
        return result.scalar() or 0
    
    @staticmethod
    async def count_tasks_by_executor(
        session: AsyncSession,
        executor_id: int,
        status: TaskStatus = None
    ) -> int:
        """Быстрый подсчет задач по исполнителю без загрузки данных"""
        query = select(func.count(Task.id)).where(Task.executor_id == executor_id)
        if status:
            query = query.where(Task.status == status)
        result = await session.execute(query)
        return result.scalar() or 0
    
    @staticmethod
    async def count_available_tasks_for_executor(
        session: AsyncSession,
        executor_id: int,
        status: TaskStatus = None
    ) -> int:
        """Быстрый подсчет доступных задач для исполнителя"""
        from sqlalchemy import or_
        
        # Получаем назначенных баеров для исполнителя
        assigned_buyers_stmt = select(executor_buyer_assignments.c.buyer_id).where(
            executor_buyer_assignments.c.executor_id == executor_id
        )
        assigned_buyers_result = await session.execute(assigned_buyers_stmt)
        assigned_buyer_ids = [row[0] for row in assigned_buyers_result.all()]
        
        # Строим запрос для подсчета
        if assigned_buyer_ids:
            if status == TaskStatus.PENDING or status is None:
                conditions = [Task.executor_id == executor_id]
                if status == TaskStatus.PENDING or status is None:
                    conditions.append(
                        (Task.status == TaskStatus.PENDING) & 
                        (Task.created_by_id.in_(assigned_buyer_ids)) &
                        (Task.executor_id.is_(None))
                    )
                query = select(func.count(Task.id)).where(or_(*conditions))
                if status == TaskStatus.PENDING:
                    query = query.where(Task.status == TaskStatus.PENDING)
            else:
                query = select(func.count(Task.id)).where(
                    Task.executor_id == executor_id,
                    Task.status == status
                )
        else:
            conditions = [Task.executor_id == executor_id]
            if status == TaskStatus.PENDING or status is None:
                conditions.append(
                    (Task.status == TaskStatus.PENDING) & (Task.executor_id.is_(None))
                )
            query = select(func.count(Task.id)).where(or_(*conditions))
            if status and status != TaskStatus.PENDING:
                query = query.where(
                    (Task.executor_id == executor_id) & (Task.status == status)
                )
            elif status == TaskStatus.PENDING:
                query = query.where(Task.status == TaskStatus.PENDING)
        
        result = await session.execute(query)
        return result.scalar() or 0


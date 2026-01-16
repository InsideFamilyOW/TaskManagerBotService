"""Запросы для работы с логами"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone

from db.models import ActionLog, TaskLog
from log import logger


class LogQueries:
    """Запросы для работы с логами"""
    
    @staticmethod
    async def create_action_log(
        session: AsyncSession,
        user_id: int,
        action_type: str,
        entity_type: str,
        entity_id: int = None,
        details: dict = None
    ):
        """Создать лог действия"""
        log = ActionLog(
            user_id=user_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )
        session.add(log)
        await session.commit()
        
        logger.info(f"Лог: пользователь {user_id} выполнил {action_type} на {entity_type}")
    
    @staticmethod
    async def get_user_actions(
        session: AsyncSession,
        user_id: int,
        limit: int = 50
    ) -> List[ActionLog]:
        """Получить действия пользователя"""
        result = await session.execute(
            select(ActionLog)
            .where(ActionLog.user_id == user_id)
            .order_by(ActionLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_recent_actions(
        session: AsyncSession,
        hours: int = 24,
        limit: int = 100
    ) -> List[ActionLog]:
        """Получить недавние действия"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        result = await session.execute(
            select(ActionLog)
            .where(ActionLog.created_at >= since)
            .order_by(ActionLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_task_logs(
        session: AsyncSession,
        task_id: int
    ) -> List[TaskLog]:
        """Получить логи задачи"""
        result = await session.execute(
            select(TaskLog)
            .where(TaskLog.task_id == task_id)
            .order_by(TaskLog.created_at)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_actions_by_type(
        session: AsyncSession,
        action_type: str,
        days: int = 7,
        limit: int = 50
    ) -> List[ActionLog]:
        """Получить действия по типу"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await session.execute(
            select(ActionLog)
            .where(
                ActionLog.action_type == action_type,
                ActionLog.created_at >= since
            )
            .order_by(ActionLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_actions_stats(
        session: AsyncSession,
        days: int = 7
    ) -> Dict[str, int]:
        """Получить статистику действий"""
        from sqlalchemy import func
        
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await session.execute(
            select(
                ActionLog.action_type,
                func.count(ActionLog.id).label('count')
            )
            .where(ActionLog.created_at >= since)
            .group_by(ActionLog.action_type)
            .order_by(func.count(ActionLog.id).desc())
        )
        
        stats = {}
        for row in result:
            stats[row.action_type] = row.count
        
        return stats
    
    @staticmethod
    async def create_task_log(
        session: AsyncSession,
        task_id: int,
        user_id: int,
        action: str,
        old_status = None,
        new_status = None,
        details: dict = None
    ):
        """Создать лог задачи"""
        log = TaskLog(
            task_id=task_id,
            user_id=user_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            details=details
        )
        session.add(log)
        await session.commit()
        
        logger.info(f"Лог задачи {task_id}: {action}")


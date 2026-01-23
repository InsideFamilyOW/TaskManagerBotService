"""Сервис для работы со статусом занятости исполнителей и уведомлениями баеров."""

from typing import Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TaskStatus
from db.queries.task_queries import TaskQueries
from db.queries.user_queries import UserQueries
from bot.utils.notifications import NotificationService
from log import logger


class ExecutorStatusService:
    """Бизнес-логика, связанная с занятостью исполнителей."""

    @staticmethod
    async def is_executor_busy(session: AsyncSession, executor_id: int) -> bool:
        """
        Проверить, занят ли исполнитель.

        Исполнитель считается занятым только если:
        1. У него есть задачи в статусе IN_PROGRESS
        2. И он помечен как недоступный (is_available=False)
        
        Если исполнитель доступен (is_available=True), он может брать новые задачи,
        даже если у него есть задачи в работе.
        """
        # Получаем информацию об исполнителе
        executor = await UserQueries.get_user_by_id(session, executor_id)
        if not executor:
            return True  # Если исполнитель не найден, считаем его занятым
        
        # Если исполнитель помечен как доступный, он не занят
        if getattr(executor, 'is_available', True):
            return False
        
        # Если исполнитель недоступен, проверяем наличие задач в работе
        in_progress = await TaskQueries.count_tasks_by_executor(
            session=session,
            executor_id=executor_id,
            status=TaskStatus.IN_PROGRESS,
        )
        return in_progress > 0

    @staticmethod
    async def notify_buyers_if_executor_free(
        bot: Bot,
        session: AsyncSession,
        executor_id: int,
    ) -> int:
        """
        Если у исполнителя больше нет задач в работе, уведомить всех баеров,
        которым он назначен.

        Возвращает количество уведомлённых баеров.
        """
        # Проверяем, остались ли задачи в работе
        in_progress = await TaskQueries.count_tasks_by_executor(
            session=session,
            executor_id=executor_id,
            status=TaskStatus.IN_PROGRESS,
        )
        if in_progress > 0:
            return 0

        executor = await UserQueries.get_user_by_id(session, executor_id)
        if not executor:
            return 0

        buyers = await UserQueries.get_buyers_for_executor(session, executor_id)
        if not buyers:
            return 0

        notified = 0
        for buyer in buyers:
            msg = (
                "🟢 <b>ИСПОЛНИТЕЛЬ СВОБОДЕН</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🛠️ <b>Исполнитель:</b> {executor.first_name} {executor.last_name or ''}\n\n"
                "Этот исполнитель завершил все задачи и сейчас свободен.\n"
                "Вы можете назначить ему новую задачу."
            )
            ok = await NotificationService.notify_user(
                bot=bot,
                user_id=buyer.telegram_id,
                message=msg,
            )
            if ok:
                notified += 1

        logger.info(
            f"Уведомлено баеров о том, что исполнитель {executor_id} свободен: {notified}/{len(buyers)}"
        )
        return notified



"""Обработчики профиля исполнителя для байера."""

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries
from db.models import TaskStatus
from bot.keyboards.buyer_profile_kb import BuyerProfileKeyboards
from bot.keyboards.buyer_kb import BuyerKeyboards
from log import logger


router = Router()


@router.callback_query(F.data.startswith("buyer_exec_profile_"))
async def buyer_view_executor_profile(callback: CallbackQuery):
    """Показать байеру профиль закреплённого исполнителя."""
    executor_id = int(callback.data.replace("buyer_exec_profile_", ""))

    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_id(session, executor_id)

        if not executor:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        text = f"""
👤 <b>ПРОФИЛЬ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Имя: {executor.first_name or ''} {executor.last_name or ''}
Username: @{executor.username or 'нет'}

Направление: {executor.direction.value if executor.direction else 'не указано'}
Текущая загрузка: {executor.current_load}

Исполнитель закреплён за вами. Ниже можно посмотреть его задачи.
"""

        await callback.message.edit_text(
            text,
            reply_markup=BuyerProfileKeyboards.executor_profile(executor_id),
            parse_mode="HTML",
        )
        await callback.answer()


@router.callback_query(F.data.startswith("buyer_exec_tasks_"))
async def buyer_view_executor_tasks(callback: CallbackQuery):
    """Показ задач исполнителя по статусу."""
    # callback_data имеет вид: buyer_exec_tasks_<executor_id>_<status>
    data = callback.data.replace("buyer_exec_tasks_", "")
    exec_id_str, status_value = data.split("_", 1)
    executor_id = int(exec_id_str)
    status = TaskStatus(status_value)

    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_id(session, executor_id)
        if not executor:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return

        tasks = await TaskQueries.get_tasks_by_executor(
            session, executor_id, status=status
        )

        if not tasks:
            await callback.answer("❌ У исполнителя нет задач с таким статусом", show_alert=True)
            return

        status_names = {
            TaskStatus.PENDING: "⏳ Ожидают",
            TaskStatus.IN_PROGRESS: "🟡 В работе",
            TaskStatus.APPROVED: "🎉 Одобрены",
        }

        text = f"""
📋 <b>ЗАДАЧИ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Исполнитель: {executor.first_name or ''} {executor.last_name or ''}
Статус: {status_names.get(status, status.value)}

Выберите задачу для просмотра:
"""

        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_list(tasks),
            parse_mode="HTML",
        )
        await callback.answer()



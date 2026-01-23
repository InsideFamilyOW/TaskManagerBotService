"""Обработчики для исполнителя"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, timezone

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries, MessageQueries, FileQueries, LogQueries
from db.models import UserRole, TaskStatus, RejectionReason, FileType
from bot.keyboards.executor_kb import ExecutorKeyboards
from bot.keyboards.common_kb import CommonKeyboards
from states.executor_states import ExecutorStates
from bot.utils.file_handler import FileHandler
from bot.utils.photo_handler import PhotoHandler
from bot.utils.log_channel import LogChannel
from bot.services.executor_status_service import ExecutorStatusService
from log import logger

router = Router()



async def _can_executor_reject_task(session, task_id: int, executor_telegram_id: int) -> bool:
    """Проверить, может ли текущий исполнитель ещё раз отказаться от задачи"""
    executor = await UserQueries.get_user_by_telegram_id(session, executor_telegram_id)
    if not executor:
        return False
    return not await TaskQueries.has_executor_rejected(session, task_id, executor.id)


def format_task_management_text(task, messages=None):
    """Сформировать текст управления задачей для повторного использования."""
    from bot.utils.time_tracker import get_execution_time_display
    
    priority_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
    priority_names = ["Низкий", "Средний", "Высокий", "Срочный"]
    
    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.IN_PROGRESS: "🟡",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.APPROVED: "🎉"
    }
    
    buyer_name = (
        f"{task.creator.first_name} {task.creator.last_name or ''}"
        if task.creator else "Неизвестен"
    )
    deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
    
    # Получаем время выполнения
    execution_time = get_execution_time_display(task)
    
    text = f"""
🔧 <b>УПРАВЛЕНИЕ ЗАДАЧЕЙ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>{task.title}</b>
🏷️ <b>Статус:</b> {status_emoji.get(task.status, '')} {task.status.value}
👤 <b>Байер:</b> {buyer_name}
⏱️ <b>Срок:</b> {deadline_str}
📍 <b>Приоритет:</b> {priority_emoji.get(task.priority, '')} {priority_names[task.priority-1]}

{execution_time}

━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Описание:</b>
{task.description}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if messages:
        text += "\n💬 <b>История сообщений:</b>\n"
        for msg in messages[-3:]:
            sender_name = msg.sender.first_name if msg.sender else "Система"
            time_str = msg.created_at.strftime("%H:%M")
            text += f"[{time_str}] {sender_name}: {msg.content[:50]}...\n"
    
    text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return text


# ============ ГЛАВНОЕ МЕНЮ ============

@router.message(F.text == "🆕 Новые задачи")
async def executor_new_tasks(message: Message, state: FSMContext):
    """Новые задачи для исполнителя"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет новых задач (PENDING)
        pending_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.PENDING)
        
        if pending_count == 0:
            await message.answer(
                "📭 <b>НЕТ НОВЫХ ЗАДАЧ</b>\n\n"
                "У вас пока нет новых назначенных задач.",
                parse_mode="HTML"
            )
            return
        
        # Загружаем только первую страницу новых задач
        page = 1
        per_page = 5
        tasks = await TaskQueries.get_available_tasks_for_executor(
            session, user.id, status=TaskStatus.PENDING, page=page, per_page=per_page
        )
        
        text = f"""
🆕 <b>НОВЫЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Найдено новых задач: {pending_count}

Выберите задачу для просмотра:
"""
        
        await message.answer(
            text,
            reply_markup=ExecutorKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=pending_count, is_new_tasks=True),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "executor_toggle_availability")
async def toggle_executor_availability(callback: CallbackQuery):
    """Переключение статуса 'Работаю / Не работаю' исполнителем из профиля"""
    async with AsyncSessionLocal() as session:
        # Берем пользователя без фильтрации по is_active, чтобы не сломать переключение
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id, active_only=False)

        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ Доступно только для исполнителей", show_alert=True)
            return

        # Переключаем флаг
        current = getattr(user, "is_available", True)
        user.is_available = not current
        await session.commit()

        # Обновляем только клавиатуру под сообщением профиля
        from bot.keyboards.executor_kb import ExecutorKeyboards
        await callback.message.edit_reply_markup(
            reply_markup=ExecutorKeyboards.profile_actions(user.is_available)
        )

        status_text = "Теперь вы <b>работаете</b> и можете получать новые задачи" if user.is_available \
            else "Теперь вы <b>не принимаете новые задачи</b>. Баеры не увидят вас при создании новых задач."
        await callback.answer(status_text, show_alert=False)


@router.callback_query(F.data == "executor_my_tasks")
async def callback_executor_my_tasks(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку задач исполнителя (оптимизировано)"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет без загрузки данных
        total_count = await TaskQueries.count_available_tasks_for_executor(session, user.id)
        in_progress_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.IN_PROGRESS)
        pending_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.PENDING)
        
        if total_count == 0:
            await callback.message.edit_text("📋 У вас пока нет задач")
            await callback.answer()
            return
        
        # Загружаем только первую страницу активных задач (PENDING + IN_PROGRESS)
        page = 1
        per_page = 5
        # Сначала загружаем задачи в работе, затем ожидающие
        tasks = []
        if in_progress_count > 0:
            tasks.extend(await TaskQueries.get_available_tasks_for_executor(
                session, user.id, status=TaskStatus.IN_PROGRESS, page=page, per_page=per_page
            ))
        remaining_slots = per_page - len(tasks)
        if remaining_slots > 0 and pending_count > 0:
            tasks.extend(await TaskQueries.get_available_tasks_for_executor(
                session, user.id, status=TaskStatus.PENDING, page=page, per_page=remaining_slots
            ))
        
        active_count = in_progress_count + pending_count
        
        text = f"""
📋 <b>МОИ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Всего задач: {total_count}
🟡 В работе: {in_progress_count}

Выберите задачу для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=active_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("executor_new_tasks_page_"))
async def callback_executor_new_tasks_page(callback: CallbackQuery, state: FSMContext):
    """Перелистывание страниц новых задач исполнителя"""
    await state.clear()
    
    try:
        page = int(callback.data.replace("executor_new_tasks_page_", ""))
    except ValueError:
        await callback.answer("❌ Ошибка перелистывания")
        return
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет новых задач (PENDING)
        pending_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.PENDING)
        
        if pending_count == 0:
            await callback.message.edit_text(
                "📭 <b>НЕТ НОВЫХ ЗАДАЧ</b>\n\n"
                "У вас пока нет новых назначенных задач.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Загружаем только запрошенную страницу
        per_page = 5
        
        # Проверяем валидность страницы
        total_pages = (pending_count + per_page - 1) // per_page
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
        
        # Загружаем задачи для текущей страницы
        tasks = await TaskQueries.get_available_tasks_for_executor(
            session, user.id, status=TaskStatus.PENDING, page=page, per_page=per_page
        )
        
        text = f"""
🆕 <b>НОВЫЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Найдено новых задач: {pending_count}

Выберите задачу для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=pending_count, is_new_tasks=True),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("executor_tasks_page_"))
async def callback_executor_tasks_page(callback: CallbackQuery, state: FSMContext):
    """Перелистывание страниц задач исполнителя (оптимизировано)"""
    await state.clear()
    
    try:
        page = int(callback.data.replace("executor_tasks_page_", ""))
    except ValueError:
        await callback.answer("❌ Ошибка перелистывания")
        return
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет без загрузки данных
        total_count = await TaskQueries.count_available_tasks_for_executor(session, user.id)
        in_progress_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.IN_PROGRESS)
        pending_count = await TaskQueries.count_available_tasks_for_executor(session, user.id, status=TaskStatus.PENDING)
        
        if total_count == 0:
            await callback.message.edit_text("📋 У вас пока нет задач")
            await callback.answer()
            return
        
        # Загружаем только запрошенную страницу
        per_page = 5
        active_count = in_progress_count + pending_count
        
        # Проверяем валидность страницы
        total_pages = (active_count + per_page - 1) // per_page
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
        
        # Загружаем задачи для текущей страницы
        tasks = []
        if in_progress_count > 0:
            in_progress_tasks = await TaskQueries.get_available_tasks_for_executor(
                session, user.id, status=TaskStatus.IN_PROGRESS, page=page, per_page=per_page
            )
            tasks.extend(in_progress_tasks)
        
        remaining_slots = per_page - len(tasks)
        if remaining_slots > 0 and pending_count > 0:
            pending_tasks = await TaskQueries.get_available_tasks_for_executor(
                session, user.id, status=TaskStatus.PENDING, page=page, per_page=remaining_slots
            )
            tasks.extend(pending_tasks)
        
        text = f"""
📋 <b>МОИ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Всего задач: {total_count}
🟡 В работе: {in_progress_count}

Выберите задачу для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=active_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("executor_history_"))
async def callback_task_history(callback: CallbackQuery):
    """История сообщений по задаче"""
    task_id = int(callback.data.replace("executor_history_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
        
        # Получаем все сообщения
        messages = await MessageQueries.get_task_messages(session, task_id)
        
        if not messages:
            await callback.answer("📭 Нет сообщений", show_alert=True)
            return
        
        text = f"""
💬 <b>ИСТОРИЯ СООБЩЕНИЙ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Задача: {task.task_number}
📌 {task.title}

━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        for msg in messages:
            sender_name = msg.sender.first_name if msg.sender else "Система"
            time_str = msg.created_at.strftime("%d.%m.%Y %H:%M")
            text += f"<b>[{time_str}] {sender_name}:</b>\n{msg.content}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"

        can_reject = await _can_executor_reject_task(session, task_id, callback.from_user.id)

        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_management(task_id, task.status, can_reject=can_reject),
            parse_mode="HTML"
        )
    
    await callback.answer()


async def _show_task_view(callback: CallbackQuery, task_id: int):
    """Вспомогательная функция для отображения задачи"""
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
        
        # Получаем историю сообщений
        messages = await MessageQueries.get_task_messages(session, task_id)

        text = format_task_management_text(task, messages)

        can_reject = await _can_executor_reject_task(session, task_id, callback.from_user.id)

        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_management(task_id, task.status, can_reject=can_reject),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("executor_view_task_"))
async def callback_view_task(callback: CallbackQuery):
    """Просмотр задачи"""
    task_id = int(callback.data.replace("executor_view_task_", ""))
    await _show_task_view(callback, task_id)


# ============ ПРИНЯТИЕ ЗАДАЧИ ============

@router.callback_query(F.data.startswith("executor_take_"))
async def callback_take_task(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Взять задачу в работу"""
    task_id = int(callback.data.replace("executor_take_", ""))
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была отменена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена", show_alert=True)
            return
        
        # Обновляем статус задачи
        await TaskQueries.update_task_status(session, task_id, TaskStatus.IN_PROGRESS, executor.id, "Задача взята в работу")
        
        # Логируем действие
        await LogQueries.create_action_log(
            session=session,
            user_id=executor.id,
            action_type="task_taken",
            entity_type="task",
            entity_id=task_id,
            details={"task_number": task.task_number}
        )
        
        # Логируем в канал
        await LogChannel.log_task_status_change(bot, task, TaskStatus.PENDING, TaskStatus.IN_PROGRESS, executor)
        
        # Уведомляем байера
        if task.creator:
            try:
                await bot.send_message(
                    task.creator.telegram_id,
                    f"✅ <b>ЗАДАЧА ВЗЯТА В РАБОТУ</b>\n\n"
                    f"📋 Задача: {task.task_number}\n"
                    f"🛠️ Исполнитель: {executor.first_name} {executor.last_name or ''}\n\n"
                    f"Исполнитель приступил к выполнению задачи.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления байеру: {e}")
        
        # Подтверждение исполнителю
        await callback.message.edit_text(
            f"""
✅ <b>ВЫ ВЗЯЛИ ЗАДАЧУ В РАБОТУ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
🏷️ <b>Статус:</b> 🟡 В работе

━━━━━━━━━━━━━━━━━━━━━━━━━━

Байер получил уведомление.

Теперь вы можете:
• Общаться с байером через бота
• Отправлять промежуточные результаты
• Завершить задачу

━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
            reply_markup=ExecutorKeyboards.task_taken_actions(task_id),
            parse_mode="HTML"
        )
        
        logger.info(f"Исполнитель {executor.telegram_id} взял задачу {task.task_number}")
    
    await callback.answer("Задача принята!")


@router.callback_query(F.data.startswith("executor_open_"))
async def callback_open_task(callback: CallbackQuery):
    """Открыть задачу"""
    task_id = int(callback.data.replace("executor_open_", ""))
    
    # Перенаправляем на просмотр задачи
    await _show_task_view(callback, task_id)


# ============ ОТКАЗ ОТ ЗАДАЧИ ============

@router.callback_query(F.data.startswith("executor_reject_"))
async def callback_reject_task(callback: CallbackQuery, state: FSMContext):
    """Отказ от задачи"""
    task_id = int(callback.data.replace("executor_reject_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
        
        # Проверяем, что задача не завершена или одобрена
        if task.status in [TaskStatus.COMPLETED, TaskStatus.APPROVED]:
            await callback.answer("❌ Нельзя отказаться от задачи, которая уже выполнена", show_alert=True)
            return
    
    await state.update_data(reject_task_id=task_id)
    
    await callback.message.edit_text(
        """
⚠️ <b>ОТКАЗ ОТ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Укажите причину отказа:
""",
        reply_markup=ExecutorKeyboards.reject_reason(),
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_reject_reason)
    await callback.answer()


@router.callback_query(
    F.data.in_([
        "reject_lack_info", 
        "reject_out_of_scope", 
        "reject_tech_limitations", 
        "reject_overload", 
        "reject_other"
    ]), 
    ExecutorStates.waiting_reject_reason
)
async def process_reject_reason(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка причины отказа"""
    reason_map = {
        "reject_lack_info": ("Не хватает информации в ТЗ", RejectionReason.LACK_INFO),
        "reject_out_of_scope": ("Задача вне моей компетенции", RejectionReason.OUT_OF_SCOPE),
        "reject_tech_limitations": ("Технические ограничения", RejectionReason.TECH_LIMITATIONS),
        "reject_overload": ("Перегрузка по задачам", RejectionReason.OVERLOAD),
        "reject_other": ("Другая причина", RejectionReason.OTHER)
    }
    
    reason_text, reason_enum = reason_map.get(callback.data, ("Другая причина", RejectionReason.OTHER))
    
    if reason_enum == RejectionReason.OTHER:
        await callback.message.edit_text(
            "📝 <b>ДРУГАЯ ПРИЧИНА</b>\n\n"
            "Пожалуйста, опишите причину отказа:",
            parse_mode="HTML"
        )
        await state.update_data(reason_enum=reason_enum)
        await state.set_state(ExecutorStates.waiting_reject_custom)
        await callback.answer()
        return
    
    # Обрабатываем отказ
    data = await state.get_data()
    task_id = data['reject_task_id']
    
    await process_task_rejection(callback.message, task_id, reason_enum, reason_text, callback.from_user.id, state, bot)
    await callback.answer("Отказ оформлен")


@router.message(ExecutorStates.waiting_reject_custom)
async def process_custom_reject_reason(message: Message, state: FSMContext, bot: Bot):
    """Обработка своей причины отказа"""
    custom_reason = message.text.strip()
    data = await state.get_data()
    task_id = data['reject_task_id']
    reason_enum = data['reason_enum']
    
    await process_task_rejection(message, task_id, reason_enum, custom_reason, message.from_user.id, state, bot)


async def process_task_rejection(message, task_id: int, reason_enum, reason_text: str, user_telegram_id: int, state: FSMContext, bot: Bot):
    """Обработать отказ от задачи"""
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_telegram_id(session, user_telegram_id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена или была удалена")
            await state.clear()
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await message.answer("❌ Эта задача была отменена и удалена")
            await state.clear()
            return
        
        # Сохраняем причину отказа
        from db.models import TaskRejection, TaskLog
        rejection = TaskRejection(
            task_id=task_id,
            executor_id=executor.id,
            reason=reason_enum,
            custom_reason=reason_text if reason_enum == RejectionReason.OTHER else None
        )
        session.add(rejection)
        
        # Сохраняем старый статус для логирования
        old_status = task.status
        
        # Если задача была в работе, уменьшаем загрузку и обнуляем время начала
        if task.status == TaskStatus.IN_PROGRESS:
            await UserQueries.update_user_load(session, executor.id, -1)
            task.started_at = None  # Обнуляем время начала для следующего исполнителя
        
        # Обновляем статус задачи
        task.executor_id = None
        task.status = TaskStatus.PENDING
        
        # Создаем запись в TaskLog для логирования изменения статуса
        task_log = TaskLog(
            task_id=task_id,
            user_id=executor.id,
            action="status_change",
            old_status=old_status,
            new_status=TaskStatus.PENDING,
            details={"comment": f"Отказ от задачи. Причина: {reason_text}"}
        )
        session.add(task_log)
        
        await session.commit()
        
        # Логируем действие
        await LogQueries.create_action_log(
            session=session,
            user_id=executor.id,
            action_type="task_rejected",
            entity_type="task",
            entity_id=task_id,
            details={"reason": reason_text}
        )
        
        # Логируем изменение статуса в канал
        await LogChannel.log_task_status_change(bot, task, old_status, TaskStatus.PENDING, executor)
        
        # Логируем отказ в канал
        await LogChannel.log_task_rejected(bot, task, executor, reason_text)
        
        # Уведомляем байера
        if task.creator:
            try:
                # Клавиатура для общения по поводу отказа и переназначения исполнителя
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                builder.button(
                    text="💬 Обсудить отказ",
                    callback_data=f"buyer_message_{task.id}:{executor.id}"
                )
                builder.button(
                    text="👤 Назначить другого исполнителя",
                    callback_data=f"buyer_reassign_executor_{task.id}"
                )
                builder.adjust(1)

                await bot.send_message(
                    task.creator.telegram_id,
                    f"❌ <b>ОТКАЗ ОТ ЗАДАЧИ</b>\n\n"
                    f"📋 Задача: {task.task_number}\n"
                    f"🛠️ Исполнитель: {executor.first_name} {executor.last_name or ''}\n"
                    f"💬 Причина: {reason_text}\n\n"
                    f"Задача возвращена в статус ожидания.\n"
                    f"Вы можете написать исполнителю, чтобы обсудить отказ.\n"
                    f"При необходимости вы можете сразу назначить другого исполнителя.",
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления байеру: {e}")
        
        # Подтверждение исполнителю
        await message.answer(
            f"❌ <b>ВЫ ОТКАЗАЛИСЬ ОТ ЗАДАЧИ</b>\n\n"
            f"📋 Задача: {task.task_number}\n"
            f"💬 Причина: {reason_text}\n\n"
            f"Байер получил уведомление.",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Исполнитель {executor.telegram_id} отказался от задачи {task.task_number}")


# ============ ЗАВЕРШЕНИЕ ЗАДАЧИ ============

@router.callback_query(F.data.startswith("executor_complete_"))
async def callback_complete_task(callback: CallbackQuery, state: FSMContext):
    """Завершение задачи"""
    task_id = int(callback.data.replace("executor_complete_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
    
    await state.update_data(complete_task_id=task_id, completion_files=[])
    
    await callback.message.edit_text(
        """
🎯 <b>ЗАВЕРШЕНИЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 1/3: Комментарий к выполнению</b>

Добавьте комментарий о проделанной работе:
""",
        reply_markup=CommonKeyboards.skip_and_cancel(),
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_completion_comment)
    await callback.answer()


@router.callback_query(F.data == "skip", ExecutorStates.waiting_completion_comment)
async def skip_completion_comment(callback: CallbackQuery, state: FSMContext):
    """Пропустить комментарий"""
    await state.update_data(completion_comment=None)
    
    await callback.message.edit_text(
        """
📎 <b>ФАЙЛЫ РЕЗУЛЬТАТА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 2/3: Прикрепите файлы</b>

Отправьте файлы результата (до 5 файлов).
Когда закончите, нажмите "Завершить загрузку".
""",
        reply_markup=CommonKeyboards.file_actions(),
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_completion_files)
    await callback.answer("Комментарий пропущен")


@router.message(ExecutorStates.waiting_completion_comment)
async def process_completion_comment(message: Message, state: FSMContext):
    """Обработка комментария к выполнению"""
    comment = message.text.strip()
    
    await state.update_data(completion_comment=comment)
    
    await message.answer(
        """
✅ <b>Комментарий принят</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 2/3: Прикрепите файлы</b>

Отправьте файлы результата (до 5 файлов).
Когда закончите, нажмите "Завершить загрузку".
""",
        reply_markup=CommonKeyboards.file_actions(),
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_completion_files)


@router.message(ExecutorStates.waiting_completion_files, F.document | F.photo | F.video)
async def process_completion_file(message: Message, state: FSMContext, bot: Bot):
    """Обработка файла результата"""
    data = await state.get_data()
    files = data.get('completion_files', [])
    
    if len(files) >= 5:
        await message.answer("❌ Максимум 5 файлов!")
        return
    
    # Сохраняем информацию о файле
    if message.photo:
        # Фотография - будет храниться в base64
        photo = message.photo[-1]
        file_info = {
            'file_id': photo.file_id,
            'file_name': f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'mime_type': "image/jpeg",
            'file_size': photo.file_size,
            'is_photo': True,
            'is_video': False
        }
    elif message.video:
        # Видео
        video = message.video
        file_info = {
            'file_id': video.file_id,
            'file_name': video.file_name or f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            'mime_type': video.mime_type or "video/mp4",
            'file_size': video.file_size,
            'is_photo': False,
            'is_video': True
        }
    elif message.document:
        # Проверяем, является ли документ фотографией или видео
        is_photo = PhotoHandler.is_photo_mime_type(message.document.mime_type)
        is_video = message.document.mime_type and message.document.mime_type.startswith('video/')
        file_info = {
            'file_id': message.document.file_id,
            'file_name': message.document.file_name,
            'mime_type': message.document.mime_type,
            'file_size': message.document.file_size,
            'is_photo': is_photo,
            'is_video': is_video
        }
    else:
        return
    
    files.append(file_info)
    await state.update_data(completion_files=files)
    
    if file_info.get('is_photo'):
        file_type = "📷 Фото"
    elif file_info.get('is_video'):
        file_type = "🎥 Видео"
    else:
        file_type = "📎 Файл"
    
    await message.answer(
        f"✅ {file_type} добавлен ({len(files)}/5)\n\n"
        f"Отправьте еще файлы или нажмите 'Завершить загрузку'.",
        reply_markup=CommonKeyboards.file_actions()
    )


@router.callback_query(F.data == "files_done", ExecutorStates.waiting_completion_files)
async def files_upload_done(callback: CallbackQuery, state: FSMContext):
    """Завершение загрузки файлов"""
    data = await state.get_data()
    files = data.get('completion_files', [])
    
    await callback.message.edit_text(
        f"""
📋 <b>ПОДТВЕРЖДЕНИЕ ОТПРАВКИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 3/3: Проверка данных</b>

💬 Комментарий: {"Да" if data.get('completion_comment') else "Нет"}
📎 Файлов: {len(files)}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправить результат байеру?
""",
        reply_markup=CommonKeyboards.confirm_action("send_completion", str(data['complete_task_id'])),
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_completion_confirm)
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_send_completion:"), ExecutorStates.waiting_completion_confirm)
async def confirm_send_completion(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение отправки результата"""
    task_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            await state.clear()
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            await state.clear()
            return
        
        # Обновляем задачу
        task.completion_comment = data.get('completion_comment')
        old_status = task.status
        await TaskQueries.update_task_status(
            session,
            task_id,
            TaskStatus.COMPLETED,
            executor.id,
            "Задача выполнена",
        )

        # Если после завершения задачи у исполнителя не осталось задач в работе,
        # уведомляем всех баеров, которым он назначен
        await ExecutorStatusService.notify_buyers_if_executor_free(bot, session, executor.id)
        
        # Сохраняем файлы в БД
        files_info = data.get('completion_files', [])
        for file_info in files_info:
            is_photo = file_info.get('is_photo', False)
            
            if is_photo:
                # Сохраняем фото в base64
                if 'file_id' in file_info:
                    # Определяем тип фото
                    if file_info.get('mime_type') and file_info['mime_type'] != 'image/jpeg':
                        # Это файл-фото
                        photo_data = await PhotoHandler.download_and_encode_photo_from_file(bot, file_info['file_id'])
                    else:
                        # Это обычная фотография
                        photo_size = type('obj', (object,), {'file_id': file_info['file_id'], 'file_size': file_info.get('file_size', 0)})
                        photo_data = await PhotoHandler.download_and_encode_photo(bot, photo_size)
                    
                    if photo_data:
                        base64_string, file_size, mime_type = photo_data
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.RESULT,
                            file_name=file_info['file_name'],
                            file_data=base64_string,
                            file_size=file_size,
                            uploaded_by_id=executor.id,
                            mime_type=mime_type
                        )
                        # Отправляем файл в канал
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="RESULT",
                            uploaded_by=executor,
                            mime_type=mime_type
                        )
            else:
                # Сохраняем обычный файл в БД (base64) - включая видео
                # Для больших файлов (>20MB) сохраняем только file_id
                MAX_SIZE_FOR_BASE64 = 20 * 1024 * 1024  # 20 MB
                file_size_from_info = file_info.get('file_size', 0)
                
                try:
                    # Если файл больше 20MB или является видео, сохраняем только file_id
                    if file_size_from_info > MAX_SIZE_FOR_BASE64 or file_info.get('is_video', False):
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.RESULT,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=executor.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        # Отправляем файл в канал
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="RESULT",
                            uploaded_by=executor,
                            mime_type=final_mime_type
                        )
                    else:
                        # Пытаемся скачать и сохранить в base64
                        file_data_tuple = await FileHandler.download_and_encode_file(bot, file_info['file_id'])
                        if file_data_tuple:
                            base64_string, file_size, mime_type = file_data_tuple
                            final_mime_type = file_info.get('mime_type') or mime_type
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.RESULT,
                                file_name=file_info['file_name'],
                                file_data=base64_string,
                                file_size=file_size,
                                uploaded_by_id=executor.id,
                                mime_type=final_mime_type
                            )
                            # Отправляем файл в канал
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="RESULT",
                                uploaded_by=executor,
                                mime_type=final_mime_type
                            )
                        else:
                            # Если не удалось скачать, сохраняем только file_id
                            logger.warning(f"Не удалось скачать файл {file_info.get('file_name')}, сохраняем только file_id")
                            final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.RESULT,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=executor.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                except Exception as e:
                    logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}, сохраняем только file_id")
                    try:
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.RESULT,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=executor.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                    except Exception as e2:
                        logger.error(f"Критическая ошибка при сохранении file_id: {e2}")
        
        # Вычисляем время выполнения
        if task.started_at:
            completion_time = datetime.now(timezone.utc) - task.started_at
            days = completion_time.days
            hours = completion_time.seconds // 3600
            completion_time_str = f"{days} дней {hours} часов" if days > 0 else f"{hours} часов"
        else:
            completion_time_str = "Неизвестно"
        
        # Логируем в канал
        await LogChannel.log_task_completed(bot, task, executor, completion_time_str)
        
        # Уведомляем байера с файлами в одном сообщении
        if task.creator:
            files_text = "\n".join([f"• {f['file_name']}" for f in files_info]) if files_info else "Нет файлов"
            
            try:
                from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaVideo
                
                text_message = f"""
📬 <b>РЕЗУЛЬТАТ ПО ЗАДАЧЕ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>{task.title}</b>

👤 <b>Исполнитель:</b> {executor.first_name} {executor.last_name or ''}
⏱️ <b>Время выполнения:</b> {completion_time_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Комментарий исполнителя:</b>
{task.completion_comment or 'Без комментария'}

━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 <b>Прикрепленные файлы:</b>
{files_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Пожалуйста, проверьте результат.
Используйте /start для доступа к задаче.
"""
                
                # Если есть файлы, отправляем их как media group с первым файлом содержащим caption
                if files_info:
                    media_group = []
                    for idx, file_info in enumerate(files_info):
                        is_photo = file_info.get('is_photo', False)
                        is_video = file_info.get('is_video', False)
                        caption = text_message if idx == 0 else None
                        
                        if is_photo:
                            media_group.append(InputMediaPhoto(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                        elif is_video:
                            media_group.append(InputMediaVideo(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                        else:
                            media_group.append(InputMediaDocument(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                    
                    # Отправляем media group
                    await bot.send_media_group(task.creator.telegram_id, media=media_group)
                else:
                    # Если нет файлов, отправляем обычное сообщение
                    await bot.send_message(
                        task.creator.telegram_id,
                        text_message,
                        parse_mode="HTML"
                    )
                        
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления байеру: {e}")
        
        # Подтверждение исполнителю
        await callback.message.edit_text(
            f"""
📨 <b>РЕЗУЛЬТАТ ОТПРАВЛЕН БАЙЕРУ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Задача {task.task_number} ожидает проверки
💬 Ваш комментарий: "{task.completion_comment or 'Без комментария'}"
📎 Прикреплено файлов: {len(files_info)}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Байер получит уведомление для проверки.
После подтверждения задача будет завершена.
""",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Исполнитель {executor.telegram_id} завершил задачу {task.task_number}")
    
    await callback.answer("Результат отправлен!")


# ============ КОММУНИКАЦИЯ ============

@router.callback_query(F.data.startswith("executor_message_"))
async def callback_send_message(callback: CallbackQuery, state: FSMContext):
    """Отправка сообщения байеру"""
    task_id = int(callback.data.replace("executor_message_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
    
    await state.update_data(message_task_id=task_id)
    
    await callback.message.edit_text(
        """
💭 <b>СООБЩЕНИЕ БАЙЕРУ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше сообщение будет отправлено автору задачи
и добавлено в историю обсуждения.

━━━━━━━━━━━━━━━━━━━━━━━━━━

Напишите ваше сообщение:
""",
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_message_to_buyer)
    await callback.answer()


@router.message(ExecutorStates.waiting_message_to_buyer)
async def process_message_to_buyer(message: Message, state: FSMContext, bot: Bot):
    """Обработка сообщения байеру"""
    content = message.text.strip()
    data = await state.get_data()
    task_id = data['message_task_id']
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена или была удалена")
            await state.clear()
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await message.answer("❌ Эта задача была отменена и удалена")
            await state.clear()
            return
        
        # Сохраняем сообщение
        await MessageQueries.create_message(
            session=session,
            task_id=task_id,
            sender_id=executor.id,
            content=content
        )
        
        # Отправляем байеру
        if task.creator:
            try:
                # Создаем клавиатуру с кнопкой "Ответить"
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                # Передаем ID исполнителя, чтобы байер мог ответить даже если задача позже будет без исполнителя
                builder.button(text="💬 Ответить", callback_data=f"buyer_message_{task.id}:{executor.id}")
                
                await bot.send_message(
                    task.creator.telegram_id,
                    f"""
💬 <b>СООБЩЕНИЕ ОТ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
🛠️ <b>От:</b> {executor.first_name} {executor.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

{content}

━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения байеру: {e}")
        
        await message.answer(
            "✅ <b>Сообщение отправлено байеру</b>",
            parse_mode="HTML"
        )
        
        # Возвращаем исполнителя к экрану управления задачей
        messages = await MessageQueries.get_task_messages(session, task_id)
        task_view_text = format_task_management_text(task, messages)
        await message.answer(
            task_view_text,
            reply_markup=ExecutorKeyboards.task_management(
                task_id,
                task.status,
                can_reject=not await TaskQueries.has_executor_rejected(session, task_id, executor.id),
            ),
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Исполнитель {executor.telegram_id} отправил сообщение по задаче {task.task_number}")


@router.callback_query(F.data.startswith("executor_clarify_"))
async def callback_clarify_task(callback: CallbackQuery, state: FSMContext):
    """Запросить уточнение"""
    task_id = int(callback.data.replace("executor_clarify_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
    
    await state.update_data(message_task_id=task_id)
    
    await callback.message.edit_text(
        """
💭 <b>УТОЧНЕНИЕ ПО ЗАДАЧЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше сообщение с уточняющими вопросами будет отправлено автору задачи
и добавлено в историю обсуждения.

━━━━━━━━━━━━━━━━━━━━━━━━━━

Напишите ваши вопросы:
""",
        parse_mode="HTML"
    )
    await state.set_state(ExecutorStates.waiting_message_to_buyer)
    await callback.answer()


@router.callback_query(F.data.startswith("executor_add_file_"))
async def callback_add_file_to_task(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Добавление файла к задаче"""
    task_id = int(callback.data.replace("executor_add_file_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            return
        
        # Получаем уже существующие файлы задачи
        existing_files = await FileQueries.get_task_files(session, task_id)
        
        # Если есть файлы, показываем их список с кнопками
        if existing_files:
            # Формируем список файлов для кнопок
            files_list = []
            files_text_lines = []
            
            for file_record in existing_files:
                file_icon = "📷" if file_record.mime_type and file_record.mime_type.startswith('image/') else "📎"
                size_mb = file_record.file_size / (1024 * 1024) if file_record.file_size else 0
                uploader_name = f"{file_record.uploader.first_name} {file_record.uploader.last_name or ''}".strip() if file_record.uploader else "Неизвестно"
                
                files_list.append({
                    'id': file_record.id,
                    'file_name': file_record.file_name,
                    'is_photo': file_record.mime_type and file_record.mime_type.startswith('image/')
                })
                
                files_text_lines.append(f"• {file_record.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}")
            
            files_text = "\n".join(files_text_lines)
            
            # Первое сообщение - список файлов для просмотра
            await callback.message.edit_text(
                f"""
📎 <b>ФАЙЛЫ ЗАДАЧИ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Файлы из сообщений ({len(existing_files)}):</b>

{files_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Нажмите на файл чтобы просмотреть его.
""",
                reply_markup=CommonKeyboards.file_list_view_only(files_list, f"task_{task_id}"),
                parse_mode="HTML"
            )
            
            # Второе сообщение - форма добавления новых файлов
            await callback.message.answer(
                f"""
📎 <b>ДОБАВИТЬ ФАЙЛЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файлы, которые хотите прикрепить к задаче.
Можно отправить несколько файлов (до 10).

📋 <b>Уже добавлено ({len(existing_files)}/10 файлов)</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━

Когда закончите, нажмите "Завершить загрузку".
""",
                reply_markup=CommonKeyboards.file_actions(),
                parse_mode="HTML"
            )
        else:
            # Если файлов нет, сразу показываем форму добавления
            await callback.message.edit_text(
                """
📎 <b>ДОБАВИТЬ ФАЙЛЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файлы, которые хотите прикрепить к задаче.
Можно отправить несколько файлов (до 10).

━━━━━━━━━━━━━━━━━━━━━━━━━━

Когда закончите, нажмите "Завершить загрузку".
""",
                reply_markup=CommonKeyboards.file_actions(),
                parse_mode="HTML"
            )
        
        await state.update_data(file_task_id=task_id, task_files=[])
        await state.set_state(ExecutorStates.waiting_file_to_task)
    
    await callback.answer()


@router.callback_query(F.data.startswith("view_file_task_"))
async def view_task_file(callback: CallbackQuery, bot: Bot):
    """Просмотр файла задачи"""
    # Формат: view_file_task_{task_id}:{file_idx}
    parts = callback.data.replace("view_file_task_", "").split(":")
    task_id = int(parts[0])
    file_idx = int(parts[1])
    
    async with AsyncSessionLocal() as session:
        # Получаем все файлы задачи
        existing_files = await FileQueries.get_task_files(session, task_id)
        
        if file_idx >= len(existing_files):
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
        
        file_record = existing_files[file_idx]
        
        try:
            # Проверяем, есть ли сохраненный file_id для больших файлов
            telegram_file_id = FileQueries.get_telegram_file_id(file_record)
            
            size_mb = file_record.file_size / (1024 * 1024) if file_record.file_size else 0
            caption = f"{file_record.file_name}\n📊 Размер: {size_mb:.2f} МБ"
            
            if telegram_file_id:
                # Отправляем файл используя сохраненный file_id
                if file_record.mime_type and file_record.mime_type.startswith('image/'):
                    await bot.send_photo(callback.from_user.id, telegram_file_id, caption=caption)
                elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                    await bot.send_video(callback.from_user.id, telegram_file_id, caption=caption)
                else:
                    await bot.send_document(callback.from_user.id, telegram_file_id, caption=caption)
                await callback.answer("✅ Файл отправлен")
            else:
                from aiogram.types import BufferedInputFile
                
                # Получаем данные файла
                file_data = file_record.file_data or file_record.photo_base64
                
                if file_data:
                    # Декодируем из base64
                    file_bytes = FileHandler.decode_file_base64(file_data)
                    if file_bytes:
                        input_file = BufferedInputFile(file_bytes, filename=file_record.file_name)
                        
                        # Отправляем как фото, видео или документ
                        if file_record.mime_type and file_record.mime_type.startswith('image/'):
                            await bot.send_photo(callback.from_user.id, input_file, caption=caption)
                        elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                            await bot.send_video(callback.from_user.id, input_file, caption=caption)
                        else:
                            await bot.send_document(callback.from_user.id, input_file, caption=caption)
                        
                        await callback.answer("✅ Файл отправлен")
                    else:
                        await callback.answer("❌ Ошибка декодирования файла", show_alert=True)
                elif file_record.file_path:
                    # Проверяем, это telegram_file_id или путь к файлу на диске
                    if file_record.file_path.startswith("telegram_file_id:"):
                        telegram_file_id = file_record.file_path.replace("telegram_file_id:", "")
                        if file_record.mime_type and file_record.mime_type.startswith('image/'):
                            await bot.send_photo(callback.from_user.id, telegram_file_id, caption=caption)
                        elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                            await bot.send_video(callback.from_user.id, telegram_file_id, caption=caption)
                        else:
                            await bot.send_document(callback.from_user.id, telegram_file_id, caption=caption)
                        await callback.answer("✅ Файл отправлен")
                    else:
                        # Старый формат - файл на диске
                        import os
                        if os.path.exists(file_record.file_path):
                            with open(file_record.file_path, 'rb') as f:
                                if file_record.mime_type and file_record.mime_type.startswith('image/'):
                                    await bot.send_photo(callback.from_user.id, f, caption=caption)
                                elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                                    await bot.send_video(callback.from_user.id, f, caption=caption)
                                else:
                                    await bot.send_document(callback.from_user.id, f, caption=caption)
                            
                            await callback.answer("✅ Файл отправлен")
                        else:
                            await callback.answer("❌ Файл не найден на диске", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await callback.answer("❌ Ошибка отправки файла", show_alert=True)


@router.callback_query(F.data.startswith("executor_view_files_"))
async def callback_executor_view_files(callback: CallbackQuery):
    """Просмотр файлов задачи исполнителем"""
    task_id = int(callback.data.replace("executor_view_files_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ У вас нет доступа")
            return
        
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
        
        # Проверяем, что исполнитель имеет доступ к этой задаче
        if task.executor_id != user.id:
            await callback.answer("❌ У вас нет доступа к этой задаче", show_alert=True)
            return
        
        # Получаем файлы задачи
        files = await FileQueries.get_task_files(session, task_id)
        
        if not files:
            await callback.answer("📭 Нет файлов", show_alert=True)
            return
        
        # Группируем файлы по типам
        initial_files = [f for f in files if f.file_type == FileType.INITIAL]
        result_files = [f for f in files if f.file_type == FileType.RESULT]
        message_files = [f for f in files if f.file_type == FileType.MESSAGE]
        
        text = f"""
📎 <b>ФАЙЛЫ ЗАДАЧИ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        if initial_files:
            text += f"📤 <b>Исходные файлы ({len(initial_files)}):</b>\n"
            for f in initial_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n"
            text += "\n"
        
        if result_files:
            text += f"📥 <b>Файлы результата ({len(result_files)}):</b>\n"
            for f in result_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n"
            text += "\n"
        
        if message_files:
            text += f"💬 <b>Файлы из сообщений ({len(message_files)}):</b>\n"
            for f in message_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n\n"
        
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=ExecutorKeyboards.task_files_actions(task_id, files),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("executor_download_file_"))
async def callback_executor_download_file(callback: CallbackQuery, bot: Bot):
    """Скачивание файла исполнителем"""
    file_id = int(callback.data.replace("executor_download_file_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            await callback.answer("❌ У вас нет доступа")
            return
        
        file_record = await FileQueries.get_file_by_id(session, file_id)
        
        if not file_record:
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
        
        # Получаем задачу для проверки доступа
        task = await TaskQueries.get_task_by_id(session, file_record.task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
        
        # Проверяем, что исполнитель имеет доступ к задаче, к которой прикреплен файл
        if task.executor_id != user.id:
            await callback.answer("❌ У вас нет доступа к этому файлу", show_alert=True)
            return
        
        try:
            # Проверяем, есть ли сохраненный file_id для больших файлов
            telegram_file_id = FileQueries.get_telegram_file_id(file_record)
            
            if telegram_file_id:
                # Отправляем файл используя сохраненный file_id
                if file_record.mime_type and file_record.mime_type.startswith('image/'):
                    await bot.send_photo(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                    await bot.send_video(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                else:
                    await bot.send_document(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                await callback.answer("✅ Файл отправлен")
            elif file_record.file_data:
                # Декодируем файл из base64
                from aiogram.types import BufferedInputFile
                file_bytes = FileHandler.decode_file_base64(file_record.file_data)
                if file_bytes:
                    input_file = BufferedInputFile(file_bytes, filename=file_record.file_name)
                    # Определяем тип файла по mime_type
                    if file_record.mime_type and file_record.mime_type.startswith('image/'):
                        await bot.send_photo(callback.from_user.id, input_file, caption=file_record.file_name)
                    elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                        await bot.send_video(callback.from_user.id, input_file, caption=file_record.file_name)
                    else:
                        await bot.send_document(callback.from_user.id, input_file, caption=file_record.file_name)
                    await callback.answer("✅ Файл отправлен")
                else:
                    await callback.answer("❌ Ошибка декодирования файла", show_alert=True)
            elif file_record.photo_base64:
                # Устаревший формат - фото в base64
                from aiogram.types import BufferedInputFile
                photo_bytes = PhotoHandler.decode_photo_base64(file_record.photo_base64)
                if photo_bytes:
                    input_file = BufferedInputFile(photo_bytes, filename=file_record.file_name)
                    await bot.send_photo(callback.from_user.id, input_file, caption=file_record.file_name)
                    await callback.answer("✅ Фото отправлено")
                else:
                    await callback.answer("❌ Ошибка декодирования фото", show_alert=True)
            elif file_record.file_path:
                # Проверяем, это telegram_file_id или путь к файлу на диске
                if file_record.file_path.startswith("telegram_file_id:"):
                    # Это сохраненный file_id для большого файла
                    telegram_file_id = file_record.file_path.replace("telegram_file_id:", "")
                    if file_record.mime_type and file_record.mime_type.startswith('image/'):
                        await bot.send_photo(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                        await bot.send_video(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    else:
                        await bot.send_document(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    await callback.answer("✅ Файл отправлен")
                else:
                    # Устаревший формат - файл на диске
                    import os
                    if os.path.exists(file_record.file_path):
                        with open(file_record.file_path, 'rb') as f:
                            if file_record.mime_type and file_record.mime_type.startswith('image/'):
                                await bot.send_photo(callback.from_user.id, f)
                            elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                                await bot.send_video(callback.from_user.id, f, caption=file_record.file_name)
                            else:
                                await bot.send_document(callback.from_user.id, f, caption=file_record.file_name)
                        await callback.answer("✅ Файл отправлен")
                    else:
                        await callback.answer("❌ Файл не найден на диске", show_alert=True)
            else:
                await callback.answer("❌ Файл недоступен", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await callback.answer("❌ Ошибка отправки файла", show_alert=True)


@router.message(ExecutorStates.waiting_file_to_task, F.document | F.photo | F.video)
async def process_file_to_task(message: Message, state: FSMContext, bot: Bot):
    """Обработка файла для задачи"""
    data = await state.get_data()
    files = data.get('task_files', [])
    task_id = data.get('file_task_id')
    
    # Проверяем общее количество файлов (существующие + новые)
    async with AsyncSessionLocal() as session:
        existing_files = await FileQueries.get_task_files(session, task_id)
        total_files = len(existing_files) + len(files)
        
        if total_files >= 10:
            await message.answer(f"❌ Максимум 10 файлов! У вас уже {len(existing_files)} файлов в задаче.")
            return
    
    # Сохраняем информацию о файле
    if message.photo:
        # Фотография - будет храниться в base64
        photo = message.photo[-1]
        file_info = {
            'file_id': photo.file_id,
            'file_name': f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'mime_type': "image/jpeg",
            'file_size': photo.file_size,
            'is_photo': True,
            'is_video': False
        }
    elif message.video:
        # Видео
        video = message.video
        file_info = {
            'file_id': video.file_id,
            'file_name': video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            'mime_type': video.mime_type or "video/mp4",
            'file_size': video.file_size,
            'is_photo': False,
            'is_video': True
        }
    elif message.document:
        # Проверяем, является ли документ фотографией или видео
        is_photo = PhotoHandler.is_photo_mime_type(message.document.mime_type)
        is_video = message.document.mime_type and message.document.mime_type.startswith('video/')
        file_info = {
            'file_id': message.document.file_id,
            'file_name': message.document.file_name,
            'mime_type': message.document.mime_type,
            'file_size': message.document.file_size,
            'is_photo': is_photo,
            'is_video': is_video
        }
    else:
        return
    
    files.append(file_info)
    await state.update_data(task_files=files)
    
    if file_info.get('is_photo'):
        file_type = "📷 Фото"
    elif file_info.get('is_video'):
        file_type = "🎥 Видео"
    else:
        file_type = "📎 Файл"
    
    total_in_session = len(files)
    total_overall = len(existing_files) + len(files)
    
    await message.answer(
        f"✅ {file_type} добавлен!\n\n"
        f"📊 В этой сессии: {total_in_session}\n"
        f"📋 Всего в задаче: {total_overall}/10\n\n"
        f"Отправьте еще файлы или нажмите 'Завершить загрузку'.",
        reply_markup=CommonKeyboards.file_actions()
    )


@router.callback_query(F.data == "files_done", ExecutorStates.waiting_file_to_task)
async def files_to_task_done(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Завершение загрузки файлов к задаче"""
    data = await state.get_data()
    task_id = data.get('file_task_id')
    files = data.get('task_files', [])
    
    if not files:
        await callback.answer("❌ Не выбрано ни одного файла", show_alert=True)
        return
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            await state.clear()
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена и удалена", show_alert=True)
            await state.clear()
            return
        
        # Сохраняем файлы в БД
        saved_count = 0
        for file_info in files:
            is_photo = file_info.get('is_photo', False)
            
            if is_photo:
                # Сохраняем фото в base64
                if 'file_id' in file_info:
                    # Определяем тип фото
                    if file_info.get('mime_type') and file_info['mime_type'] != 'image/jpeg':
                        # Это файл-фото
                        photo_data = await PhotoHandler.download_and_encode_photo_from_file(bot, file_info['file_id'])
                    else:
                        # Это обычная фотография
                        photo_size = type('obj', (object,), {'file_id': file_info['file_id'], 'file_size': file_info.get('file_size', 0)})
                        photo_data = await PhotoHandler.download_and_encode_photo(bot, photo_size)
                    
                    if photo_data:
                        base64_string, file_size, mime_type = photo_data
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=base64_string,
                            file_size=file_size,
                            uploaded_by_id=executor.id,
                            mime_type=mime_type
                        )
                        # Отправляем файл в канал
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=executor,
                            mime_type=mime_type
                        )
                        saved_count += 1
            else:
                # Сохраняем обычный файл в БД (base64) - включая видео
                # Для больших файлов (>20MB) сохраняем только file_id
                MAX_SIZE_FOR_BASE64 = 20 * 1024 * 1024  # 20 MB
                file_size_from_info = file_info.get('file_size', 0)
                
                try:
                    # Если файл больше 20MB или является видео, сохраняем только file_id
                    if file_size_from_info > MAX_SIZE_FOR_BASE64 or file_info.get('is_video', False):
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=executor.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        # Отправляем файл в канал
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=executor,
                            mime_type=final_mime_type
                        )
                        saved_count += 1
                        logger.info(f"Большой файл сохранен с file_id: {file_info.get('file_name')} ({file_size_from_info / (1024*1024):.2f} MB)")
                    else:
                        # Пытаемся скачать и сохранить в base64
                        file_data_tuple = await FileHandler.download_and_encode_file(bot, file_info['file_id'])
                        if file_data_tuple:
                            base64_string, file_size, mime_type = file_data_tuple
                            # Используем mime_type из file_info, если он есть (для видео это важно)
                            final_mime_type = file_info.get('mime_type') or mime_type
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=base64_string,
                                file_size=file_size,
                                uploaded_by_id=executor.id,
                                mime_type=final_mime_type
                            )
                            # Отправляем файл в канал
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="MESSAGE",
                                uploaded_by=executor,
                                mime_type=final_mime_type
                            )
                            saved_count += 1
                        else:
                            # Если не удалось скачать, сохраняем только file_id
                            logger.warning(f"Не удалось скачать файл {file_info.get('file_name')}, сохраняем только file_id")
                            final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=executor.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                            saved_count += 1
                except Exception as e:
                    # В случае ошибки сохраняем только file_id
                    logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}, сохраняем только file_id")
                    try:
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=executor.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        saved_count += 1
                    except Exception as e2:
                        logger.error(f"Критическая ошибка при сохранении file_id: {e2}")
        
        # Отправляем файлы байеру в одном сообщении
        if task.creator:
            try:
                from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaVideo
                
                text_message = f"""
📎 <b>НОВЫЕ ФАЙЛЫ ПО ЗАДАЧЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
🛠️ <b>От исполнителя:</b> {executor.first_name} {executor.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Исполнитель прикрепил файлы к задаче ({len(files)} файлов).
"""
                
                # Отправляем файлы как media group
                media_group = []
                for idx, file_info in enumerate(files):
                    is_photo = file_info.get('is_photo', False)
                    is_video = file_info.get('is_video', False)
                    caption = text_message if idx == 0 else None
                    
                    if is_photo:
                        media_group.append(InputMediaPhoto(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                    elif is_video:
                        media_group.append(InputMediaVideo(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                    else:
                        media_group.append(InputMediaDocument(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                
                # Отправляем media group
                await bot.send_media_group(task.creator.telegram_id, media=media_group)
                        
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления байеру: {e}")
        
        await callback.message.edit_text(
            f"""
✅ <b>ФАЙЛЫ ЗАГРУЖЕНЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 Загружено файлов: {saved_count}
📋 Задача: {task.task_number}

Файлы отправлены байеру.
""",
            parse_mode="HTML"
        )
        
        # Возвращаем исполнителя к экрану управления задачей
        messages = await MessageQueries.get_task_messages(session, task_id)
        task_view_text = format_task_management_text(task, messages)
        
        can_reject = await _can_executor_reject_task(session, task_id, callback.from_user.id)
        
        await callback.message.answer(
            task_view_text,
            reply_markup=ExecutorKeyboards.task_management(task_id, task.status, can_reject=can_reject),
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Исполнитель {executor.telegram_id} добавил {saved_count} файлов к задаче {task.task_number}")
    
    await callback.answer("Файлы загружены!")


@router.message(F.text == "📊 Моя статистика")
async def executor_statistics(message: Message):
    """Статистика исполнителя"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.EXECUTOR:
            return
        
        tasks = await TaskQueries.get_available_tasks_for_executor(session, user.id)
        
        total = len(tasks)
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        completed = len([t for t in tasks if t.status == TaskStatus.APPROVED])
        
        text = f"""
📊 <b>МОЯ СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Всего задач:</b> {total}
🟡 <b>В работе:</b> {in_progress}
✅ <b>Завершено:</b> {completed}
📈 <b>Текущая загрузка:</b> {user.current_load} задач

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await message.answer(text, parse_mode="HTML")


"""Обработчики для байера"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import re
from aiogram.filters import or_f
from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries, MessageQueries, FileQueries, LogQueries, ChatRequestQueries
from db.models import UserRole, DirectionType, TaskStatus, TaskPriority, FileType
from bot.keyboards.buyer_kb import BuyerKeyboards
from bot.keyboards.common_kb import CommonKeyboards
from states.buyer_states import BuyerStates
from bot.utils.file_handler import FileHandler
from bot.utils.photo_handler import PhotoHandler
from bot.utils.log_channel import LogChannel
from bot.utils.message_utils import (
    truncate_description_in_preview, 
    truncate_text_if_needed, 
    check_message_length,
    get_max_description_length,
    TELEGRAM_MAX_MESSAGE_LENGTH
)
from bot.services.executor_status_service import ExecutorStatusService
from log import logger

# Импортируем обработчики файлов
from . import buyer_files
from . import buyer_profile
from . import buyer_chats

router = Router()

router.include_router(buyer_files.router)
router.include_router(buyer_profile.router)
router.include_router(buyer_chats.router)


# ============ СОЗДАНИЕ ЗАДАЧИ ============

@router.message(F.text == "➕ Создать задачу")
async def buyer_create_task(message: Message, state: FSMContext):
    """Начало создания задачи"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await message.answer("❌ У вас нет доступа к этой функции")
            return

        assigned_executors = await UserQueries.get_executors_for_buyer(session, user.id)
        # Отдельно получаем вообще всех закреплённых (даже если сейчас недоступны)
        all_assigned_executors = await UserQueries.get_all_assigned_executors_for_buyer(session, user.id)
        
        # Группируем по направлениям только назначенных исполнителей
        executors_by_direction: Dict[DirectionType, List] = {}
        for executor in assigned_executors:
            if executor.direction:
                if executor.direction not in executors_by_direction:
                    executors_by_direction[executor.direction] = []
                executors_by_direction[executor.direction].append(executor)
        
        if not executors_by_direction:
            # Если есть закреплённые, но среди них сейчас нет доступных — покажем их
            if all_assigned_executors:
                names_lines = []
                for ex in all_assigned_executors:
                    name = f"{ex.first_name or 'User'} {ex.last_name or ''}".strip()
                    names_lines.append(f"• {name}")
                names_text = "\n".join(names_lines)

                from aiogram.utils.keyboard import InlineKeyboardBuilder

                kb = InlineKeyboardBuilder()
                for ex in all_assigned_executors:
                    name = f"{ex.first_name or 'User'} {ex.last_name or ''}".strip()
                    kb.button(
                        text=f"👤 {name}",
                        callback_data=f"buyer_exec_profile_{ex.id}",
                    )
                kb.adjust(1)

                await message.answer(
                    "❌ <b>Нет доступных исполнителей</b>\n\n"
                    "Сейчас у вас нет <b>свободных</b> исполнителей для создания новой задачи.\n\n"
                    "<b>За вами закреплены исполнители:</b>\n"
                    f"{names_text}\n\n"
                    "Но в данный момент они уже заняты другими задачами.\n\n"
                    "Как только один из исполнителей освободится, вам придёт уведомление,\n"
                    "и вы сможете создать для него новую задачу.\n\n"
                    "Вы также можете открыть профиль исполнителя и посмотреть его задачи:",
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML"
                )
            else:
                # Вообще нет назначенных исполнителей
                await message.answer(
                    "❌ <b>Нет доступных исполнителей</b>\n\n"
                    "Сейчас у вас нет <b>назначенных</b> исполнителей.\n\n"
                    "Обратитесь к администратору, чтобы вам назначили исполнителей,\n"
                    "после чего вы сможете создавать для них задачи.",
                    parse_mode="HTML"
                )
            return

        await state.update_data(executors_by_direction=executors_by_direction)
        
        text = """
🎯 <b>СОЗДАНИЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 1/6: Выбор направления и исполнителя</b>

Выберите направление работы:
"""
        
        await message.answer(
            text,
            reply_markup=BuyerKeyboards.direction_with_executors(executors_by_direction),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_direction)
        logger.info(f"Байер {user.telegram_id} начал создание задачи")


@router.callback_query(F.data.startswith("buyer_direction_"), BuyerStates.waiting_direction)
async def process_direction_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора направления"""
    direction_value = callback.data.replace("buyer_direction_", "")
    direction = DirectionType(direction_value)
    
    data = await state.get_data()
    executors = data['executors_by_direction'].get(direction, [])
    
    if not executors:
        await callback.answer("❌ Нет исполнителей в этом направлении")
        return
    
    await state.update_data(direction=direction)
    
    direction_names = {
        DirectionType.DESIGN: "🎨 Дизайн",
        DirectionType.AGENCY: "🏢 Агенство",
        DirectionType.COPYWRITING: "✍️ Копирайтинг",
        DirectionType.MARKETING: "📱 Маркетинг"
    }
    
    async with AsyncSessionLocal() as session:
        # Получаем назначенных исполнителей для баера
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if buyer and buyer.role == UserRole.BUYER:
            # Получаем только назначенных исполнителей по направлению
            executors = await UserQueries.get_executors_for_buyer(session, buyer.id, direction=direction)
        else:
            # Если не баер (не должно произойти, но на всякий случай)
            executors = []
        
        task_id = data.get('edit_task_id')
        
        # Определяем текст в зависимости от контекста (создание или редактирование)
        if task_id:
            text = f"""
✅ <b>Направление выбрано: {direction_names.get(direction, direction.value)}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЯ</b>

Выберите исполнителя из списка:
"""
        else:
            text = f"""
✅ <b>Направление выбрано: {direction_names.get(direction, direction.value)}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 2/6: Выбор исполнителя</b>

Выберите исполнителя из списка:
"""
        
        # Если редактируем существующую задачу, передаем task_id для кнопки "Назад"
        is_editing = bool(task_id)
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.executor_list(executors, direction, is_editing=is_editing, task_id=task_id),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_executor)
    
    await callback.answer()


@router.callback_query(F.data == "buyer_show_all_executors", BuyerStates.waiting_direction)
async def show_all_executors(callback: CallbackQuery, state: FSMContext):
    """Показать всех назначенных исполнителей (без группировки по направлениям)"""
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    async with AsyncSessionLocal() as session:
        # Получаем только назначенных исполнителей для баера
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if buyer and buyer.role == UserRole.BUYER:
            active_executors = await UserQueries.get_executors_for_buyer(session, buyer.id)
        else:
            active_executors = []
        
        if not active_executors:
            await callback.answer("❌ Нет назначенных исполнителей", show_alert=True)
            return
        
        # Определяем текст в зависимости от контекста (создание или редактирование)
        if task_id:
            text = """
✅ <b>Назначенные исполнители</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЯ</b>

Выберите исполнителя из списка:
"""
        else:
            text = """
✅ <b>Назначенные исполнители</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 2/6: Выбор исполнителя</b>

Выберите исполнителя из списка:
"""
        
        # Если редактируем существующую задачу, используем клавиатуру с кнопкой "Назад" к задаче
        if task_id:
            await callback.message.edit_text(
                text,
                reply_markup=BuyerKeyboards.executor_list_all_with_back(active_executors, task_id),
                parse_mode="HTML"
            )
        else:
            # Показываем назначенных исполнителей в том же формате, что и при выборе категории
            await callback.message.edit_text(
                text,
                reply_markup=BuyerKeyboards.executor_list_all(active_executors),
                parse_mode="HTML"
            )
        await state.set_state(BuyerStates.waiting_executor)
    
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_reassign_executor_"))
async def reassign_executor_after_rejection(callback: CallbackQuery, state: FSMContext):
    """Переназначение исполнителя после отказа"""
    task_id = int(callback.data.replace("buyer_reassign_executor_", ""))

    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)

        if not task:
            await callback.answer("❌ Задача не найдена")
            return

        # Переназначать имеет смысл только задачу в ожидании
        if task.status != TaskStatus.PENDING:
            await callback.answer("❌ Переназначить исполнителя можно только для задач в статусе 'Ожидает'", show_alert=True)
            return

        direction = task.direction
        
        # Получаем только назначенных исполнителей для баера
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if buyer and buyer.role == UserRole.BUYER:
            executors = await UserQueries.get_executors_for_buyer(session, buyer.id, direction=direction)
        else:
            executors = []

        if not executors:
            await callback.answer("❌ Нет исполнителей в этом направлении", show_alert=True)
            return

        # Сохраняем id задачи для редактирования и переводим в состояние выбора исполнителя
        await state.update_data(edit_task_id=task_id)

        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }

        text = f"""
👤 <b>НАЗНАЧЕНИЕ ДРУГОГО ИСПОЛНИТЕЛЯ</b>

Направление: {direction_names.get(direction, direction.value)}

Выберите нового исполнителя для этой задачи:
"""

        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.executor_list(executors, direction, is_editing=True, task_id=task_id),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_executor)

    await callback.answer()


@router.callback_query(F.data == "buyer_back_to_directions", BuyerStates.waiting_executor)
async def back_to_directions(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору направления"""
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    # Возвращаемся к выбору направления (для создания или редактирования)
    async with AsyncSessionLocal() as session:
        executors_by_direction = data.get('executors_by_direction', {})
        
        # Если данных нет в state, загружаем заново
        if not executors_by_direction:
            buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
            if buyer and buyer.role == UserRole.BUYER:
                # Получаем назначенных исполнителей
                assigned_executors = await UserQueries.get_executors_for_buyer(session, buyer.id)
                # Группируем по направлениям
                executors_by_direction = {}
                for executor in assigned_executors:
                    if executor.direction:
                        if executor.direction not in executors_by_direction:
                            executors_by_direction[executor.direction] = []
                        executors_by_direction[executor.direction].append(executor)
            else:
                executors_by_direction = {}
            await state.update_data(executors_by_direction=executors_by_direction)
        
        # Определяем текст и клавиатуру в зависимости от контекста
        if task_id:
            text = """
👤 <b>ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите направление работы:
"""
            await callback.message.edit_text(
                text,
                reply_markup=BuyerKeyboards.direction_with_executors_with_back(executors_by_direction, task_id),
                parse_mode="HTML"
            )
        else:
            text = """
🎯 <b>СОЗДАНИЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 1/6: Выбор направления и исполнителя</b>

Выберите направление работы:
"""
            await callback.message.edit_text(
                text,
                reply_markup=BuyerKeyboards.direction_with_executors(executors_by_direction),
                parse_mode="HTML"
            )
        await state.set_state(BuyerStates.waiting_direction)
    
    await callback.answer("Возврат к выбору направления")


@router.callback_query(F.data.startswith("buyer_select_executor_"), BuyerStates.waiting_executor)
async def process_executor_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора исполнителя (для создания или редактирования)"""
    executor_id = int(callback.data.replace("buyer_select_executor_", ""))
    
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if task_id:
        # Редактирование существующей задачи
        async with AsyncSessionLocal() as session:
            executor = await UserQueries.get_user_by_id(session, executor_id)
            task = await TaskQueries.get_task_by_id(session, task_id)
            
            if not executor or not task:
                await callback.answer("❌ Ошибка: исполнитель или задача не найдены")
                return
            
            # Обновляем исполнителя
            await TaskQueries.assign_executor(session, task_id, executor_id)
            
            # Возвращаемся к просмотру задачи
            await show_task_view_from_callback(callback, task_id)
        
        await state.clear()
        await callback.answer("Исполнитель обновлен")
    else:
        # Создание новой задачи
        async with AsyncSessionLocal() as session:
            buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
            executor = await UserQueries.get_user_by_id(session, executor_id)

            if not executor or not buyer:
                await callback.answer("❌ Исполнитель не найден")
                return

            # Проверяем, не занят ли исполнитель
            # Исполнитель считается занятым только если он недоступен (is_available=False)
            # и у него есть задачи в работе
            is_busy = await ExecutorStatusService.is_executor_busy(session, executor_id)
            if is_busy:
                await callback.answer(
                    "⏳ Исполнитель занят и работает над другими задачами.\n\n"
                    "Новую задачу можно назначить только после завершения текущих.\n"
                    "Вы получите уведомление, когда исполнитель освободится.",
                    show_alert=True,
                )
                return
            
            # Сохраняем направление исполнителя, если оно еще не было сохранено
            # (это происходит когда выбирают из списка всех исполнителей)
            if not data.get('direction') and executor.direction:
                await state.update_data(direction=executor.direction)
            
            await state.update_data(executor_id=executor_id, executor_name=f"{executor.first_name} {executor.last_name or ''}")
            
            text = f"""
✅ <b>Исполнитель выбран: {executor.first_name} {executor.last_name or ''}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 3/6: Название задачи</b>

Введите название задачи (до 200 символов):
"""
            
            await callback.message.edit_text(text, parse_mode="HTML")
            await state.set_state(BuyerStates.waiting_task_title)
        
        await callback.answer()






async def show_task_preview(message: Message, state: FSMContext, is_edit: bool = False):
    """Показать превью задачи перед созданием"""
    data = await state.get_data()
    
    direction_names = {
        DirectionType.DESIGN: "🎨 Дизайн",
        DirectionType.AGENCY: "🏢 Агенство",
        DirectionType.COPYWRITING: "✍️ Копирайтинг",
        DirectionType.MARKETING: "📱 Маркетинг"
    }
    
    priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
    
    deadline_str = data['deadline'].strftime("%d.%m.%Y %H:%M") if data.get('deadline') else "Не указан"
    
    # Формируем шаблон текста с плейсхолдером для описания
    text_template = f"""
📋 <b>ПРЕВЬЮ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Направление:</b> {direction_names.get(data['direction'], data['direction'].value)}
👤 <b>Исполнитель:</b> {data['executor_name']}

📌 <b>Название:</b> {data['title']}

📝 <b>Описание:</b>
{{description}}

📍 <b>Приоритет:</b> {priority_names[data['priority']-1]}
⏱️ <b>Дедлайн:</b> {deadline_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Задача будет отправлена исполнителю в ЛС бота
"""
    
    # Проверяем длину сообщения
    description = data.get('description', '')
    exceeds_limit, message_length = check_message_length(
        description=description,
        base_text_template=text_template,
        max_length=TELEGRAM_MAX_MESSAGE_LENGTH
    )
    
    if exceeds_limit:
        # Показываем предупреждение вместо превью
        max_desc_length = get_max_description_length(text_template, TELEGRAM_MAX_MESSAGE_LENGTH)
        warning_text = f"""
⚠️ <b>СООБЩЕНИЕ СЛИШКОМ ДЛИННОЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше описание задачи слишком длинное ({len(description)} символов).

Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов.

<b>Максимальная длина описания:</b> ~{max_desc_length} символов
<b>Текущая длина описания:</b> {len(description)} символов
<b>Превышение:</b> {message_length - TELEGRAM_MAX_MESSAGE_LENGTH} символов

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Пожалуйста, сократите описание задачи и попробуйте снова.</b>

Вы можете вернуться к редактированию описания, нажав кнопку ниже.
"""
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="✏️ Редактировать описание", callback_data="buyer_edit_task")
        builder.button(text="⬅️ Назад", callback_data="buyer_back_to_confirm")
        builder.adjust(1)
        
        if is_edit:
            await message.edit_text(
                warning_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                warning_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        
        logger.warning(f"Попытка создать задачу с слишком длинным описанием (длина: {len(description)}, сообщение: {message_length})")
        return  # Не переходим к подтверждению
    
    # Формируем финальный текст
    text = text_template.format(description=description)
    
    # Если это редактирование (вызов из callback), используем edit_text, иначе answer
    if is_edit:
        await message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_creation_confirm(data),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            text,
            reply_markup=BuyerKeyboards.task_creation_confirm(data),
            parse_mode="HTML"
        )
    
    await state.set_state(BuyerStates.waiting_task_confirmation)


@router.callback_query(F.data == "buyer_edit_task", BuyerStates.waiting_task_confirmation)
async def edit_task_before_create(callback: CallbackQuery, state: FSMContext):
    """Редактирование задачи перед созданием"""
    await callback.message.edit_text(
        "✏️ <b>РЕДАКТИРОВАНИЕ ЗАДАЧИ</b>\n\n"
        "Выберите поле для редактирования:",
        reply_markup=BuyerKeyboards.edit_task_field(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "buyer_back_to_confirm")
async def back_to_confirm(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Назад» из меню редактирования/подтверждения"""
    data = await state.get_data()
    task_id = data.get("edit_task_id")

    # Если редактируем существующую задачу — возвращаемся к её просмотру
    if task_id:
        await show_task_view_from_message(callback.message, task_id)
        await state.clear()
        await callback.answer("Возврат к задаче")
        return

    # Иначе возвращаемся к превью перед созданием
    await show_task_preview(callback.message, state, is_edit=True)
    await callback.answer("Возврат к превью")


@router.callback_query(F.data == "edit_field_title", BuyerStates.waiting_task_confirmation)
async def edit_field_title(callback: CallbackQuery, state: FSMContext):
    """Редактирование названия"""
    await callback.message.edit_text(
        "📌 <b>ИЗМЕНЕНИЕ НАЗВАНИЯ</b>\n\n"
        "Введите новое название задачи (до 200 символов):",
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_title)
    await callback.answer()


@router.callback_query(F.data == "edit_field_description", BuyerStates.waiting_task_confirmation)
async def edit_field_description(callback: CallbackQuery, state: FSMContext):
    """Редактирование описания"""
    # Вычисляем максимальную длину описания для превью
    data = await state.get_data()
    direction_names = {
        DirectionType.DESIGN: "🎨 Дизайн",
        DirectionType.AGENCY: "🏢 Агенство",
        DirectionType.COPYWRITING: "✍️ Копирайтинг",
        DirectionType.MARKETING: "📱 Маркетинг"
    }
    priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
    deadline_str = data.get('deadline').strftime("%d.%m.%Y %H:%M") if data.get('deadline') else "Не указан"
    
    preview_template_for_check = f"""
📋 <b>ПРЕВЬЮ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Направление:</b> {direction_names.get(data.get('direction'), '')}
👤 <b>Исполнитель:</b> {data.get('executor_name', '')}

📌 <b>Название:</b> {data.get('title', '')}

📝 <b>Описание:</b>
{{description}}

📍 <b>Приоритет:</b> {priority_names[data.get('priority', 1)-1]}
⏱️ <b>Дедлайн:</b> {deadline_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Задача будет отправлена исполнителю в ЛС бота
"""
    max_desc_length = get_max_description_length(preview_template_for_check, TELEGRAM_MAX_MESSAGE_LENGTH)
    
    await callback.message.edit_text(
        f"📝 <b>ИЗМЕНЕНИЕ ОПИСАНИЯ</b>\n\n"
        f"Введите новое описание задачи:\n\n"
        f"⚠️ <b>Ограничение:</b> Максимальная длина описания ~{max_desc_length} символов\n"
        f"(Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов)",
        parse_mode="HTML",
        reply_markup=CommonKeyboards.cancel()
    )
    await state.set_state(BuyerStates.waiting_task_description)
    await callback.answer()


@router.callback_query(F.data == "edit_field_deadline", BuyerStates.waiting_task_confirmation)
async def edit_field_deadline(callback: CallbackQuery, state: FSMContext):
    """Редактирование дедлайна"""
    text = """
⏱️ <b>ИЗМЕНЕНИЕ ДЕДЛАЙНА</b>

Введите дедлайн одним из способов:

📅 <b>Количество дней:</b>
• <code>3д</code> или <code>3 дня</code> - через 3 дня
• <code>7д</code> или <code>7 дней</code> - через неделю

⏰ <b>Количество часов:</b>
• <code>12ч</code> или <code>12 часов</code> - через 12 часов
• <code>48ч</code> или <code>48 часов</code> - через 48 часов

📆 <b>Или полная дата:</b>
• <code>25.12.2025 18:00</code>

Или нажмите "Пропустить" если дедлайн не требуется.
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=CommonKeyboards.skip_and_cancel(),
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_deadline)
    await callback.answer()


@router.callback_query(F.data == "edit_field_priority", BuyerStates.waiting_task_confirmation)
async def edit_field_priority(callback: CallbackQuery, state: FSMContext):
    """Редактирование приоритета"""
    await callback.message.edit_text(
        "📍 <b>ИЗМЕНЕНИЕ ПРИОРИТЕТА</b>\n\n"
        "Выберите новый приоритет:",
        reply_markup=CommonKeyboards.priority_selector(),
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_priority)
    await callback.answer()


@router.callback_query(F.data == "edit_field_executor", BuyerStates.waiting_task_confirmation)
async def edit_field_executor(callback: CallbackQuery, state: FSMContext):
    """Редактирование исполнителя"""
    data = await state.get_data()
    direction = data.get('direction')
    task_id = data.get('edit_task_id')
    
    if not direction:
        await callback.answer("❌ Ошибка: направление не выбрано")
        return
    
    async with AsyncSessionLocal() as session:
        executors = await UserQueries.get_executors_by_direction(session, direction)
        
        if not executors:
            await callback.answer("❌ Нет исполнителей в этом направлении")
            return
        
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        
        text = f"""
👤 <b>ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЯ</b>

Направление: {direction_names.get(direction, direction.value)}

Выберите нового исполнителя:
"""
        
        # Если редактируем существующую задачу, передаем task_id для кнопки "Назад"
        is_editing = bool(task_id)
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.executor_list(executors, direction, is_editing=is_editing, task_id=task_id),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_executor)
    
    await callback.answer()


@router.callback_query(F.data == "buyer_confirm_create", BuyerStates.waiting_task_confirmation)
async def confirm_create_task(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение создания задачи"""
    data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        executor = await UserQueries.get_user_by_id(session, data['executor_id'])
        
        # Создаем задачу
        task = await TaskQueries.create_task(
            session=session,
            title=data['title'],
            description=data['description'],
            direction=data['direction'],
            priority=data['priority'],
            created_by_id=buyer.id,
            executor_id=executor.id,
            deadline=data.get('deadline')
        )
        
        # Сохраняем файлы задачи в БД (если есть)
        initial_files = data.get('initial_files', [])
        if initial_files:
            for file_info in initial_files:
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
                                task_id=task.id,
                                file_type=FileType.INITIAL,
                                file_name=file_info['file_name'],
                                file_data=base64_string,
                                file_size=file_size,
                                uploaded_by_id=buyer.id,
                                mime_type=mime_type
                            )
                            # Отправляем файл в канал
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="INITIAL",
                                uploaded_by=buyer,
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
                                task_id=task.id,
                                file_type=FileType.INITIAL,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                            # Отправляем файл в канал
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="INITIAL",
                                uploaded_by=buyer,
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
                                    task_id=task.id,
                                    file_type=FileType.INITIAL,
                                    file_name=file_info['file_name'],
                                    file_data=base64_string,
                                    file_size=file_size,
                                    uploaded_by_id=buyer.id,
                                    mime_type=final_mime_type
                                )
                                # Отправляем файл в канал
                                await LogChannel.log_file_uploaded(
                                    bot=bot,
                                    task=task,
                                    file_id=file_info['file_id'],
                                    file_name=file_info['file_name'],
                                    file_type="INITIAL",
                                    uploaded_by=buyer,
                                    mime_type=final_mime_type
                                )
                            else:
                                # Если не удалось скачать, сохраняем только file_id
                                logger.warning(f"Не удалось скачать файл {file_info.get('file_name')}, сохраняем только file_id")
                                final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                                await FileQueries.create_file(
                                    session=session,
                                    task_id=task.id,
                                    file_type=FileType.INITIAL,
                                    file_name=file_info['file_name'],
                                    file_data=None,
                                    file_size=file_size_from_info,
                                    uploaded_by_id=buyer.id,
                                    mime_type=final_mime_type,
                                    telegram_file_id=file_info['file_id']
                                )
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}, сохраняем только file_id")
                        try:
                            final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                            await FileQueries.create_file(
                                session=session,
                                task_id=task.id,
                                file_type=FileType.INITIAL,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                        except Exception as e2:
                            logger.error(f"Критическая ошибка при сохранении file_id: {e2}")
        
        # Логируем действие
        await LogQueries.create_action_log(
            session=session,
            user_id=buyer.id,
            action_type="task_created",
            entity_type="task",
            entity_id=task.id,
            details={
                "task_number": task.task_number,
                "executor_id": executor.id
            }
        )
        
        # Отправляем уведомление исполнителю
        await send_new_task_notification(bot, task, buyer, executor)
        
        # Логируем в канал
        await LogChannel.log_task_created(bot, task, buyer, executor)
        
        # Подтверждение байеру
        await callback.message.edit_text(
            f"✅ <b>ЗАДАЧА СОЗДАНА</b>\n\n"
            f"📋 Номер задачи: <b>{task.task_number}</b>\n"
            f"👤 Исполнитель: {executor.first_name} {executor.last_name or ''}\n\n"
            f"Исполнитель получил уведомление в ЛС бота.",
            reply_markup=BuyerKeyboards.task_created_view(task.id),
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Создана задача {task.task_number} байером {buyer.telegram_id}")
    
    await callback.answer("Задача создана!")


async def send_new_task_notification(bot: Bot, task, buyer, executor):
    """Отправить уведомление о новой задаче исполнителю"""
    from bot.keyboards.executor_kb import ExecutorKeyboards
    from db.engine import AsyncSessionLocal
    from db.queries import TaskQueries
    
    priority_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
    priority_names = ["Низкий", "Средний", "Высокий", "Срочный"]
    
    deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
    
    text = f"""
🆕 <b>НОВАЯ ЗАДАЧА ОТ БАЙЕРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>{task.task_number}: {task.title}</b>

👤 <b>От:</b> {buyer.first_name} {buyer.last_name or ''}
⏱️ <b>Срок:</b> {deadline_str}
📍 <b>Приоритет:</b> {priority_emoji[task.priority]} {priority_names[task.priority-1]}

━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Описание:</b>
{task.description}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    try:
        async with AsyncSessionLocal() as session:
            # Проверяем, отказывался ли исполнитель уже от этой задачи
            has_rejected = await TaskQueries.has_executor_rejected(session, task.id, executor.id)

        await bot.send_message(
            executor.telegram_id,
            text,
            reply_markup=ExecutorKeyboards.new_task_notification(task.id, can_reject=not has_rejected),
            parse_mode="HTML"
        )
        logger.info(f"Отправлено уведомление о задаче {task.task_number} исполнителю {executor.telegram_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления исполнителю: {e}")


# ============ ПРОСМОТР ЗАДАЧ ============

@router.callback_query(F.data == "buyer_my_tasks")
async def callback_buyer_my_tasks(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку задач байера (оптимизировано)"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет без загрузки данных
        total_count = await TaskQueries.count_tasks_by_creator(session, user.id)
        
        if total_count == 0:
            await callback.message.edit_text("📋 У вас пока нет задач")
            await callback.answer()
            return
        
        # Загружаем только первую страницу (5 задач)
        page = 1
        per_page = 5
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id, page=page, per_page=per_page)
        
        text = f"📋 <b>МОИ ЗАДАЧИ</b>\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=total_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "buyer_tasks_on_review")
async def callback_buyer_tasks_on_review(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку задач на проверке (оптимизировано)"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет задач на проверке
        completed_count = await TaskQueries.count_tasks_by_creator(session, user.id, status=TaskStatus.COMPLETED)
        
        if completed_count == 0:
            await callback.message.edit_text(
                "📋 <b>ЗАДАЧИ НА ПРОВЕРКЕ</b>\n\n"
                "У вас нет задач на проверке.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Загружаем только первую страницу задач на проверке (5 задач)
        page = 1
        per_page = 5
        tasks_on_review = await TaskQueries.get_tasks_by_creator(
            session, user.id, status=TaskStatus.COMPLETED, page=page, per_page=per_page
        )
        
        text = f"""
📋 <b>ЗАДАЧИ НА ПРОВЕРКЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Задач на проверке: {completed_count}

Выберите задачу для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_list(tasks_on_review, page=page, per_page=per_page, total_count=completed_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_tasks_page_"))
async def callback_tasks_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация списка задач байера (оптимизировано - загружает только нужную страницу)"""
    page = int(callback.data.replace("buyer_tasks_page_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет без загрузки данных
        total_count = await TaskQueries.count_tasks_by_creator(session, user.id)
        
        if total_count == 0:
            await callback.answer("❌ Нет задач")
            return
        
        # Загружаем только запрошенную страницу (5 задач)
        per_page = 5
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id, page=page, per_page=per_page)
        
        if not tasks:
            await callback.answer("❌ Страница не найдена")
            return
        
        text = f"📋 <b>МОИ ЗАДАЧИ</b>\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_list(tasks, page=page, per_page=per_page, total_count=total_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_view_task_"))
async def callback_view_task(callback: CallbackQuery):
    """Просмотр задачи"""
    task_id = int(callback.data.replace("buyer_view_task_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        from bot.utils.time_tracker import get_execution_time_display
        
        status_emoji = {
            TaskStatus.PENDING: "⏳ Ожидает",
            TaskStatus.IN_PROGRESS: "🟡 В работе",
            TaskStatus.COMPLETED: "✅ Завершена",
            TaskStatus.APPROVED: "🎉 Одобрена",
            TaskStatus.REJECTED: "❌ Отклонена",
            TaskStatus.CANCELLED: "🚫 Отменена"
        }
        
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        executor_name = f"{task.executor.first_name} {task.executor.last_name or ''}" if task.executor else "Не назначен"
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        # Получаем время выполнения
        execution_time = get_execution_time_display(task)
        
        # Формируем шаблон с плейсхолдером для описания
        text_template = f"""
📋 <b>ЗАДАЧА {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Название:</b> {task.title}
🏷️ <b>Статус:</b> {status_emoji.get(task.status, task.status.value)}
📍 <b>Приоритет:</b> {priority_names[task.priority-1]}

👤 <b>Исполнитель:</b> {executor_name}
⏱️ <b>Дедлайн:</b> {deadline_str}

{execution_time}

📝 <b>Описание:</b>
{{description}}

📅 <b>Создана:</b> {task.created_at.strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Обрезаем описание, если сообщение слишком длинное
        description = task.description or "Без описания"
        text, was_truncated = truncate_description_in_preview(
            description=description,
            base_text_template=text_template,
            max_length=TELEGRAM_MAX_MESSAGE_LENGTH
        )
        
        if was_truncated:
            logger.warning(f"Описание задачи {task.task_number} было обрезано при показе (длина описания: {len(description)})")
        
        executor_id = task.executor.id if task.executor else None
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_actions(task_id, task.status, executor_id),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_approve_"))
async def callback_approve_task(callback: CallbackQuery, state: FSMContext):
    """Одобрение задачи"""
    task_id = int(callback.data.replace("buyer_approve_", ""))
    
    await state.update_data(task_id_for_rating=task_id)
    
    await callback.message.edit_text(
        "⭐️ <b>ОЦЕНКА РАБОТЫ</b>\n\n"
        "Пожалуйста, оцените работу исполнителя:",
        reply_markup=CommonKeyboards.rating_selector(),
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_rating)
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_request_correction_"))
async def callback_request_correction(callback: CallbackQuery, state: FSMContext):
    """Запрос правок к задаче"""
    task_id = int(callback.data.replace("buyer_request_correction_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        if task.status != TaskStatus.COMPLETED:
            await callback.answer("❌ Запросить правки можно только для завершенных задач", show_alert=True)
            return
        
        await state.update_data(correction_task_id=task_id)
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отменить", callback_data=f"buyer_view_task_{task_id}")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"""
✏️ <b>ЗАПРОС ПРАВОК</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Опишите, какие правки нужно внести.
Ваше сообщение будет отправлено исполнителю,
и задача вернется в статус "В работе".

Напишите описание необходимых правок:
""",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_correction_description)
    
    await callback.answer()


@router.message(BuyerStates.waiting_correction_description)
async def process_correction_description(message: Message, state: FSMContext, bot: Bot):
    """Обработка описания правок"""
    correction_text = message.text.strip()
    
    if not correction_text:
        await message.answer("❌ Пожалуйста, введите описание правок")
        return
    
    data = await state.get_data()
    task_id = data.get('correction_task_id')
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена")
            await state.clear()
            return
        
        # Возвращаем задачу в работу
        await TaskQueries.update_task_status(
            session, 
            task_id, 
            TaskStatus.IN_PROGRESS, 
            buyer.id, 
            f"Запрошены правки: {correction_text}"
        )
        
        # Сохраняем сообщение с правками
        await MessageQueries.create_message(
            session=session,
            task_id=task_id,
            sender_id=buyer.id,
            content=f"✏️ ЗАПРОС ПРАВОК:\n\n{correction_text}"
        )
        
        # Уведомляем исполнителя
        if task.executor:
            try:
                from bot.keyboards.executor_kb import ExecutorKeyboards
                
                await bot.send_message(
                    task.executor.telegram_id,
                    f"""
✏️ <b>ЗАПРОШЕНЫ ПРАВКИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}

👤 <b>От байера:</b> {buyer.first_name} {buyer.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Описание правок:</b>
{correction_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Пожалуйста, внесите исправления и отправьте работу снова.
Задача возвращена в статус "В работе".
""",
                    reply_markup=ExecutorKeyboards.task_management(task_id, task.status),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления исполнителю: {e}")
        
        # Логируем в канал
        await LogChannel.log_task_status_change(bot, task, TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS, buyer)
        
        await message.answer(
            "✅ <b>ПРАВКИ ЗАПРОШЕНЫ</b>\n\n"
            f"Задача {task.task_number} возвращена в работу.\n"
            "Исполнитель получил уведомление с описанием правок.",
            parse_mode="HTML"
        )
        
        # Показываем задачу
        await show_task_view_from_message(message, task_id)
        
        await state.clear()
        logger.info(f"Байер {buyer.telegram_id} запросил правки для задачи {task.task_number}")


@router.callback_query(F.data.startswith("buyer_discuss_"))
async def callback_discuss_task(callback: CallbackQuery, state: FSMContext):
    """Обсуждение задачи с исполнителем"""
    task_id = int(callback.data.replace("buyer_discuss_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        if not task.executor:
            await callback.answer("❌ Исполнитель не назначен", show_alert=True)
            return
        
        await state.update_data(
            message_task_id=task_id,
            message_executor_id=task.executor.id
        )
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="📎 Прикрепить файл", callback_data=f"buyer_attach_file_{task_id}")
        builder.button(text="❌ Отменить", callback_data=f"buyer_view_task_{task_id}")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"""
💬 <b>ОБСУЖДЕНИЕ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}
🛠️ <b>Исполнитель:</b> {task.executor.first_name} {task.executor.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Напишите сообщение для обсуждения задачи.
Ваше сообщение будет отправлено исполнителю
и добавлено в историю обсуждения.

Напишите ваше сообщение:
""",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_message_to_executor)
    
    await callback.answer()


@router.callback_query(F.data.startswith("rating_"), BuyerStates.waiting_task_rating)
async def process_rating(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка оценки"""
    rating = int(callback.data.replace("rating_", ""))
    data = await state.get_data()
    task_id = data['task_id_for_rating']
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        # Обновляем задачу
        task.rating = rating
        # Загрузка исполнителя уменьшится автоматически в update_task_status при смене статуса на APPROVED
        await TaskQueries.update_task_status(session, task_id, TaskStatus.APPROVED, buyer.id, f"Оценка: {rating}/5")
        
        # Логируем в канал
        await LogChannel.log_task_approved(bot, task, buyer, rating)
        
        # Уведомляем исполнителя
        if task.executor:
            try:
                await bot.send_message(
                    task.executor.telegram_id,
                    f"🎉 <b>ЗАДАЧА ОДОБРЕНА!</b>\n\n"
                    f"📋 Задача: {task.task_number}\n"
                    f"⭐️ Оценка: {'⭐️' * rating}\n\n"
                    f"Спасибо за отличную работу!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")
        
        await callback.message.edit_text(
            f"🎉 <b>ЗАДАЧА ОДОБРЕНА</b>\n\n"
            f"Задача {task.task_number} завершена\n"
            f"⭐️ Оценка: {'⭐️' * rating}\n\n"
            f"Исполнитель получил уведомление.",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Задача {task.task_number} одобрена с оценкой {rating}")
    
    await callback.answer("Задача одобрена!")


@router.message(F.text == "✅ На проверке")
async def buyer_tasks_on_review(message: Message, state: FSMContext):
    """Просмотр задач на проверке (оптимизировано)"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Быстрый подсчет задач на проверке
        completed_count = await TaskQueries.count_tasks_by_creator(session, user.id, status=TaskStatus.COMPLETED)
        
        if completed_count == 0:
            await message.answer(
                "📋 <b>ЗАДАЧИ НА ПРОВЕРКЕ</b>\n\n"
                "У вас нет задач на проверке.",
                parse_mode="HTML"
            )
            return
        
        # Загружаем только первую страницу задач на проверке (5 задач)
        page = 1
        per_page = 5
        tasks_on_review = await TaskQueries.get_tasks_by_creator(
            session, user.id, status=TaskStatus.COMPLETED, page=page, per_page=per_page
        )
        
        text = f"""
📋 <b>ЗАДАЧИ НА ПРОВЕРКЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Задач на проверке: {completed_count}

Выберите задачу для просмотра:
"""
        
        await message.answer(
            text,
            reply_markup=BuyerKeyboards.task_list(tasks_on_review, page=page, per_page=per_page, total_count=completed_count),
            parse_mode="HTML"
        )
        logger.info(f"Байер {user.telegram_id} просматривает задачи на проверке")


# Обработчик статистики перемещен в common.py для универсального роутинга по ролям
# @router.message(F.text == "📊 Статистика")
# async def buyer_statistics(message: Message):
#     """Статистика байера - главное меню"""
#     async with AsyncSessionLocal() as session:
#         user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
#         
#         if not user or user.role != UserRole.BUYER:
#             return
#         
#         await message.answer(
#             "📊 <b>СТАТИСТИКА</b>\n\nВыберите раздел:",
#             reply_markup=BuyerKeyboards.statistics_menu(),
#             parse_mode="HTML"
#         )


@router.callback_query(F.data == "buyer_stats_menu")
async def callback_buyer_stats_menu(callback: CallbackQuery):
    """Возврат в меню статистики"""
    await callback.message.edit_text(
        "📊 <b>СТАТИСТИКА</b>\n\nВыберите раздел:",
        reply_markup=BuyerKeyboards.statistics_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "buyer_stats_general")
async def callback_buyer_stats_general(callback: CallbackQuery):
    """Общая статистика байера"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа")
            return
        
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
        
        total = len(tasks)
        pending = len([t for t in tasks if t.status == TaskStatus.PENDING])
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        completed_review = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        approved = len([t for t in tasks if t.status == TaskStatus.APPROVED])
        cancelled = len([t for t in tasks if t.status == TaskStatus.CANCELLED])
        
        # Средний рейтинг
        rated_tasks = [t for t in tasks if t.rating is not None]
        avg_rating = sum(t.rating for t in rated_tasks) / len(rated_tasks) if rated_tasks else 0

        chat_done, chat_not_done = await ChatRequestQueries.count_by_sender(session, user.id)
        
        text = f"""
📊 <b>ОБЩАЯ СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Всего задач:</b> {total}

<b>По статусам:</b>
   ⏳ Ожидают: {pending}
   🟡 В работе: {in_progress}
   ✅ На проверке: {completed_review}
   🎉 Одобрено: {approved}
   🚫 Отменено: {cancelled}

⭐️ <b>Средний рейтинг работ:</b> {avg_rating:.1f}/5.0
   (оценено задач: {len(rated_tasks)})

💬 <b>Запросы в чатах:</b>
   ✅ Выполнение: {chat_done}
   ❌ Невыполнение: {chat_not_done}

<b>Процент завершения:</b>
   {round(approved / total * 100) if total > 0 else 0}%

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "buyer_stats_status")
async def callback_buyer_stats_status(callback: CallbackQuery):
    """Статистика по статусам задач"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа")
            return
        
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
        
        total = len(tasks)
        pending = len([t for t in tasks if t.status == TaskStatus.PENDING])
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        completed_review = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        approved = len([t for t in tasks if t.status == TaskStatus.APPROVED])
        rejected = len([t for t in tasks if t.status == TaskStatus.REJECTED])
        cancelled = len([t for t in tasks if t.status == TaskStatus.CANCELLED])
        
        # Процентное соотношение
        def percent(count):
            return round(count / total * 100) if total > 0 else 0
        
        text = f"""
📊 <b>СТАТИСТИКА ПО СТАТУСАМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Всего задач:</b> {total}

<b>Детальная статистика:</b>

⏳ <b>Ожидают:</b> {pending} ({percent(pending)}%)
   Задачи назначены, ожидают принятия

🟡 <b>В работе:</b> {in_progress} ({percent(in_progress)}%)
   Исполнители активно работают

✅ <b>На проверке:</b> {completed_review} ({percent(completed_review)}%)
   Ждут вашего одобрения

🎉 <b>Одобрено:</b> {approved} ({percent(approved)}%)
   Успешно завершенные задачи

❌ <b>Отклонено:</b> {rejected} ({percent(rejected)}%)
   Требуют доработки

🚫 <b>Отменено:</b> {cancelled} ({percent(cancelled)}%)
   Отмененные вами задачи

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "buyer_stats_directions")
async def callback_buyer_stats_directions(callback: CallbackQuery):
    """Статистика по направлениям"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа")
            return
        
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
        
        direction_emoji = {
            DirectionType.DESIGN: "🎨",
            DirectionType.AGENCY: "🏢",
            DirectionType.COPYWRITING: "✍️",
            DirectionType.MARKETING: "📱"
        }
        
        direction_names = {
            DirectionType.DESIGN: "Дизайн",
            DirectionType.AGENCY: "Агенство",
            DirectionType.COPYWRITING: "Копирайтинг",
            DirectionType.MARKETING: "Маркетинг"
        }
        
        text = f"""
📊 <b>СТАТИСТИКА ПО НАПРАВЛЕНИЯМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        for direction in DirectionType:
            emoji = direction_emoji.get(direction, "📁")
            name = direction_names.get(direction, direction.value)
            
            # Задачи по направлению
            dir_tasks = [t for t in tasks if t.direction == direction]
            total_dir = len(dir_tasks)
            
            if total_dir == 0:
                continue
            
            # В работе
            in_work = len([t for t in dir_tasks if t.status == TaskStatus.IN_PROGRESS])
            
            # Завершено
            completed = len([t for t in dir_tasks if t.status == TaskStatus.APPROVED])
            
            # Средний рейтинг
            rated = [t for t in dir_tasks if t.rating is not None]
            avg_rating = sum(t.rating for t in rated) / len(rated) if rated else 0
            
            text += f"{emoji} <b>{name}</b>\n"
            text += f"   📋 Задач всего: {total_dir}\n"
            text += f"   🟡 В работе: {in_work}\n"
            text += f"   ✅ Завершено: {completed}\n"
            text += f"   ⭐️ Средний рейтинг: {avg_rating:.1f}/5\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "buyer_stats_executors")
async def callback_buyer_stats_executors(callback: CallbackQuery):
    """Статистика по исполнителям"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа")
            return
        
        tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
        
        # Группируем задачи по исполнителям
        executor_stats = {}
        for task in tasks:
            if task.executor:
                exec_id = task.executor.id
                if exec_id not in executor_stats:
                    executor_stats[exec_id] = {
                        'name': f"{task.executor.first_name} {task.executor.last_name or ''}".strip(),
                        'total': 0,
                        'in_progress': 0,
                        'completed': 0,
                        'ratings': []
                    }
                
                executor_stats[exec_id]['total'] += 1
                
                if task.status == TaskStatus.IN_PROGRESS:
                    executor_stats[exec_id]['in_progress'] += 1
                elif task.status == TaskStatus.APPROVED:
                    executor_stats[exec_id]['completed'] += 1
                
                if task.rating:
                    executor_stats[exec_id]['ratings'].append(task.rating)
        
        if not executor_stats:
            text = """
📊 <b>СТАТИСТИКА ПО ИСПОЛНИТЕЛЯМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

У вас пока нет задач с назначенными исполнителями.

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            # Сортируем по количеству завершенных задач
            sorted_executors = sorted(
                executor_stats.items(),
                key=lambda x: x[1]['completed'],
                reverse=True
            )
            
            text = f"""
📊 <b>СТАТИСТИКА ПО ИСПОЛНИТЕЛЯМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 <b>Всего исполнителей:</b> {len(executor_stats)}

<b>Топ исполнителей:</b>

"""
            
            for idx, (exec_id, stats) in enumerate(sorted_executors[:10], 1):
                avg_rating = sum(stats['ratings']) / len(stats['ratings']) if stats['ratings'] else 0
                
                text += f"{idx}. 👤 <b>{stats['name']}</b>\n"
                text += f"   📋 Всего задач: {stats['total']}\n"
                text += f"   🟡 В работе: {stats['in_progress']}\n"
                text += f"   ✅ Завершено: {stats['completed']}\n"
                text += f"   ⭐️ Средний рейтинг: {avg_rating:.1f}/5\n\n"
            
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "buyer_stats_period")
async def callback_buyer_stats_period(callback: CallbackQuery):
    """Выбор периода для статистики"""
    await callback.message.edit_text(
        "📅 <b>СТАТИСТИКА ЗА ПЕРИОД</b>\n\n"
        "Выберите период:",
        reply_markup=BuyerKeyboards.period_selector(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_period_"))
async def callback_buyer_period_selected(callback: CallbackQuery):
    """Обработка выбора периода"""
    period = callback.data.replace("buyer_period_", "")
    
    # Определяем даты
    now = datetime.now(timezone.utc)
    period_names = {
        "today": ("Сегодня", now.replace(hour=0, minute=0, second=0, microsecond=0)),
        "week": ("Неделя", now - timedelta(days=7)),
        "month": ("Месяц", now - timedelta(days=30)),
        "quarter": ("Квартал", now - timedelta(days=90)),
        "year": ("Год", now - timedelta(days=365)),
        "all": ("Все время", datetime(2020, 1, 1, tzinfo=timezone.utc))
    }
    
    period_name, start_date = period_names.get(period, ("Неизвестно", now))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа")
            return
        
        # Все задачи байера
        all_tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
        
        # Задачи за период (созданные)
        created_tasks = [t for t in all_tasks if t.created_at >= start_date]
        created_count = len(created_tasks)
        
        # Задачи завершенные за период
        completed_tasks = [
            t for t in all_tasks 
            if t.status == TaskStatus.APPROVED and t.completed_at and t.completed_at >= start_date
        ]
        completed_count = len(completed_tasks)
        
        # Задачи в работе
        in_progress_count = len([t for t in created_tasks if t.status == TaskStatus.IN_PROGRESS])
        
        # Средний рейтинг за период
        rated_tasks = [t for t in completed_tasks if t.rating is not None]
        avg_rating = sum(t.rating for t in rated_tasks) / len(rated_tasks) if rated_tasks else 0

        chat_done, chat_not_done = await ChatRequestQueries.count_by_sender(session, user.id, start_date=start_date)
        
        text = f"""
📊 <b>СТАТИСТИКА: {period_name.upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 <b>Период:</b> с {start_date.strftime("%d.%m.%Y")}

📋 <b>Создано задач:</b> {created_count}
✅ <b>Завершено задач:</b> {completed_count}
🟡 <b>В работе:</b> {in_progress_count}

⭐️ <b>Средний рейтинг:</b> {avg_rating:.1f}/5.0
   (оценено: {len(rated_tasks)} задач)

💬 <b>Запросы в чатах:</b>
   ✅ Выполнение: {chat_done}
   ❌ Невыполнение: {chat_not_done}

<b>Процент завершения:</b>
   {round(completed_count / created_count * 100) if created_count > 0 else 0}%

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ============ КОММУНИКАЦИЯ ============

@router.callback_query(F.data.startswith("buyer_message_"))
async def callback_buyer_message(callback: CallbackQuery, state: FSMContext):
    """Ответ исполнителю"""
    payload = callback.data.replace("buyer_message_", "")
    task_part, _, executor_part = payload.partition(":")
    task_id = int(task_part)
    explicit_executor_id = int(executor_part) if executor_part else None
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        target_executor = None
        if explicit_executor_id:
            target_executor = await UserQueries.get_user_by_id(session, explicit_executor_id)
        
        if not target_executor:
            target_executor = task.executor
        
        if not target_executor:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        await state.update_data(
            message_task_id=task_id,
            message_executor_id=target_executor.id
        )
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="📎 Прикрепить файл", callback_data=f"buyer_attach_file_{task_id}")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"""
💭 <b>ОТВЕТ ИСПОЛНИТЕЛЮ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
🛠️ <b>Исполнитель:</b> {target_executor.first_name} {target_executor.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше сообщение будет отправлено исполнителю
и добавлено в историю обсуждения.

━━━━━━━━━━━━━━━━━━━━━━━━━━

Напишите ваш ответ или прикрепите файл:
""",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_message_to_executor)
        await callback.answer()


@router.message(BuyerStates.waiting_message_to_executor)
async def process_message_to_executor(message: Message, state: FSMContext, bot: Bot):
    """Обработка сообщения исполнителю"""
    # Если это файл, переключаемся в режим загрузки файлов
    if message.document or message.photo:
        data = await state.get_data()
        task_id = data.get('message_task_id')
        if task_id:
            # Инициализируем список файлов и переключаемся в состояние загрузки файлов
            await state.update_data(message_files=[])
            await state.set_state(BuyerStates.waiting_message_file)
            # Импортируем обработчик файлов динамически
            from bot.handlers.buyer_files import process_message_file
            await process_message_file(message, state)
        return
    
    if not message.text:
        await message.answer("❌ Пожалуйста, отправьте текстовое сообщение или файл")
        return
    
    content = message.text.strip()
    data = await state.get_data()
    task_id = data['message_task_id']
    target_executor_id = data.get('message_executor_id')
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена")
            await state.clear()
            return
        
        target_executor = None
        if target_executor_id:
            target_executor = await UserQueries.get_user_by_id(session, target_executor_id)
        else:
            target_executor = task.executor
        
        if not target_executor:
            await message.answer("❌ Нет доступного исполнителя для отправки сообщения", parse_mode="HTML")
            await state.clear()
            return
        
        # Сохраняем сообщение
        await MessageQueries.create_message(
            session=session,
            task_id=task_id,
            sender_id=buyer.id,
            content=content
        )
        
        # Отправляем исполнителю
        if target_executor:
            try:
                # Создаем клавиатуру с кнопками
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()

                # Кнопка ответить байеру
                builder.button(text="💬 Ответить", callback_data=f"executor_message_{task.id}")

                # Добавляем кнопки "Принять задачу" и "Отказаться" только если задача еще не принята
                if task.status == TaskStatus.PENDING:
                    builder.button(text="▶️ ПРИНЯТЬ ЗАДАЧУ", callback_data=f"executor_take_{task.id}")
                    builder.button(text="❌ ОТКАЗАТЬСЯ", callback_data=f"executor_reject_{task.id}")

                builder.adjust(1)

                status_emoji = {
                    TaskStatus.PENDING: "⏳ Ожидает",
                    TaskStatus.IN_PROGRESS: "🟡 В работе",
                    TaskStatus.COMPLETED: "✅ Завершена",
                    TaskStatus.APPROVED: "🎉 Одобрена",
                    TaskStatus.REJECTED: "❌ Отклонена",
                    TaskStatus.CANCELLED: "🚫 Отменена"
                }
                priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
                deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
                description_text = task.description or "Без описания"

                # Формируем шаблон сообщения с плейсхолдерами
                message_template = f"""
💬 <b>СООБЩЕНИЕ ОТ БАЙЕРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}
🏷️ <b>Статус:</b> {status_emoji.get(task.status, task.status.value)}
📍 <b>Приоритет:</b> {priority_names[task.priority-1]}
⏱️ <b>Дедлайн:</b> {deadline_str}

📝 <b>Описание:</b>
{{description}}

👤 <b>От:</b> {buyer.first_name} {buyer.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

{{content}}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                
                # Формируем полный текст с описанием и контентом
                full_text = message_template.format(description=description_text, content=content)
                
                # Обрезаем текст, если он слишком длинный
                final_text = truncate_text_if_needed(full_text, TELEGRAM_MAX_MESSAGE_LENGTH)
                
                if len(final_text) < len(full_text):
                    logger.warning(f"Сообщение байера было обрезано при отправке исполнителю (длина: {len(full_text)})")

                await bot.send_message(
                    target_executor.telegram_id,
                    final_text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения исполнителю: {e}")
        
        await message.answer(
            "✅ <b>Сообщение отправлено исполнителю</b>",
            parse_mode="HTML"
        )
        
        # Показываем задачу после отправки сообщения
        await show_task_view_from_message(message, task_id)
        
        await state.clear()
        logger.info(f"Байер {buyer.telegram_id} отправил сообщение по задаче {task.task_number}")


async def show_task_view_from_message(message: Message, task_id: int):
    """Показать задачу из обработчика сообщений"""
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена")
            return
        
        from bot.utils.time_tracker import get_execution_time_display
        
        status_emoji = {
            TaskStatus.PENDING: "⏳ Ожидает",
            TaskStatus.IN_PROGRESS: "🟡 В работе",
            TaskStatus.COMPLETED: "✅ Завершена",
            TaskStatus.APPROVED: "🎉 Одобрена",
            TaskStatus.REJECTED: "❌ Отклонена",
            TaskStatus.CANCELLED: "🚫 Отменена"
        }
        
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        executor_name = f"{task.executor.first_name} {task.executor.last_name or ''}" if task.executor else "Не назначен"
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        # Получаем время выполнения
        execution_time = get_execution_time_display(task)
        
        # Формируем шаблон с плейсхолдером для описания
        text_template = f"""
📋 <b>ЗАДАЧА {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Название:</b> {task.title}
🏷️ <b>Статус:</b> {status_emoji.get(task.status, task.status.value)}
📍 <b>Приоритет:</b> {priority_names[task.priority-1]}

👤 <b>Исполнитель:</b> {executor_name}
⏱️ <b>Дедлайн:</b> {deadline_str}

{execution_time}

📝 <b>Описание:</b>
{{description}}

📅 <b>Создана:</b> {task.created_at.strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Обрезаем описание, если сообщение слишком длинное
        description = task.description or "Без описания"
        text, was_truncated = truncate_description_in_preview(
            description=description,
            base_text_template=text_template,
            max_length=TELEGRAM_MAX_MESSAGE_LENGTH
        )
        
        if was_truncated:
            logger.warning(f"Описание задачи {task.task_number} было обрезано при показе (длина описания: {len(description)})")
        
        executor_id = task.executor.id if task.executor else None
        await message.answer(
            text,
            reply_markup=BuyerKeyboards.task_actions(task_id, task.status, executor_id),
            parse_mode="HTML"
        )


# ============ РЕДАКТИРОВАНИЕ ЗАДАЧИ ============

@router.callback_query(F.data.startswith("buyer_edit_task_"))
async def callback_edit_task(callback: CallbackQuery, state: FSMContext):
    """Редактирование существующей задачи"""
    task_id = int(callback.data.replace("buyer_edit_task_", ""))
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        # Проверяем, что задача в статусе PENDING (можно редактировать только ожидающие задачи)
        if task.status != TaskStatus.PENDING:
            await callback.answer("❌ Можно редактировать только задачи в статусе 'Ожидает'", show_alert=True)
            return
        
        # Сохраняем ID задачи для редактирования
        await state.update_data(edit_task_id=task_id)
        
        await callback.message.edit_text(
            "✏️ <b>РЕДАКТИРОВАНИЕ ЗАДАЧИ</b>\n\n"
            "Выберите поле для редактирования:",
            reply_markup=BuyerKeyboards.edit_task_field(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_edit_field)
    
    await callback.answer()


@router.callback_query(F.data == "edit_field_title", BuyerStates.waiting_edit_field)
async def edit_existing_task_title(callback: CallbackQuery, state: FSMContext):
    """Редактирование названия существующей задачи"""
    await callback.message.edit_text(
        "📌 <b>ИЗМЕНЕНИЕ НАЗВАНИЯ</b>\n\n"
        "Введите новое название задачи (до 200 символов):",
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_title)
    await callback.answer()


@router.callback_query(F.data == "edit_field_description", BuyerStates.waiting_edit_field)
async def edit_existing_task_description(callback: CallbackQuery, state: FSMContext):
    """Редактирование описания существующей задачи"""
    # Примерная максимальная длина описания для просмотра задачи
    template_length = 300
    max_desc_length = TELEGRAM_MAX_MESSAGE_LENGTH - template_length - 50
    
    await callback.message.edit_text(
        f"📝 <b>ИЗМЕНЕНИЕ ОПИСАНИЯ</b>\n\n"
        f"Введите новое описание задачи:\n\n"
        f"⚠️ <b>Ограничение:</b> Максимальная длина описания ~{max_desc_length} символов\n"
        f"(Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов)",
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_description)
    await callback.answer()


@router.callback_query(F.data == "edit_field_deadline", BuyerStates.waiting_edit_field)
async def edit_existing_task_deadline(callback: CallbackQuery, state: FSMContext):
    """Редактирование дедлайна существующей задачи"""
    text = """
⏱️ <b>ИЗМЕНЕНИЕ ДЕДЛАЙНА</b>

Введите дедлайн одним из способов:

📅 <b>Количество дней:</b>
• <code>3д</code> или <code>3 дня</code> - через 3 дня
• <code>7д</code> или <code>7 дней</code> - через неделю

⏰ <b>Количество часов:</b>
• <code>12ч</code> или <code>12 часов</code> - через 12 часов
• <code>48ч</code> или <code>48 часов</code> - через 48 часов

📆 <b>Или полная дата:</b>
• <code>25.12.2025 18:00</code>

Или нажмите "Пропустить" если дедлайн не требуется.
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=CommonKeyboards.skip_and_cancel(),
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_deadline)
    await callback.answer()


@router.callback_query(F.data == "edit_field_priority", BuyerStates.waiting_edit_field)
async def edit_existing_task_priority(callback: CallbackQuery, state: FSMContext):
    """Редактирование приоритета существующей задачи"""
    await callback.message.edit_text(
        "📍 <b>ИЗМЕНЕНИЕ ПРИОРИТЕТА</b>\n\n"
        "Выберите новый приоритет:",
        reply_markup=CommonKeyboards.priority_selector(),
        parse_mode="HTML"
    )
    await state.set_state(BuyerStates.waiting_task_priority)
    await callback.answer()


@router.callback_query(F.data == "edit_field_executor", BuyerStates.waiting_edit_field)
async def edit_existing_task_executor(callback: CallbackQuery, state: FSMContext):
    """Редактирование исполнителя существующей задачи"""
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if not task_id:
        await callback.answer("❌ Ошибка: задача не найдена")
        return
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        # Получаем исполнителей по направлениям (как при создании задачи)
        executors_by_direction: Dict[DirectionType, List] = {}
        for direction in DirectionType:
            executors = await UserQueries.get_executors_by_direction(session, direction)
            if executors:
                executors_by_direction[direction] = executors
        
        if not executors_by_direction:
            await callback.answer("❌ Нет доступных исполнителей")
            return
        
        # Сохраняем данные исполнителей в state
        await state.update_data(executors_by_direction=executors_by_direction)
        
        text = """
👤 <b>ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите направление работы или покажите всех исполнителей:
"""
        
        # Показываем интерфейс с направлениями, как при создании задачи
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.direction_with_executors_with_back(executors_by_direction, task_id),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_direction)
    
    await callback.answer()


# Обработка сохранения изменений при редактировании существующей задачи
@router.message(BuyerStates.waiting_task_title)
async def save_edited_task_title(message: Message, state: FSMContext):
    """Сохранение измененного названия задачи"""
    title = message.text.strip()
    
    if len(title) > 200:
        await message.answer(
            "❌ Название слишком длинное. Максимум 200 символов.\n"
            "Введите название еще раз:",
            reply_markup=CommonKeyboards.cancel()
        )
        return
    
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if task_id:
        # Редактирование существующей задачи
        async with AsyncSessionLocal() as session:
            task = await TaskQueries.get_task_by_id(session, task_id)
            if task:
                task.title = title
                await session.commit()
                
                await message.answer(
                    f"✅ <b>Название обновлено</b>\n\n"
                    f"Новое название: {title}",
                    parse_mode="HTML"
                )
                
                # Возвращаемся к просмотру задачи
                await show_task_view_from_message(message, task_id)
        
        await state.clear()
    else:
        # Создание новой задачи (существующая логика)
        await state.update_data(title=title)
        
        # Вычисляем максимальную длину описания для превью
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        deadline_str = data.get('deadline').strftime("%d.%m.%Y %H:%M") if data.get('deadline') else "Не указан"
        
        preview_template_for_check = f"""
📋 <b>ПРЕВЬЮ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Направление:</b> {direction_names.get(data.get('direction'), '')}
👤 <b>Исполнитель:</b> {data.get('executor_name', '')}

📌 <b>Название:</b> {data.get('title', '')}

📝 <b>Описание:</b>
{{description}}

📍 <b>Приоритет:</b> {priority_names[data.get('priority', 1)-1]}
⏱️ <b>Дедлайн:</b> {deadline_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Задача будет отправлена исполнителю в ЛС бота
"""
        max_desc_length = get_max_description_length(preview_template_for_check, TELEGRAM_MAX_MESSAGE_LENGTH)
        
        text = f"""
✅ <b>Название задачи принято</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 4/6: Описание задачи</b>

Введите подробное описание задачи:
• Что нужно сделать
• Требования к результату
• Дополнительные пожелания

⚠️ <b>Ограничение:</b> Максимальная длина описания ~{max_desc_length} символов
(Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов)
"""
        
        await message.answer(
            text,
            reply_markup=CommonKeyboards.cancel(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_task_description)


@router.message(BuyerStates.waiting_task_description)
async def save_edited_task_description(message: Message, state: FSMContext):
    """Сохранение измененного описания задачи"""
    description = message.text.strip()
    
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if task_id:
        # Редактирование существующей задачи
        # Проверяем длину описания для шаблона просмотра задачи
        # Примерный шаблон для проверки (без реальных данных задачи)
        preview_template = """
📋 <b>ЗАДАЧА {task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Название:</b> {title}
🏷️ <b>Статус:</b> {status}
📍 <b>Приоритет:</b> {priority}

👤 <b>Исполнитель:</b> {executor}
⏱️ <b>Дедлайн:</b> {deadline}

{execution_time}

📝 <b>Описание:</b>
{description}

📅 <b>Создана:</b> {created_at}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        # Примерная длина шаблона без описания (около 250-300 символов)
        template_length = 300
        max_desc_length = TELEGRAM_MAX_MESSAGE_LENGTH - template_length - 50  # Запас
        
        if len(description) > max_desc_length:
            warning_text = f"""
⚠️ <b>ОПИСАНИЕ СЛИШКОМ ДЛИННОЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше описание задачи слишком длинное ({len(description)} символов).

Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов.

<b>Максимальная длина описания:</b> ~{max_desc_length} символов
<b>Текущая длина описания:</b> {len(description)} символов
<b>Превышение:</b> {len(description) - max_desc_length} символов

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Пожалуйста, сократите описание и попробуйте снова.</b>
"""
            await message.answer(
                warning_text,
                reply_markup=CommonKeyboards.cancel(),
                parse_mode="HTML"
            )
            logger.warning(f"Попытка сохранить слишком длинное описание для задачи {task_id} (длина: {len(description)})")
            return
        
        async with AsyncSessionLocal() as session:
            task = await TaskQueries.get_task_by_id(session, task_id)
            if task:
                task.description = description
                await session.commit()
                
                await message.answer(
                    f"✅ <b>Описание обновлено</b>",
                    parse_mode="HTML"
                )
                
                # Возвращаемся к просмотру задачи
                await show_task_view_from_message(message, task_id)
        
        await state.clear()
    else:
        # Создание новой задачи - проверяем длину для превью
        # Формируем шаблон превью для проверки
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        deadline_str = data.get('deadline').strftime("%d.%m.%Y %H:%M") if data.get('deadline') else "Не указан"
        
        preview_template = f"""
📋 <b>ПРЕВЬЮ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Направление:</b> {direction_names.get(data.get('direction'), '')}
👤 <b>Исполнитель:</b> {data.get('executor_name', '')}

📌 <b>Название:</b> {data.get('title', '')}

📝 <b>Описание:</b>
{{description}}

📍 <b>Приоритет:</b> {priority_names[data.get('priority', 1)-1]}
⏱️ <b>Дедлайн:</b> {deadline_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Задача будет отправлена исполнителю в ЛС бота
"""
        
        # Проверяем длину
        exceeds_limit, message_length = check_message_length(
            description=description,
            base_text_template=preview_template,
            max_length=TELEGRAM_MAX_MESSAGE_LENGTH
        )
        
        if exceeds_limit:
            max_desc_length = get_max_description_length(preview_template, TELEGRAM_MAX_MESSAGE_LENGTH)
            warning_text = f"""
⚠️ <b>ОПИСАНИЕ СЛИШКОМ ДЛИННОЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Ваше описание задачи слишком длинное ({len(description)} символов).

Telegram не позволяет отправлять сообщения длиннее {TELEGRAM_MAX_MESSAGE_LENGTH} символов.

<b>Максимальная длина описания:</b> ~{max_desc_length} символов
<b>Текущая длина описания:</b> {len(description)} символов
<b>Превышение:</b> {message_length - TELEGRAM_MAX_MESSAGE_LENGTH} символов

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Пожалуйста, сократите описание и попробуйте снова.</b>
"""
            await message.answer(
                warning_text,
                reply_markup=CommonKeyboards.cancel(),
                parse_mode="HTML"
            )
            logger.warning(f"Попытка создать задачу с слишком длинным описанием (длина: {len(description)}, сообщение: {message_length})")
            return
        
        # Сохраняем описание
        await state.update_data(description=description)
        
        text = """
✅ <b>Описание принято</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 5/6: Приоритет задачи</b>

Выберите приоритет:
"""
        
        await message.answer(
            text,
            reply_markup=CommonKeyboards.priority_selector(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_task_priority)


@router.callback_query(F.data.startswith("priority_"), BuyerStates.waiting_task_priority)
async def save_edited_task_priority(callback: CallbackQuery, state: FSMContext):
    """Сохранение измененного приоритета задачи"""
    priority = int(callback.data.replace("priority_", ""))
    
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if task_id:
        # Редактирование существующей задачи
        async with AsyncSessionLocal() as session:
            task = await TaskQueries.get_task_by_id(session, task_id)
            if task:
                task.priority = priority
                await session.commit()
                
                # Возвращаемся к просмотру задачи
                await show_task_view_from_callback(callback, task_id)
        
        await state.clear()
        await callback.answer("Приоритет обновлен")
    else:
        # Создание новой задачи (существующая логика)
        await state.update_data(priority=priority)
        
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        text = f"""
✅ <b>Приоритет выбран: {priority_names[priority-1]}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 6/6: Дедлайн</b>

Введите дедлайн одним из способов:

📅 <b>Количество дней:</b>
• <code>3д</code> или <code>3 дня</code> - через 3 дня
• <code>7д</code> или <code>7 дней</code> - через неделю

⏰ <b>Количество часов:</b>
• <code>12ч</code> или <code>12 часов</code> - через 12 часов
• <code>48ч</code> или <code>48 часов</code> - через 48 часов

📆 <b>Или полная дата:</b>
• <code>25.12.2025 18:00</code>

Или нажмите "Пропустить" если дедлайн не требуется.
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=CommonKeyboards.skip_and_cancel(),
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_task_deadline)
        await callback.answer()


async def show_task_view_from_callback(callback: CallbackQuery, task_id: int):
    """Показать задачу из обработчика callback"""
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        from bot.utils.time_tracker import get_execution_time_display
        
        status_emoji = {
            TaskStatus.PENDING: "⏳ Ожидает",
            TaskStatus.IN_PROGRESS: "🟡 В работе",
            TaskStatus.COMPLETED: "✅ Завершена",
            TaskStatus.APPROVED: "🎉 Одобрена",
            TaskStatus.REJECTED: "❌ Отклонена",
            TaskStatus.CANCELLED: "🚫 Отменена"
        }
        
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        executor_name = f"{task.executor.first_name} {task.executor.last_name or ''}" if task.executor else "Не назначен"
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        # Получаем время выполнения
        execution_time = get_execution_time_display(task)
        
        text = f"""
📋 <b>ЗАДАЧА {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Название:</b> {task.title}
🏷️ <b>Статус:</b> {status_emoji.get(task.status, task.status.value)}
📍 <b>Приоритет:</b> {priority_names[task.priority-1]}

👤 <b>Исполнитель:</b> {executor_name}
⏱️ <b>Дедлайн:</b> {deadline_str}

{execution_time}

📝 <b>Описание:</b>
{task.description}

📅 <b>Создана:</b> {task.created_at.strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        executor_id = task.executor.id if task.executor else None
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_actions(task_id, task.status, executor_id),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "skip", BuyerStates.waiting_task_deadline)
async def skip_edited_deadline(callback: CallbackQuery, state: FSMContext):
    """Пропуск дедлайна при редактировании"""
    data = await state.get_data()
    task_id = data.get('edit_task_id')
    
    if task_id:
        # Редактирование существующей задачи
        async with AsyncSessionLocal() as session:
            task = await TaskQueries.get_task_by_id(session, task_id)
            if task:
                task.deadline = None
                await session.commit()
                
                # Возвращаемся к просмотру задачи
                await show_task_view_from_callback(callback, task_id)
        
        await state.clear()
        await callback.answer("Дедлайн удален")
    else:
        # Создание новой задачи (существующая логика)
        await state.update_data(deadline=None)
        await show_task_preview(callback.message, state)
        await callback.answer("Дедлайн пропущен")


@router.message(BuyerStates.waiting_task_deadline)
async def save_edited_task_deadline(message: Message, state: FSMContext):
    """Сохранение измененного дедлайна задачи"""
    text = message.text.strip().lower()
    deadline = None
    
    try:
        # Попытка 1: Проверяем формат с днями (3д, 3 дня, 3 день)
        days_match = re.match(r'^(\d+)\s*(?:д|дня|день|дней)$', text)
        if days_match:
            days = int(days_match.group(1))
            deadline = datetime.now(timezone.utc) + timedelta(days=days)
        
        # Попытка 2: Проверяем формат с часами (12ч, 12 часов, 12 час)
        if not deadline:
            hours_match = re.match(r'^(\d+)\s*(?:ч|час|часа|часов)$', text)
            if hours_match:
                hours = int(hours_match.group(1))
                deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
        
        # Попытка 3: Проверяем полный формат даты (ДД.ММ.ГГГГ ЧЧ:ММ)
        if not deadline:
            deadline = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
            
            if deadline < datetime.now(timezone.utc):
                await message.answer(
                    "❌ Дедлайн не может быть в прошлом!\n"
                    "Введите корректную дату:",
                    reply_markup=CommonKeyboards.skip_and_cancel()
                )
                return
        
        data = await state.get_data()
        task_id = data.get('edit_task_id')
        
        if task_id:
            # Редактирование существующей задачи
            async with AsyncSessionLocal() as session:
                task = await TaskQueries.get_task_by_id(session, task_id)
                if task:
                    task.deadline = deadline
                    await session.commit()
                    
                    deadline_str = deadline.strftime("%d.%m.%Y %H:%M")
                    await message.answer(
                        f"✅ <b>Дедлайн обновлен</b>\n\n"
                        f"Новый дедлайн: {deadline_str}",
                        parse_mode="HTML"
                    )
                    
                    # Возвращаемся к просмотру задачи
                    await show_task_view_from_message(message, task_id)
            
            await state.clear()
        else:
            # Создание новой задачи (существующая логика)
            if deadline:
                await state.update_data(deadline=deadline)
                await show_task_preview(message, state)
            else:
                raise ValueError("Неверный формат")
        
    except (ValueError, AttributeError):
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\n"
            "📅 <b>Примеры:</b>\n"
            "• <code>3д</code> или <code>3 дня</code>\n"
            "• <code>12ч</code> или <code>12 часов</code>\n"
            "• <code>25.12.2025 18:00</code>\n\n"
            "Попробуйте еще раз:",
            reply_markup=CommonKeyboards.skip_and_cancel(),
            parse_mode="HTML"
        )


# ============ ОТМЕНА ЗАДАЧИ ============

@router.callback_query(F.data.startswith("buyer_cancel_task_"))
async def callback_cancel_task(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отмена задачи"""
    task_id = int(callback.data.replace("buyer_cancel_task_", ""))
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        # Проверяем, что задача в статусе PENDING (можно отменять только ожидающие задачи)
        if task.status != TaskStatus.PENDING:
            await callback.answer("❌ Можно отменять только задачи в статусе 'Ожидает'", show_alert=True)
            return
        
        # Сохраняем данные задачи перед удалением
        task_number = task.task_number
        task_title = task.title
        executor_telegram_id = task.executor.telegram_id if task.executor else None
        
        # Уведомляем исполнителя, если он был назначен (до удаления задачи)
        if executor_telegram_id:
            try:
                await bot.send_message(
                    executor_telegram_id,
                    f"🚫 <b>ЗАДАЧА ОТМЕНЕНА</b>\n\n"
                    f"📋 Задача: {task_number}\n"
                    f"📌 {task_title}\n\n"
                    f"Байер отменил эту задачу. Задача была полностью удалена.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления исполнителю: {e}")
        
        # Логируем в канал перед удалением
        old_status = task.status
        await LogChannel.log_task_status_change(bot, task, old_status, TaskStatus.CANCELLED, buyer)
        
        # Полностью удаляем задачу со всей информацией
        await TaskQueries.cancel_task(session, task_id, buyer.id)
        
        # Обновляем сообщение
        await callback.message.edit_text(
            f"🚫 <b>ЗАДАЧА ОТМЕНЕНА</b>\n\n"
            f"📋 Задача: {task_number}\n"
            f"📌 {task_title}",
            parse_mode="HTML"
        )
        
        # Получаем обновленный список задач и отправляем
        tasks = await TaskQueries.get_tasks_by_creator(session, buyer.id)
        
        if tasks:
            text = f"📋 <b>МОИ ЗАДАЧИ</b>\n\n"
            await callback.message.answer(
                text,
                reply_markup=BuyerKeyboards.task_list(tasks),
                parse_mode="HTML"
            )
        
        logger.info(f"Байер {buyer.telegram_id} удалил задачу {task_number}")
    
    await callback.answer("Задача удалена")

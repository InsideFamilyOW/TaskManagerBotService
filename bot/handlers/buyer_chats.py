"""Чаты для баеров.

Функционал:
- Просмотр списка чатов, где есть бот
- Просмотр информации о чате
- Отправка сообщения в чат
- Отправка своей задачи в чат

Это аналог админского раздела "💬 Чаты", но с ограничениями по доступу:
- Баер может отправлять в чат только задачи, созданные им.
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries, LogQueries, ChatAccessQueries, ChatRequestQueries
from db.queries.chat_queries import ChatQueries
from db.models import UserRole, TaskStatus

from bot.keyboards.admin_kb import AdminKeyboards
from bot.keyboards.common_kb import CommonKeyboards
from states.buyer_states import BuyerStates
from bot.utils.message_utils import truncate_description_in_preview, TELEGRAM_MAX_MESSAGE_LENGTH
from log import logger


router = Router()


async def _render_chat_info(callback: CallbackQuery, chat):
    """Рендер информации о чате (переиспользуем админскую клавиатуру действий)"""
    status_emoji = "👑" if chat.bot_status == "administrator" else "👤"
    status_text = "Администратор" if chat.bot_status == "administrator" else "Участник"

    chat_type_names = {
        "group": "Группа",
        "supergroup": "Супергруппа",
        "channel": "Канал",
    }
    chat_type_name = chat_type_names.get(chat.chat_type, chat.chat_type)

    text = f"""
💬 <b>ИНФОРМАЦИЯ О ЧАТЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Название:</b> {chat.chat_title or 'Не указано'}
🆔 <b>Chat ID:</b> <code>{chat.chat_id}</code>
📋 <b>Тип:</b> {chat_type_name}
{status_emoji} <b>Статус бота:</b> {status_text}
"""

    text += f"\n📅 <b>Добавлен:</b> {chat.created_at.strftime('%d.%m.%Y %H:%M') if chat.created_at else 'Неизвестно'}"

    await callback.message.edit_text(
        text,
        reply_markup=AdminKeyboards.chat_actions(chat.id, include_delete=False),
        parse_mode="HTML",
    )


async def _get_open_tasks_for_buyer(session, buyer_id: int, page: int = 1, per_page: int = 10):
    """Получить открытые задачи баера (PENDING/IN_PROGRESS) с пагинацией."""
    from sqlalchemy import select, func as sql_func
    from db.models import Task

    open_statuses = [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]

    total_count_result = await session.execute(
        select(sql_func.count(Task.id)).where(
            Task.created_by_id == buyer_id,
            Task.status.in_(open_statuses),
        )
    )
    total_count = total_count_result.scalar() or 0
    if total_count == 0:
        return [], 0

    query = (
        select(Task)
        .where(
            Task.created_by_id == buyer_id,
            Task.status.in_(open_statuses),
        )
        .order_by(Task.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(query)
    tasks = result.scalars().all()
    return tasks, total_count


# ============ ЧАТЫ (BAUYER) ============


@router.message(F.text == "💬 Чаты")
async def buyer_chats_menu(message: Message):
    """Меню чатов для баера."""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)

        if not user or user.role != UserRole.BUYER:
            return

        total_count = await ChatAccessQueries.count_accessible_chats(session, user.id)
        if total_count == 0:
            await message.answer(
                "💬 <b>ЧАТЫ</b>\n\n"
                "📋 Нет доступных чатов.\n\n"
                "Обратитесь к администратору для выдачи доступа к нужному чату.",
                parse_mode="HTML",
            )
            return

        page = 1
        per_page = 8
        chats = await ChatAccessQueries.get_accessible_chats(session, user.id, page=page, per_page=per_page)

        text = "💬 <b>ЧАТЫ</b>\n\n📊 Выберите чат из списка:\n\n"
        await message.answer(
            text,
            reply_markup=AdminKeyboards.chat_list(
                chats,
                page=page,
                per_page=per_page,
                total_count=total_count,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "admin_chats_list")
async def buyer_callback_chats_list(callback: CallbackQuery):
    """Список чатов (callback) для баера."""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        total_count = await ChatAccessQueries.count_accessible_chats(session, user.id)
        if total_count == 0:
            await callback.message.edit_text(
                "💬 <b>ЧАТЫ</b>\n\n"
                "📋 Нет доступных чатов.\n\n"
                "Обратитесь к администратору для выдачи доступа к нужному чату.",
                parse_mode="HTML",
            )
            await callback.answer()
            return

        page = 1
        per_page = 8
        chats = await ChatAccessQueries.get_accessible_chats(session, user.id, page=page, per_page=per_page)

        text = "💬 <b>ЧАТЫ</b>\n\n📊 Выберите чат из списка:\n\n"
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.chat_list(
                chats,
                page=page,
                per_page=per_page,
                total_count=total_count,
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_chats_page_"))
async def buyer_callback_chats_page(callback: CallbackQuery):
    """Навигация по страницам чатов (для баера)."""
    page = int(callback.data.replace("admin_chats_page_", ""))
    per_page = 8

    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        total_count = await ChatAccessQueries.count_accessible_chats(session, user.id)
        if total_count == 0:
            await callback.message.edit_text(
                "💬 <b>ЧАТЫ</b>\n\n"
                "📋 Нет доступных чатов.",
                parse_mode="HTML",
            )
            await callback.answer()
            return

        chats = await ChatAccessQueries.get_accessible_chats(session, user.id, page=page, per_page=per_page)
        text = "💬 <b>ЧАТЫ</b>\n\n📊 Выберите чат из списка:\n\n"
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.chat_list(
                chats,
                page=page,
                per_page=per_page,
                total_count=total_count,
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_chat_"))
async def buyer_callback_view_chat(callback: CallbackQuery, state: FSMContext):
    """Просмотр информации о чате (для баера)."""
    chat_db_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        if not await ChatAccessQueries.has_access(session, user.id, chat_db_id):
            await callback.answer("❌ У вас нет доступа к этому чату", show_alert=True)
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        if not chat:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return

        # сохраняем chat_db_id в стейт, чтобы потом можно было вернуться
        await state.update_data(chat_db_id=chat_db_id)
        await _render_chat_info(callback, chat)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_send_message_chat_"))
async def buyer_callback_send_message_chat(callback: CallbackQuery, state: FSMContext):
    """Начало отправки сообщения в чат (для баера)."""
    chat_db_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        if not await ChatAccessQueries.has_access(session, user.id, chat_db_id):
            await callback.answer("❌ У вас нет доступа к этому чату", show_alert=True)
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        if not chat:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return

        await state.update_data(chat_db_id=chat_db_id, chat_telegram_id=chat.chat_id)
        await state.set_state(BuyerStates.waiting_chat_message)

        await callback.message.edit_text(
            f"✍️ <b>ОТПРАВКА СООБЩЕНИЯ В ЧАТ</b>\n\n"
            f"📝 Чат: <b>{chat.chat_title or f'Chat {chat.chat_id}'}</b>\n\n"
            "Напишите сообщение, которое хотите отправить в этот чат:\n\n"
            "<i>Можно отправить текст, фото, видео, документ, аудио или voice.</i>",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(BuyerStates.waiting_chat_message)
async def buyer_process_chat_message(message: Message, state: FSMContext, bot: Bot):
    """Обработка сообщения для отправки в чат (для баера)."""
    data = await state.get_data()
    chat_telegram_id = data.get("chat_telegram_id")
    chat_db_id = data.get("chat_db_id")
    if not chat_telegram_id:
        await message.answer("❌ Ошибка: не найден ID чата")
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await message.answer("❌ У вас нет доступа", parse_mode="HTML")
            await state.clear()
            return

        if not chat_db_id:
            await message.answer("❌ Ошибка: не найден чат", parse_mode="HTML")
            await state.clear()
            return

        if not await ChatAccessQueries.has_access(session, user.id, chat_db_id):
            await message.answer("❌ У вас нет доступа к этому чату", parse_mode="HTML")
            await state.clear()
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        chat_title = chat.chat_title if chat else None

        def _preview(text: str | None) -> str | None:
            if not text:
                return None
            text = text.strip()
            if len(text) > 500:
                return text[:497] + "..."
            return text

        try:
            content_type = "unknown"
            content_preview = None

            if message.text:
                content_type = "text"
                content_preview = _preview(message.text)
            elif message.photo:
                content_type = "photo"
                content_preview = _preview(message.caption) or "Фото"
            elif message.video:
                content_type = "video"
                content_preview = _preview(message.caption) or "Видео"
            elif message.document:
                content_type = "document"
                content_preview = _preview(message.caption) or (message.document.file_name or "Документ")
            elif message.audio:
                content_type = "audio"
                content_preview = _preview(message.caption) or "Аудио"
            elif message.voice:
                content_type = "voice"
                content_preview = "Voice"
            else:
                await message.answer("❌ Неподдерживаемый тип сообщения", parse_mode="HTML")
                await state.clear()
                return

            chat_request = await ChatRequestQueries.create_request(
                session,
                chat_db_id=chat_db_id,
                chat_telegram_id=chat_telegram_id,
                chat_title=chat_title,
                sender_id=user.id,
                content_type=content_type,
                content_preview=content_preview,
            )

            keyboard = CommonKeyboards.chat_request_complete(chat_request.id)

            if message.text:
                sent = await bot.send_message(
                    chat_id=chat_telegram_id,
                    text=message.text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif message.photo:
                sent = await bot.send_photo(
                    chat_id=chat_telegram_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption or "",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif message.video:
                sent = await bot.send_video(
                    chat_id=chat_telegram_id,
                    video=message.video.file_id,
                    caption=message.caption or "",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif message.document:
                sent = await bot.send_document(
                    chat_id=chat_telegram_id,
                    document=message.document.file_id,
                    caption=message.caption or "",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif message.audio:
                sent = await bot.send_audio(
                    chat_id=chat_telegram_id,
                    audio=message.audio.file_id,
                    caption=message.caption or "",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif message.voice:
                sent = await bot.send_voice(
                    chat_id=chat_telegram_id,
                    voice=message.voice.file_id,
                    reply_markup=keyboard,
                )
            else:
                raise ValueError("Неподдерживаемый тип сообщения")

            chat_request.chat_message_id = sent.message_id
            await session.commit()

            await message.answer("✅ <b>Сообщение отправлено!</b>", parse_mode="HTML")
            logger.info(f"Баер {message.from_user.id} отправил запрос в чат {chat_telegram_id}")
        except Exception as e:
            await session.rollback()
            error_msg = str(e)
            await message.answer(f"❌ <b>Ошибка отправки</b>\n\n{error_msg}", parse_mode="HTML")
            logger.error(f"Ошибка при отправке сообщения в чат {chat_telegram_id}: {e}")
        finally:
            await state.clear()


@router.callback_query(F.data.startswith("admin_send_task_chat_"))
async def buyer_callback_send_task_chat(callback: CallbackQuery, state: FSMContext):
    """Начало процесса отправки задачи в чат (для баера)."""
    chat_db_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        if not await ChatAccessQueries.has_access(session, user.id, chat_db_id):
            await callback.answer("❌ У вас нет доступа к этому чату", show_alert=True)
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        if not chat:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return

        tasks, total_count = await _get_open_tasks_for_buyer(session, user.id, page=1, per_page=8)
        chat_title = chat.chat_title or f"Chat {chat.chat_id}"

        await state.update_data(
            chat_db_id=chat_db_id,
            chat_telegram_id=chat.chat_id,
            chat_title=chat_title,
        )
        await state.set_state(BuyerStates.waiting_chat_task_selection)

        text = f"""
📤 <b>ОТПРАВКА ЗАДАЧИ В ЧАТ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Чат:</b> {chat_title}
📊 <b>Открытых задач:</b> {total_count}

<b>Выберите задачу для отправки:</b>
"""
        if total_count == 0:
            text += "\nУ вас нет открытых задач (ожидают/в работе)."

        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.chat_task_list(
                tasks,
                page=1,
                per_page=8,
                total_count=total_count,
                back_text="◀️ Назад к чату",
                back_callback="admin_chat_task_back_to_chat",
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_chat_task_tasks_page_"),
    BuyerStates.waiting_chat_task_selection,
)
async def buyer_callback_chat_task_tasks_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация списка задач для отправки в чат (для баера)."""
    page = int(callback.data.replace("admin_chat_task_tasks_page_", ""))
    per_page = 8

    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        data = await state.get_data()
        chat_title = data.get("chat_title", "Чат")
        tasks, total_count = await _get_open_tasks_for_buyer(
            session,
            user.id,
            page=page,
            per_page=per_page,
        )

        text = f"""
📤 <b>ОТПРАВКА ЗАДАЧИ В ЧАТ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Чат:</b> {chat_title}
📊 <b>Открытых задач:</b> {total_count}

<b>Выберите задачу для отправки:</b>
"""
        if total_count == 0:
            text += "\nУ вас нет открытых задач (ожидают/в работе)."

        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.chat_task_list(
                tasks,
                page=page,
                per_page=per_page,
                total_count=total_count,
                back_text="◀️ Назад к чату",
                back_callback="admin_chat_task_back_to_chat",
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(
    F.data.startswith("admin_chat_task_select_"),
    BuyerStates.waiting_chat_task_selection,
)
async def buyer_callback_chat_task_select(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отправка выбранной задачи баера в чат."""
    task_id = int(callback.data.replace("admin_chat_task_select_", ""))
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        data = await state.get_data()
        chat_db_id = data.get("chat_db_id")
        chat_telegram_id = data.get("chat_telegram_id")
        if not chat_telegram_id or not chat_db_id:
            await callback.answer("❌ Не найден чат для отправки", show_alert=True)
            await state.clear()
            return

        task = await TaskQueries.get_task_by_id(session, task_id)
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return

        if task.created_by_id != user.id:
            await callback.answer("❌ Можно отправлять только свои задачи", show_alert=True)
            return

        open_statuses = {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}
        if task.status not in open_statuses:
            await callback.answer("❌ Задача уже закрыта/не актуальна", show_alert=True)
            return

        buyer_name = f"{task.creator.first_name} {task.creator.last_name or ''}".strip() if task.creator else "Баер"
        executor_name = f"{task.executor.first_name} {task.executor.last_name or ''}".strip() if task.executor else "Не назначен"
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"

        priority_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
        priority_names = ["Низкий", "Средний", "Высокий", "Срочный"]

        text_template = f"""
📣 <b>ЗАДАЧА В ЧАТ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>{task.task_number}: {task.title}</b>

👤 <b>Баер:</b> {buyer_name}
👷 <b>Исполнитель:</b> {executor_name}
⏱ <b>Срок:</b> {deadline_str}
📍 <b>Приоритет:</b> {priority_emoji.get(task.priority, '')} {priority_names[task.priority - 1]}

📝 <b>Описание:</b>
{{description}}

Нажмите кнопку ниже, когда задача будет выполнена.
"""

        description = task.description or "Без описания"
        text, was_truncated = truncate_description_in_preview(
            description=description,
            base_text_template=text_template,
            max_length=TELEGRAM_MAX_MESSAGE_LENGTH,
        )
        if was_truncated:
            logger.warning(f"Описание задачи {task.task_number} было обрезано при отправке в чат")

        try:
            await bot.send_message(
                chat_id=chat_telegram_id,
                text=text,
                reply_markup=CommonKeyboards.chat_task_complete(task.id),
                parse_mode="HTML",
            )
        except Exception as e:
            await callback.message.edit_text(
                f"❌ <b>Ошибка отправки</b>\n\n{e}",
                parse_mode="HTML",
            )
            logger.error(f"Ошибка при отправке задачи {task.task_number} в чат {chat_telegram_id}: {e}")
            await callback.answer()
            return

        try:
            await LogQueries.create_action_log(
                session=session,
                user_id=user.id,
                action_type="chat_task_sent",
                entity_type="task",
                entity_id=task.id,
                details={
                    "chat_id": chat_telegram_id,
                    "task_number": task.task_number,
                },
            )
        except Exception as e:
            logger.error(f"Не удалось записать лог отправки задачи {task.task_number}: {e}")

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        await state.clear()

        if chat:
            await _render_chat_info(callback, chat)
        else:
            await callback.message.edit_text("✅ <b>Задача отправлена в чат</b>", parse_mode="HTML")
    await callback.answer("✅ Задача отправлена")


@router.callback_query(F.data == "admin_chat_task_back_to_executors", BuyerStates.waiting_chat_task_selection)
async def buyer_callback_chat_task_back(callback: CallbackQuery, state: FSMContext):
    """Возврат из списка задач обратно к карточке чата (для баера)."""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        data = await state.get_data()
        chat_db_id = data.get("chat_db_id")
        if not chat_db_id:
            await callback.answer("❌ Чат не найден", show_alert=True)
            await state.clear()
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        await state.clear()
        if not chat:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return

        await _render_chat_info(callback, chat)
    await callback.answer()


@router.callback_query(F.data == "admin_chat_task_back_to_chat")
async def buyer_callback_chat_task_back_to_chat(callback: CallbackQuery, state: FSMContext):
    """Совместимость: кнопка '◀️ Назад к чату' (в нашем сценарии уже чат)."""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

        data = await state.get_data()
        chat_db_id = data.get("chat_db_id")
        if not chat_db_id:
            await callback.answer("❌ Чат не найден", show_alert=True)
            await state.clear()
            return

        chat = await ChatQueries.get_chat_by_db_id(session, chat_db_id)
        await state.clear()
        if not chat:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return

        await _render_chat_info(callback, chat)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_chat_"))
async def buyer_callback_delete_chat(callback: CallbackQuery):
    """Запрещаем баеру удалять чат из БД (кнопка есть в админской клавиатуре)."""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        if not user or user.role != UserRole.BUYER:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return

    await callback.answer("❌ У вас нет прав удалять чаты", show_alert=True)

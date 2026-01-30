"""Общие обработчики для всех пользователей"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries
from db.queries.chat_queries import ChatQueries
from db.queries.channel_queries import ChannelQueries
from db.models import UserRole, DirectionType, TaskStatus
from bot.keyboards.admin_kb import AdminKeyboards
from bot.keyboards.buyer_kb import BuyerKeyboards
from bot.keyboards.executor_kb import ExecutorKeyboards
from log import logger

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        # Если пользователя нет в БД - добавляем автоматически
        if not user:
            from Data.config import ADMIN_TG_ID
            
            # Определяем роль
            if message.from_user.id in ADMIN_TG_ID:
                # Администратор - сразу с ролью
                role = UserRole.ADMIN
                logger.info(f"Автоматическая регистрация администратора: {message.from_user.id}")
            else:
                # Обычный пользователь - без роли (будет назначена админом)
                role = None
                logger.info(f"Автоматическая регистрация пользователя: {message.from_user.id}")
            
            # Создаем пользователя
            user = await UserQueries.create_user(
                session=session,
                telegram_id=message.from_user.id,
                role=role,
                username=message.from_user.username,
                first_name=message.from_user.first_name or "User",
                last_name=message.from_user.last_name
            )
            
            # Если это админ
            if role == UserRole.ADMIN:
                await message.answer(
                    "🎉 <b>Добро пожаловать, администратор!</b>\n\n"
                    "Вы автоматически зарегистрированы в системе.\n"
                    "Ваша роль: 👑 Администратор",
                    parse_mode="HTML"
                )
                logger.info(f"Администратор {message.from_user.id} автоматически зарегистрирован")
            else:
                # Обычный пользователь без роли - создана заявка
                await message.answer(
                    "👋 <b>Привет!</b>\n\n"
                    "✅ Ваша заявка отправлена администратору!\n\n"
                    "⏳ Ожидайте назначения роли от администратора.\n\n"
                    f"📋 <b>Ваши данные:</b>\n"
                    f"• Имя: {user.first_name} {user.last_name or ''}\n"
                    f"• Username: @{user.username or 'не указан'}\n"
                    f"• Telegram ID: <code>{message.from_user.id}</code>\n\n"
                    "<i>Мы уведомили администраторов о вашей заявке.</i>",
                    parse_mode="HTML"
                )
                logger.info(f"Создана заявка от пользователя {message.from_user.id}")
                
                # Уведомляем всех администраторов о новой заявке
                from Data.config import ADMIN_TG_ID
                admins = await UserQueries.get_all_users(session, role=UserRole.ADMIN)
                
                from datetime import datetime
                notification_text = f"""
📝 <b>НОВАЯ ЗАЯВКА!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Пользователь:</b> {user.first_name} {user.last_name or ''}
📱 <b>Username:</b> @{user.username or 'не указан'}
🆔 <b>Telegram ID:</b> <code>{message.from_user.id}</code>
📅 <b>Дата заявки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Выберите действие:</b>
"""
                
                for admin in admins:
                    try:
                        await message.bot.send_message(
                            chat_id=admin.telegram_id,
                            text=notification_text,
                            parse_mode="HTML",
                            reply_markup=AdminKeyboards.quick_application_actions(user.id)
                        )
                    except Exception as e:
                        logger.error(f"Не удалось отправить уведомление админу {admin.telegram_id}: {e}")
                
                return
        
        # Проверяем, нужно ли обновить данные пользователя
        # (если имя начинается с "⏳" - это временное имя)
        if user.first_name and user.first_name.startswith("⏳"):
            # Обновляем данные из Telegram
            user.first_name = message.from_user.first_name or "User"
            user.last_name = message.from_user.last_name
            user.username = message.from_user.username
            await session.commit()
            logger.info(f"Обновлены данные пользователя {user.telegram_id}: {user.first_name} {user.last_name or ''}")
        
        # Если у пользователя нет роли - показываем сообщение ожидания
        if user.role is None:
            await message.answer(
                "⏳ <b>Ожидание назначения роли</b>\n\n"
                "Вы зарегистрированы, но роль еще не назначена.\n"
                "Обратитесь к администратору.\n\n"
                f"📋 <b>Ваш Telegram ID:</b> <code>{message.from_user.id}</code>",
                parse_mode="HTML"
            )
            return
        
        # Обновляем last_activity
        user.last_activity = func.now()
        await session.commit()
        
        # Приветственное сообщение в зависимости от роли
        role_messages = {
            UserRole.ADMIN: "👑 <b>Панель администратора</b>",
            UserRole.BUYER: "👔 <b>Панель байера</b>",
            UserRole.EXECUTOR: "🛠️ <b>Панель исполнителя</b>"
        }
        
        role_descriptions = {
            UserRole.ADMIN: "Вы можете управлять пользователями, просматривать статистику и настраивать систему.",
            UserRole.BUYER: "Вы можете создавать задачи, выбирать исполнителей и отслеживать выполнение.",
            UserRole.EXECUTOR: "Вы можете просматривать назначенные задачи и управлять их выполнением."
        }
        
        welcome_text = f"""
{role_messages.get(user.role, 'Панель пользователя')}
━━━━━━━━━━━━━━━━━━━━━━━━━━

👋 Добро пожаловать, {user.first_name}!

{role_descriptions.get(user.role, '')}

Используйте кнопки меню для работы с системой.
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем клавиатуру в зависимости от роли
        if user.role == UserRole.ADMIN:
            keyboard = AdminKeyboards.main_menu()
        elif user.role == UserRole.BUYER:
            keyboard = BuyerKeyboards.main_menu()
        elif user.role == UserRole.EXECUTOR:
            keyboard = ExecutorKeyboards.main_menu()
        else:
            keyboard = None
        
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"Пользователь {user.telegram_id} ({user.role.value}) вошел в систему")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user:
            return
        
        help_texts = {
            UserRole.ADMIN: """
<b>📚 Помощь администратору</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Управление пользователями:</b>
• Добавление новых пользователей
• Назначение ролей и прав
• Деактивация пользователей

<b>Статистика:</b>
• Общая статистика системы
• Статистика по пользователям
• Статистика по направлениям

<b>Настройки:</b>
• Настройка каналов логов
• Управление системой

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
            UserRole.BUYER: """
<b>📚 Помощь байеру</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Создание задачи:</b>
1. Выберите направление
2. Выберите исполнителя
3. Заполните данные задачи
4. Добавьте файлы (опционально)
5. Подтвердите создание

<b>Управление задачами:</b>
• Просмотр списка задач
• Отслеживание статусов
• Общение с исполнителями
• Проверка результатов

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
            UserRole.EXECUTOR: """
<b>📚 Помощь исполнителю</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Работа с задачами:</b>
• Принятие новых задач
• Выполнение задач
• Общение с байером
• Отправка результатов

<b>Действия:</b>
▶️ Взять в работу - принять задачу
✅ Выполнить - отправить результат
💬 Сообщение - написать байеру
❌ Отказаться - отклонить задачу

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        }
        
        help_text = help_texts.get(user.role, "Помощь недоступна")
        await message.answer(help_text, parse_mode="HTML")


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Действие отменено</b>\n\nИспользуйте /start для возврата в главное меню.",
        parse_mode="HTML"
    )
    await callback.answer("Отменено")
    logger.info(f"Пользователь {callback.from_user.id} отменил действие")


@router.callback_query(F.data == "back")
async def callback_back(callback: CallbackQuery, state: FSMContext):
    """Возврат назад"""
    await callback.answer("Возврат...")
    # Логика возврата будет реализована в конкретных обработчиках


@router.callback_query(F.data == "page_info")
async def callback_page_info(callback: CallbackQuery):
    """Информация о странице"""
    await callback.answer("Информация о текущей странице", show_alert=False)


@router.message(F.text == "🔄 Обновить")
async def refresh_data(message: Message):
    """Обновление данных"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user:
            return
        
        await message.answer("🔄 Данные обновлены!", show_alert=False)
        
        # Отправляем главное меню
        if user.role == UserRole.ADMIN:
            keyboard = AdminKeyboards.main_menu()
        elif user.role == UserRole.BUYER:
            keyboard = BuyerKeyboards.main_menu()
        elif user.role == UserRole.EXECUTOR:
            keyboard = ExecutorKeyboards.main_menu()
        else:
            return
        
        await message.answer("Выберите действие:", reply_markup=keyboard)


@router.message(F.text == "📋 Мои задачи")
async def my_tasks(message: Message, state: FSMContext):
    """Универсальный обработчик для моих задач"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        if user.role == UserRole.BUYER:
            # Задачи байера
            tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
            
            if not tasks:
                await message.answer("📋 У вас пока нет задач")
                return
            
            text = f"📋 <b>МОИ ЗАДАЧИ</b>\n\n"
            
            await message.answer(
                text,
                reply_markup=BuyerKeyboards.task_list(tasks),
                parse_mode="HTML"
            )
            
        elif user.role == UserRole.EXECUTOR:
            # Задачи исполнителя
            tasks = await TaskQueries.get_tasks_by_executor(session, user.id)
            
            if not tasks:
                await message.answer("📋 У вас пока нет задач")
                return
            
            # Фильтруем активные задачи
            active_tasks = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]]
            
            text = f"""
📋 <b>МОИ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Всего задач: {len(tasks)}
🟡 В работе: {len(active_tasks)}

Выберите задачу для просмотра:
"""
            
            await message.answer(
                text,
                reply_markup=ExecutorKeyboards.task_list(active_tasks if active_tasks else tasks),
                parse_mode="HTML"
            )
            
        elif user.role == UserRole.ADMIN:
            # Для админа показываем все задачи
            from sqlalchemy import select
            from db.models import Task
            
            result = await session.execute(select(Task).order_by(Task.created_at.desc()).limit(50))
            tasks = result.scalars().all()
            
            if not tasks:
                await message.answer("📋 В системе пока нет задач")
                return
            
            text = f"📋 <b>ВСЕ ЗАДАЧИ В СИСТЕМЕ</b>\n\nВсего задач: {len(tasks)}\n\n"
            
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ У вас нет доступа к этой функции")


@router.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message):
    """Просмотр своего профиля"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        # Определяем название роли
        role_names = {
            UserRole.ADMIN: "👑 Администратор",
            UserRole.BUYER: "👔 Байер",
            UserRole.EXECUTOR: "🛠️ Исполнитель"
        }
        
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        
        role_name = role_names.get(user.role, "Неизвестная роль")
        
        text = f"""
👤 <b>МОЙ ПРОФИЛЬ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Основная информация:</b>
• Имя: {user.first_name} {user.last_name or ''}
• Username: @{user.username or 'не указан'}
• Telegram ID: <code>{user.telegram_id}</code>
• Роль: {role_name}
"""
        
        # Дополнительная информация для исполнителя
        reply_markup = None

        if user.role == UserRole.EXECUTOR:
            direction_name = direction_names.get(user.direction, "Не указано") if user.direction else "Не указано"
            status = "✅ Активен" if user.is_active else "❌ Неактивен"
            availability = "🟢 Работаю (принимаю задачи)" if getattr(user, "is_available", True) else "🔴 Не работаю (не принимать задачи)"
            
            text += f"""
<b>Информация исполнителя:</b>
• Направление: {direction_name}
• Статус: {status}
• Статус приема задач: {availability}
• Текущая загрузка: {user.current_load} задач
• Завершено задач: {user.completed_tasks}
• Средняя оценка: {user.avg_rating:.2f}/5.00
"""

            # Под профилем исполнителя показываем кнопку-переключатель статуса
            from bot.keyboards.executor_kb import ExecutorKeyboards
            reply_markup = ExecutorKeyboards.profile_actions(getattr(user, "is_available", True))
        
        # Дополнительная информация для байера
        elif user.role == UserRole.BUYER:
            tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
            completed = len([t for t in tasks if t.status == TaskStatus.APPROVED])
            
            text += f"""
<b>Статистика байера:</b>
• Всего создано задач: {len(tasks)}
• Завершено: {completed}
"""
        
        text += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 Дата регистрации: {user.created_at.strftime("%d.%m.%Y")}
🕒 Последняя активность: {user.last_activity.strftime("%d.%m.%Y %H:%M") if user.last_activity else "Неизвестно"}
"""
        
        await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.message(F.text == "📊 Статистика")
async def statistics_menu(message: Message):
    """Универсальный обработчик статистики - роутинг по ролям"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        # Роутинг в зависимости от роли
        if user.role == UserRole.ADMIN:
            await message.answer(
                "📊 <b>СТАТИСТИКА</b>\n\nВыберите раздел:",
                reply_markup=AdminKeyboards.statistics_menu(),
                parse_mode="HTML"
            )
        elif user.role == UserRole.BUYER:
            await message.answer(
                "📊 <b>СТАТИСТИКА</b>\n\nВыберите раздел:",
                reply_markup=BuyerKeyboards.statistics_menu(),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ У вас нет доступа к этой функции")


@router.my_chat_member()
async def handle_my_chat_member(event: ChatMemberUpdated):
    """Обработка изменений статуса бота в чатах"""
    try:
        chat = event.chat
        new_status = event.new_chat_member.status
        old_status = event.old_chat_member.status if event.old_chat_member else None
        
        # Получаем информацию о чате
        chat_id = chat.id
        chat_type = chat.type
        chat_title = chat.title or chat.username or f"Chat {chat_id}"
        
        # Получаем права бота, если он администратор
        can_post_messages = False
        can_edit_messages = False
        can_delete_messages = False
        can_restrict_members = False
        can_promote_members = False
        can_change_info = False
        can_invite_users = False
        can_pin_messages = False
        can_manage_chat = False
        can_manage_video_chats = False
        
        if new_status == "administrator" and hasattr(event.new_chat_member, "can_post_messages"):
            can_post_messages = getattr(event.new_chat_member, "can_post_messages", False)
            can_edit_messages = getattr(event.new_chat_member, "can_edit_messages", False)
            can_delete_messages = getattr(event.new_chat_member, "can_delete_messages", False)
            can_restrict_members = getattr(event.new_chat_member, "can_restrict_members", False)
            can_promote_members = getattr(event.new_chat_member, "can_promote_members", False)
            can_change_info = getattr(event.new_chat_member, "can_change_info", False)
            can_invite_users = getattr(event.new_chat_member, "can_invite_users", False)
            can_pin_messages = getattr(event.new_chat_member, "can_pin_messages", False)
            can_manage_chat = getattr(event.new_chat_member, "can_manage_chat", False)
            can_manage_video_chats = getattr(event.new_chat_member, "can_manage_video_chats", False)
        
        async with AsyncSessionLocal() as session:
            # Если это канал, сохраняем в таблицу Channel
            if chat_type == "channel":
                # Сохраняем или обновляем канал в БД
                # Сохраняем только если бот добавлен как member или administrator
                if new_status in ["member", "administrator"]:
                    channel_obj = await ChannelQueries.add_or_update_channel(
                        session=session,
                        channel_id=chat_id,
                        channel_name=chat_title,
                        bot_status=new_status,
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
                    
                    if channel_obj:
                        logger.info(
                            f"Бот добавлен/обновлен в канал: {chat_title} (ID: {chat_id}, "
                            f"Статус: {new_status})"
                        )
                    else:
                        logger.error(f"Не удалось сохранить канал {chat_id} в БД")
                
                # Если бот удален из канала, обновляем статус
                elif new_status in ["left", "kicked"]:
                    await ChannelQueries.update_channel_status(session, chat_id, new_status)
                    logger.info(
                        f"Бот удален из канала: {chat_title} (ID: {chat_id}, Статус: {new_status})"
                    )
                
                # Если статус изменился (например, с member на administrator)
                elif old_status and old_status != new_status:
                    await ChannelQueries.add_or_update_channel(
                        session=session,
                        channel_id=chat_id,
                        channel_name=chat_title,
                        bot_status=new_status,
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
                    logger.info(
                        f"Статус бота изменен в канале {chat_title} (ID: {chat_id}): "
                        f"{old_status} → {new_status}"
                    )
            
            else:
                # Для групп и супергрупп сохраняем в таблицу Chat
                # Сохраняем только если бот добавлен как member или administrator
                if new_status in ["member", "administrator"]:
                    chat_obj = await ChatQueries.add_or_update_chat(
                        session=session,
                        chat_id=chat_id,
                        chat_type=chat_type,
                        chat_title=chat_title,
                        bot_status=new_status,
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
                    
                    if chat_obj:
                        logger.info(
                            f"Бот добавлен/обновлен в чат: {chat_title} (ID: {chat_id}, "
                            f"Тип: {chat_type}, Статус: {new_status})"
                        )
                    else:
                        logger.error(f"Не удалось сохранить чат {chat_id} в БД")
                
                # Если бот удален из чата, обновляем статус
                elif new_status in ["left", "kicked"]:
                    await ChatQueries.update_chat_status(session, chat_id, new_status)
                    logger.info(
                        f"Бот удален из чата: {chat_title} (ID: {chat_id}, Статус: {new_status})"
                    )
                
                # Если статус изменился (например, с member на administrator)
                elif old_status and old_status != new_status:
                    await ChatQueries.add_or_update_chat(
                        session=session,
                        chat_id=chat_id,
                        chat_type=chat_type,
                        chat_title=chat_title,
                        bot_status=new_status,
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
                    logger.info(
                        f"Статус бота изменен в чате {chat_title} (ID: {chat_id}): "
                        f"{old_status} → {new_status}"
                    )
    
    except Exception as e:
        logger.error(f"Ошибка при обработке my_chat_member: {e}")
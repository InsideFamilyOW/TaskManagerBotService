"""Обработчики для администратора"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries, LogQueries, FileQueries, MessageQueries
from db.models import UserRole, DirectionType, TaskStatus
from bot.keyboards.admin_kb import AdminKeyboards
from bot.keyboards.common_kb import CommonKeyboards
from states.admin_states import AdminStates
from bot.utils.log_channel import LogChannel
from log import logger

router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def notify_user_role_assigned(bot: Bot, user_telegram_id: int, role: UserRole, direction: DirectionType = None):
    """Отправляет уведомление пользователю о назначении роли"""
    try:
        role_emoji = {
            UserRole.ADMIN: "👑",
            UserRole.BUYER: "👔",
            UserRole.EXECUTOR: "🛠️"
        }
        
        role_names = {
            UserRole.ADMIN: "Администратор",
            UserRole.BUYER: "Байер",
            UserRole.EXECUTOR: "Исполнитель"
        }
        
        role_descriptions = {
            UserRole.ADMIN: "Вы можете управлять пользователями, просматривать статистику и настраивать систему.",
            UserRole.BUYER: "Вы можете создавать задачи, выбирать исполнителей и отслеживать выполнение.",
            UserRole.EXECUTOR: "Вы можете просматривать назначенные задачи и управлять их выполнением."
        }
        
        emoji = role_emoji.get(role, "👤")
        role_name = role_names.get(role, role.value)
        description = role_descriptions.get(role, "")
        
        notification_text = f"""
🎉 <b>ПОЗДРАВЛЯЕМ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{emoji} <b>Вам назначена роль: {role_name}</b>

{description}

Теперь вы можете пользоваться системой!
"""
        
        if direction:
            direction_names = {
                DirectionType.DESIGN: "🎨 Дизайн",
                DirectionType.AGENCY: "🏢 Агенство",
                DirectionType.COPYWRITING: "✍️ Копирайтинг",
                DirectionType.MARKETING: "📱 Маркетинг"
            }
            notification_text += f"\n📁 <b>Ваше направление:</b> {direction_names.get(direction, direction.value)}\n"
        
        notification_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        notification_text += "\n💡 <i>Используйте команду /start для начала работы</i>"
        
        await bot.send_message(
            chat_id=user_telegram_id,
            text=notification_text,
            parse_mode="HTML"
        )
        
        logger.info(f"Уведомление о назначении роли {role.value} отправлено пользователю {user_telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {user_telegram_id}: {e}")
        return False


# ============ ГЛАВНОЕ МЕНЮ ============

@router.message(F.text == "📝 Заявки")
async def admin_applications(message: Message):
    """Просмотр заявок (пользователей без роли)"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Получаем всех пользователей без роли
        from sqlalchemy import select
        from db.models import User
        
        result = await session.execute(
            select(User).where(User.role.is_(None)).order_by(User.created_at.desc())
        )
        applications = result.scalars().all()
        
        if not applications:
            await message.answer(
                "✅ <b>НЕТ НОВЫХ ЗАЯВОК</b>\n\n"
                "На данный момент нет пользователей, ожидающих назначения роли.",
                parse_mode="HTML"
            )
            return
        
        text = f"""
📝 <b>ЗАЯВКИ НА РЕГИСТРАЦИЮ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Всего заявок: {len(applications)}

Выберите заявку для просмотра:
"""
        
        await message.answer(
            text,
            reply_markup=AdminKeyboards.application_list(applications),
            parse_mode="HTML"
        )
        logger.info(f"Админ {user.telegram_id} открыл список заявок ({len(applications)} шт.)")


@router.callback_query(F.data == "admin_applications")
async def callback_applications(callback: CallbackQuery):
    """Обновление списка заявок"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        # Получаем всех пользователей без роли
        from sqlalchemy import select
        from db.models import User
        
        result = await session.execute(
            select(User).where(User.role.is_(None)).order_by(User.created_at.desc())
        )
        applications = result.scalars().all()
        
        if not applications:
            await callback.message.edit_text(
                "✅ <b>НЕТ НОВЫХ ЗАЯВОК</b>\n\n"
                "На данный момент нет пользователей, ожидающих назначения роли.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = f"""
📝 <b>ЗАЯВКИ НА РЕГИСТРАЦИЮ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Всего заявок: {len(applications)}

Выберите заявку для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.application_list(applications),
            parse_mode="HTML"
        )
        await callback.answer("🔄 Список обновлен")


@router.callback_query(F.data.startswith("admin_view_application_"))
async def callback_view_application(callback: CallbackQuery):
    """Просмотр заявки"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Если у пользователя уже есть роль
        if user.role is not None:
            await callback.answer("⚠️ Этой заявке уже назначена роль", show_alert=True)
            await callback_applications(callback)
            return
        
        text = f"""
📝 <b>ЗАЯВКА НА РЕГИСТРАЦИЮ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Имя:</b> {user.first_name or 'Не указано'} {user.last_name or ''}
📱 <b>Username:</b> @{user.username or 'не указан'}
🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>
📅 <b>Дата заявки:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}
🔘 <b>Статус:</b> {'✅ Активен' if user.is_active else '❌ Неактивен'}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите действие:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.application_actions(user.id),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_accept_application_"))
async def callback_accept_application(callback: CallbackQuery, state: FSMContext):
    """Принятие заявки - выбор роли"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        if user.role is not None:
            await callback.answer("⚠️ Этой заявке уже назначена роль", show_alert=True)
            return
        
        # Сохраняем ID пользователя и флаг что это заявка
        await state.update_data(
            edit_user_id=user_id,
            telegram_id=user.telegram_id,
            existing_user=True,
            is_application=True
        )
        
        text = f"""
✅ <b>ПРИНЯТИЕ ЗАЯВКИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Пользователь:</b> {user.first_name} {user.last_name or ''}
📱 <b>Username:</b> @{user.username or 'не указан'}
🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>
📅 <b>Дата заявки:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Выберите роль для пользователя:</b>
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.role_selector(),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_user_role)
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject_application_"))
async def callback_reject_application(callback: CallbackQuery):
    """Отклонение заявки"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Сохраняем информацию для уведомления
        user_telegram_id = user.telegram_id
        user_name = f"{user.first_name} {user.last_name or ''}"
        user_username = user.username
        
        # Удаляем пользователя
        success = await UserQueries.delete_user(session, user_id)
        
        if success:
            # Логируем
            await LogQueries.create_action_log(
                session=session,
                user_id=admin.id,
                action_type="application_rejected",
                entity_type="user",
                entity_id=None,
                details={
                    "telegram_id": user_telegram_id,
                    "name": user_name
                }
            )
            
            # Уведомляем пользователя об отклонении
            try:
                await callback.bot.send_message(
                    chat_id=user_telegram_id,
                    text="❌ <b>Ваша заявка отклонена</b>\n\n"
                         "К сожалению, администратор отклонил вашу заявку на регистрацию.\n"
                         "Для получения дополнительной информации свяжитесь с администратором.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {user_telegram_id}: {e}")
            
            await callback.message.edit_text(
                f"❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>Пользователь:</b> {user_name}\n"
                f"📱 <b>Username:</b> @{user_username or 'не указан'}\n"
                f"🆔 <b>Telegram ID:</b> <code>{user_telegram_id}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ Пользователь удален из базы данных\n"
                f"📨 Уведомление отправлено пользователю",
                parse_mode="HTML"
            )
            
            logger.info(f"Админ {admin.telegram_id} отклонил заявку от {user_telegram_id}")
            await callback.answer("✅ Заявка отклонена")
        else:
            await callback.message.edit_text("❌ Ошибка при отклонении заявки")
            await callback.answer("❌ Ошибка")


@router.message(F.text == "👥 Управление пользователями")
async def admin_user_management(message: Message):
    """Управление пользователями"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        text = """
👥 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите действие:
"""
        
        await message.answer(text, reply_markup=AdminKeyboards.user_management(), parse_mode="HTML")
        logger.info(f"Админ {user.telegram_id} открыл управление пользователями")


@router.callback_query(F.data == "admin_add_user")
async def callback_add_user(callback: CallbackQuery, state: FSMContext):
    """Начало добавления пользователя"""
    await callback.message.edit_text(
        "➕ <b>ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите Telegram ID нового пользователя:",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_telegram_id)
    await callback.answer()


@router.message(AdminStates.waiting_telegram_id)
async def process_telegram_id(message: Message, state: FSMContext):
    """Обработка Telegram ID"""
    try:
        telegram_id = int(message.text.strip())
        
        async with AsyncSessionLocal() as session:
            # Проверяем, не существует ли уже пользователь
            existing_user = await UserQueries.get_user_by_telegram_id(session, telegram_id)
            
            if existing_user and existing_user.role is not None:
                # Пользователь уже существует с ролью
                role_names = {
                    UserRole.ADMIN: "Администратор",
                    UserRole.BUYER: "Байер",
                    UserRole.EXECUTOR: "Исполнитель"
                }
                await message.answer(
                    f"❌ <b>Пользователь уже зарегистрирован!</b>\n\n"
                    f"👤 Имя: {existing_user.first_name} {existing_user.last_name or ''}\n"
                    f"🎭 Роль: {role_names.get(existing_user.role, 'Неизвестно')}\n\n"
                    f"Используйте функцию редактирования для изменения роли.",
                    reply_markup=CommonKeyboards.cancel(),
                    parse_mode="HTML"
                )
                await state.clear()
                return
            
            # Сохраняем информацию о существующем пользователе
            await state.update_data(
                telegram_id=telegram_id,
                existing_user=existing_user is not None,
                user_name=f"{existing_user.first_name} {existing_user.last_name or ''}" if existing_user else None
            )
            
            # Запрашиваем роль
            if existing_user:
                await message.answer(
                    f"✅ <b>Пользователь найден в базе!</b>\n\n"
                    f"👤 Имя: {existing_user.first_name} {existing_user.last_name or ''}\n"
                    f"🆔 ID: <code>{telegram_id}</code>\n\n"
                    f"Выберите роль для назначения:",
                    reply_markup=AdminKeyboards.role_selector(),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    "✅ Telegram ID принят\n\n"
                    "Теперь выберите роль пользователя:",
                    reply_markup=AdminKeyboards.role_selector(),
                    parse_mode="HTML"
                )
            
            await state.set_state(AdminStates.waiting_user_role)
    
    except ValueError:
        await message.answer(
            "❌ Неверный формат Telegram ID. Введите число:",
            reply_markup=CommonKeyboards.cancel()
        )


@router.callback_query(F.data.startswith("role_"), AdminStates.waiting_user_role)
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора роли"""
    role_map = {
        "role_admin": UserRole.ADMIN,
        "role_buyer": UserRole.BUYER,
        "role_executor": UserRole.EXECUTOR
    }
    
    selected_role = role_map.get(callback.data)
    if not selected_role:
        await callback.answer("❌ Ошибка выбора роли")
        return
    
    data = await state.get_data()
    await state.update_data(role=selected_role)
    
    # Получаем имя пользователя для отображения
    user_name = data.get('user_name', 'Неизвестно')
    
    # Если это заявка или существующий пользователь
    if data.get('existing_user') or data.get('is_application'):
        # Получаем информацию о пользователе для отображения
        if data.get('edit_user_id'):
            async with AsyncSessionLocal() as session:
                user = await UserQueries.get_user_by_id(session, data.get('edit_user_id'))
                if user:
                    user_name = f"{user.first_name} {user.last_name or ''}"
        
        # Если исполнитель - нужно направление
        if selected_role == UserRole.EXECUTOR:
            await callback.message.edit_text(
                f"✅ <b>Роль выбрана: Исполнитель</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>Пользователь:</b> {user_name}\n"
                f"🎭 <b>Роль:</b> 🛠️ Исполнитель\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Выберите направление работы:</b>",
                reply_markup=AdminKeyboards.direction_selector(),
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_user_direction)
        else:
            # Для админа и байера сразу назначаем роль
            await assign_role_to_existing_user(callback.message, state, callback.from_user.id)
    else:
        # Новый пользователь - создаём с временным именем
        if selected_role == UserRole.EXECUTOR:
            await callback.message.edit_text(
                "✅ <b>Роль выбрана: Исполнитель</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🎭 <b>Роль:</b> 🛠️ Исполнитель\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<b>Выберите направление работы:</b>",
                reply_markup=AdminKeyboards.direction_selector(),
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_user_direction)
        else:
            # Для админа и байера создаём пользователя сразу
            await create_new_user_with_temp_name(callback.message, state, callback.from_user.id)
    
    await callback.answer()


@router.callback_query(F.data.startswith("direction_"), AdminStates.waiting_user_direction)
async def process_direction_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора направления"""
    direction_map = {
        "direction_design": DirectionType.DESIGN,
        "direction_agency": DirectionType.AGENCY,
        "direction_copywriting": DirectionType.COPYWRITING,
        "direction_marketing": DirectionType.MARKETING
    }
    
    selected_direction = direction_map.get(callback.data)
    if not selected_direction:
        await callback.answer("❌ Ошибка выбора направления")
        return
    
    data = await state.get_data()
    await state.update_data(direction=selected_direction)
    
    # Проверяем, это редактирование существующего пользователя или добавление нового
    if data.get('edit_user_id'):
        # Редактирование - обновляем роль и направление существующего пользователя
        user_id = data.get('edit_user_id')
        new_role = data.get('new_role')
        
        async with AsyncSessionLocal() as session:
            admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
            user = await UserQueries.get_user_by_id(session, user_id)
            
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                await state.clear()
                return
            
            # Если new_role не установлен в состоянии, используем роль исполнителя
            # (так как выбор направления происходит только для исполнителей)
            if new_role is None:
                new_role = UserRole.EXECUTOR
            
            # Обновляем роль и направление
            old_role = user.role
            await UserQueries.update_user_role(session, user_id, new_role)
            await UserQueries.update_user_direction(session, user_id, selected_direction)
            
            # Получаем обновленного пользователя
            await session.refresh(user)
            
            # Логируем
            await LogQueries.create_action_log(
                session=session,
                user_id=admin.id,
                action_type="role_changed",
                entity_type="user",
                entity_id=user_id,
                details={
                    "old_role": old_role.value if old_role else "None",
                    "new_role": new_role.value if new_role else "None",
                    "direction": selected_direction.value
                }
            )
            
            # Отправляем уведомление пользователю
            try:
                notification_sent = await notify_user_role_assigned(
                    bot=callback.bot,
                    user_telegram_id=user.telegram_id,
                    role=new_role,
                    direction=selected_direction
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления пользователю {user.telegram_id}: {e}")
                notification_sent = False
            
            direction_names = {
                DirectionType.DESIGN: "🎨 Дизайн",
                DirectionType.AGENCY: "🏢 Агенство",
                DirectionType.COPYWRITING: "✍️ Копирайтинг",
                DirectionType.MARKETING: "📱 Маркетинг"
            }
            
            # Определяем, это заявка или редактирование
            is_application = data.get('is_application', False)
            
            if is_application:
                success_text = f"✅ <b>ЗАЯВКА ПРИНЯТА!</b>\n"
            else:
                success_text = f"✅ <b>РОЛЬ И НАПРАВЛЕНИЕ ИЗМЕНЕНЫ</b>\n"
            
            success_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            success_text += f"👤 <b>Пользователь:</b> {user.first_name} {user.last_name or ''}\n"
            success_text += f"📱 <b>Username:</b> @{user.username or 'не указан'}\n"
            success_text += f"🎭 <b>Роль:</b> 🛠️ Исполнитель\n"
            success_text += f"📁 <b>Направление:</b> {direction_names.get(selected_direction, selected_direction.value)}\n\n"
            success_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if notification_sent:
                success_text += "✅ Пользователь получил уведомление\n"
                success_text += "🎉 Теперь он может начать работу!"
            else:
                success_text += "⚠️ Не удалось отправить уведомление\n"
                success_text += "💡 Пользователь получит доступ при /start"
            
            await callback.message.edit_text(success_text, parse_mode="HTML")
            
            await state.clear()
            logger.info(f"Админ {admin.telegram_id} изменил роль и направление пользователя {user.telegram_id}")
    
    elif data.get('existing_user'):
        # Добавление роли существующему пользователю без роли
        await assign_role_to_existing_user(callback.message, state, callback.from_user.id)
    else:
        # Новый пользователь-исполнитель - создаём с временным именем
        await create_new_user_with_temp_name(callback.message, state, callback.from_user.id)
    
    await callback.answer()


async def create_new_user_with_temp_name(message, state: FSMContext, admin_telegram_id: int):
    """Создать нового пользователя с временным именем"""
    data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, admin_telegram_id)
        
        try:
            # Создаём пользователя с временным именем
            temp_first_name = "⏳ Ожидание первого входа"
            temp_last_name = None
            
            new_user = await UserQueries.create_user(
                session=session,
                telegram_id=data['telegram_id'],
                role=data['role'],
                first_name=temp_first_name,
                last_name=temp_last_name,
                direction=data.get('direction')
            )
            
            # Логируем действие
            await LogQueries.create_action_log(
                session=session,
                user_id=admin.id,
                action_type="user_created",
                entity_type="user",
                entity_id=new_user.id,
                details={
                    "telegram_id": data['telegram_id'],
                    "role": data['role'].value,
                    "direction": data.get('direction').value if data.get('direction') else None,
                    "temp_name": True
                }
            )
            
            # Отправляем уведомление пользователю
            bot = message.bot
            notification_sent = await notify_user_role_assigned(
                bot=bot,
                user_telegram_id=new_user.telegram_id,
                role=data['role'],
                direction=data.get('direction')
            )
            
            role_emoji = {"admin": "👑", "buyer": "👔", "executor": "🛠️"}
            emoji = role_emoji.get(data['role'].value, "👤")
            
            role_names = {
                UserRole.ADMIN: "Администратор",
                UserRole.BUYER: "Байер",
                UserRole.EXECUTOR: "Исполнитель"
            }
            
            success_text = f"""
✅ <b>ПОЛЬЗОВАТЕЛЬ СОЗДАН</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{emoji} <b>Роль:</b> {role_names.get(data['role'], data['role'].value)}
🆔 <b>Telegram ID:</b> {data['telegram_id']}
👤 <b>Статус:</b> Ожидается первый вход
"""
            
            if data.get('direction'):
                direction_names = {
                    DirectionType.DESIGN: "🎨 Дизайн",
                    DirectionType.AGENCY: "🏢 Агенство",
                    DirectionType.COPYWRITING: "✍️ Копирайтинг",
                    DirectionType.MARKETING: "📱 Маркетинг"
                }
                success_text += f"📁 <b>Направление:</b> {direction_names.get(data['direction'], data['direction'].value)}\n"
            
            success_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if notification_sent:
                success_text += "📨 <i>Пользователь получил уведомление.\nИмя обновится автоматически при первом /start</i>"
            else:
                success_text += "⚠️ <i>Не удалось отправить уведомление.\nИмя обновится автоматически при первом /start</i>"
            
            await message.answer(success_text, parse_mode="HTML")
            await state.clear()
            
            logger.info(f"Админ {admin.telegram_id} создал пользователя {new_user.telegram_id} с временным именем")
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании пользователя: {str(e)}")
            logger.error(f"Ошибка создания пользователя: {e}")


async def assign_role_to_existing_user(message, state: FSMContext, admin_telegram_id: int):
    """Назначить роль существующему пользователю"""
    data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, admin_telegram_id)
        
        # Получаем пользователя либо по telegram_id, либо по edit_user_id
        if data.get('edit_user_id'):
            user = await UserQueries.get_user_by_id(session, data['edit_user_id'])
        elif data.get('telegram_id'):
            user = await UserQueries.get_user_by_telegram_id(session, data['telegram_id'])
        else:
            await message.answer("❌ Ошибка: не указан ID пользователя")
            await state.clear()
            return
        
        if not user:
            await message.answer("❌ Ошибка: пользователь не найден")
            await state.clear()
            return
        
        # Обновляем роль
        old_role = user.role
        user.role = data['role']
        
        # Если исполнитель - обновляем направление
        if data['role'] == UserRole.EXECUTOR and data.get('direction'):
            user.direction = data['direction']
        # Если новая роль не исполнитель - удаляем направление
        elif data['role'] != UserRole.EXECUTOR and user.direction is not None:
            user.direction = None
        
        await session.commit()
        
        # Логируем
        action_type = "application_accepted" if data.get('is_application') else "role_assigned"
        await LogQueries.create_action_log(
            session=session,
            user_id=admin.id,
            action_type=action_type,
            entity_type="user",
            entity_id=user.id,
            details={
                "telegram_id": user.telegram_id,
                "old_role": old_role.value if old_role else "без роли",
                "new_role": data['role'].value,
                "direction": user.direction.value if user.direction else None
            }
        )
        
        # Отправляем уведомление пользователю
        bot = message.bot
        notification_sent = await notify_user_role_assigned(
            bot=bot,
            user_telegram_id=user.telegram_id,
            role=data['role'],
            direction=user.direction
        )
        
        role_emoji = {"admin": "👑", "buyer": "👔", "executor": "🛠️"}
        emoji = role_emoji.get(data['role'].value, "👤")
        
        role_names = {
            UserRole.ADMIN: "Администратор",
            UserRole.BUYER: "Байер",
            UserRole.EXECUTOR: "Исполнитель"
        }
        
        role_emojis = {
            UserRole.ADMIN: "👑",
            UserRole.BUYER: "👔",
            UserRole.EXECUTOR: "🛠️"
        }
        
        role_emoji = role_emojis.get(data['role'], "👤")
        
        success_text = f"""
✅ <b>ЗАЯВКА ПРИНЯТА!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Пользователь:</b> {user.first_name} {user.last_name or ''}
📱 <b>Username:</b> @{user.username or 'не указан'}
🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>
{role_emoji} <b>Роль:</b> {role_names.get(data['role'], data['role'].value)}
"""
        
        if user.direction:
            direction_names = {
                DirectionType.DESIGN: "🎨 Дизайн",
                DirectionType.AGENCY: "🏢 Агенство",
                DirectionType.COPYWRITING: "✍️ Копирайтинг",
                DirectionType.MARKETING: "📱 Маркетинг"
            }
            success_text += f"📁 <b>Направление:</b> {direction_names.get(user.direction, user.direction.value)}\n"
        
        success_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if notification_sent:
            success_text += "✅ Пользователь получил уведомление\n"
            success_text += "🎉 Теперь он может начать работу!"
        else:
            success_text += "⚠️ Не удалось отправить уведомление\n"
            success_text += "💡 Пользователь получит доступ при /start"
        
        await message.answer(success_text, parse_mode="HTML")
        await state.clear()
        
        logger.info(f"Админ {admin.telegram_id} назначил роль {data['role'].value} пользователю {user.telegram_id}")


@router.callback_query(F.data == "admin_list_users")
async def callback_list_users(callback: CallbackQuery):
    """Список пользователей (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        # Быстрый подсчет без загрузки данных
        total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
        
        if total_count == 0:
            await callback.message.edit_text("📋 Пользователей не найдено")
            await callback.answer()
            return
        
        # Загружаем только первую страницу (10 пользователей)
        page = 1
        per_page = 10
        users = await UserQueries.get_all_users(session, role=None, active_only=True, page=page, per_page=per_page)
        
        text = f"👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n📊 Всего: {total_count} пользователей\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "admin_list_inactive_users")
async def callback_list_inactive_users(callback: CallbackQuery):
    """Список неактивных пользователей (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        # Подсчитываем неактивных пользователей
        total_count = await UserQueries.count_users_by_role(session, role=None, active_only=False)
        active_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
        inactive_count = total_count - active_count
        
        if inactive_count == 0:
            await callback.message.edit_text(
                "✅ <b>ВСЕ ПОЛЬЗОВАТЕЛИ АКТИВНЫ</b>\n\n"
                "Нет деактивированных пользователей.",
                reply_markup=AdminKeyboards.user_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Загружаем всех неактивных (их обычно немного, можно не оптимизировать)
        # Но все равно ограничим до 1000 для безопасности
        all_users = await UserQueries.get_all_users(session, active_only=False, page=1, per_page=1000)
        inactive_users = [u for u in all_users if not u.is_active]
        
        text = f"🚫 <b>НЕАКТИВНЫЕ ПОЛЬЗОВАТЕЛИ</b>\n\n📊 Всего: {inactive_count} пользователей\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.user_list(inactive_users, page=1, per_page=10, total_count=inactive_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ============ СТАТИСТИКА ============

# Обработчик статистики перемещен в common.py для универсального роутинга по ролям
# @router.message(F.text == "📊 Статистика")
# async def admin_statistics(message: Message):
#     """Статистика"""
#     async with AsyncSessionLocal() as session:
#         user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
#         
#         if not user or user.role != UserRole.ADMIN:
#             await message.answer("❌ У вас нет доступа к этой функции")
#             return
#         
#         await message.answer(
#             "📊 <b>СТАТИСТИКА</b>\n\nВыберите раздел:",
#             reply_markup=AdminKeyboards.statistics_menu(),
#             parse_mode="HTML"
#         )


@router.callback_query(F.data == "stats_general")
async def callback_general_stats(callback: CallbackQuery):
    """Общая статистика (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        # Быстрый подсчет пользователей без загрузки данных
        total_users = await UserQueries.count_users_by_role(session, role=None, active_only=True)
        buyers_count = await UserQueries.count_users_by_role(session, role=UserRole.BUYER, active_only=True)
        executors_count = await UserQueries.count_users_by_role(session, role=UserRole.EXECUTOR, active_only=True)
        admins_count = await UserQueries.count_users_by_role(session, role=UserRole.ADMIN, active_only=True)
        
        # Подсчет задач
        from sqlalchemy import select, func as sql_func
        from db.models import Task
        
        total_tasks_result = await session.execute(select(sql_func.count(Task.id)))
        total_tasks = total_tasks_result.scalar()
        
        in_progress_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.IN_PROGRESS)
        )
        in_progress = in_progress_result.scalar()
        
        completed_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.APPROVED)
        )
        completed = completed_result.scalar()
        
        text = f"""
📊 <b>ОБЩАЯ СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 <b>Пользователи:</b>
   • Всего: {total_users}
   • 👑 Администраторы: {admins_count}
   • 👔 Байеры: {buyers_count}
   • 🛠️ Исполнители: {executors_count}

📋 <b>Задачи:</b>
   • Всего: {total_tasks}
   • 🟡 В работе: {in_progress}
   • ✅ Завершено: {completed}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ============ НАСТРОЙКА КАНАЛОВ ЛОГОВ ============

@router.message(F.text == "⚙️ Настройки каналов логов")
async def admin_log_channels(message: Message):
    """Настройка каналов логов"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        # Получаем список каналов из БД
        from db.queries.channel_queries import ChannelQueries
        channels = await ChannelQueries.get_all_active_channels(session)
        
        channels_text = ""
        if channels:
            for channel in channels:
                channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
                channels_text += f"• {channel_name} (ID: {channel.channel_id})\n"
        else:
            channels_text = "Не настроены"
        
        text = f"""
⚙️ <b>НАСТРОЙКА КАНАЛОВ ЛОГОВ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Текущие каналы:</b>
{channels_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Бот будет отправлять уведомления о задачах во все добавленные каналы.

Выберите действие:
"""
        
        await message.answer(
            text,
            reply_markup=AdminKeyboards.log_channel_management(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_channels_menu")
async def callback_channels_menu(callback: CallbackQuery):
    """Возврат в меню каналов"""
    async with AsyncSessionLocal() as session:
        from db.queries.channel_queries import ChannelQueries
        channels = await ChannelQueries.get_all_active_channels(session)
        
        channels_text = ""
        if channels:
            for channel in channels:
                channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
                channels_text += f"• {channel_name} (ID: {channel.channel_id})\n"
        else:
            channels_text = "Не настроены"
        
        text = f"""
⚙️ <b>НАСТРОЙКА КАНАЛОВ ЛОГОВ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Текущие каналы:</b>
{channels_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Бот будет отправлять уведомления о задачах во все добавленные каналы.

Выберите действие:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.log_channel_management(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "admin_add_channel")
async def callback_add_channel(callback: CallbackQuery, state: FSMContext):
    """Добавление канала"""
    await callback.message.edit_text(
        "➕ <b>ДОБАВЛЕНИЕ КАНАЛА</b>\n\n"
        "Введите ID канала (например: -1001234567890)\n\n"
        "<i>⚠️ Важно: Бот должен быть администратором канала!</i>\n\n"
        "Для получения ID канала:\n"
        "1. Отправьте сообщение в канал\n"
        "2. Перешлите его боту @userinfobot или @raw\n"
        "3. ID канала будет выглядеть как: -1001234567890",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_channel_id)
    await callback.answer()


@router.message(AdminStates.waiting_channel_id)
async def process_channel_id(message: Message, state: FSMContext, bot: Bot):
    """Обработка ID канала"""
    try:
        channel_id = int(message.text.strip())
        
        # Проверяем, что бот имеет доступ к каналу
        try:
            chat = await bot.get_chat(channel_id)
            channel_name = chat.title
        except Exception as e:
            await message.answer(
                "❌ <b>ОШИБКА</b>\n\n"
                "Не удалось получить доступ к каналу.\n\n"
                "Убедитесь, что:\n"
                "• ID канала введен правильно\n"
                "• Бот добавлен в канал как администратор\n"
                "• У бота есть права на публикацию сообщений",
                parse_mode="HTML"
            )
            logger.error(f"Ошибка доступа к каналу {channel_id}: {e}")
            return
        
        async with AsyncSessionLocal() as session:
            from db.queries.channel_queries import ChannelQueries
            user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
            
            # Добавляем канал в БД
            channel = await ChannelQueries.add_channel(
                session,
                channel_id=channel_id,
                created_by_id=user.id,
                channel_name=channel_name
            )
            
            if channel:
                # Добавляем канал в память LogChannel
                LogChannel.add_channel(channel_id)
                
                await message.answer(
                    f"✅ <b>КАНАЛ ДОБАВЛЕН</b>\n\n"
                    f"📢 Название: {channel_name}\n"
                    f"🆔 ID канала: {channel_id}\n\n"
                    f"Все уведомления о задачах будут отправляться в этот канал.",
                    parse_mode="HTML"
                )
                
                logger.info(f"Добавлен канал {channel_id} ({channel_name}) пользователем {user.telegram_id}")
            else:
                await message.answer(
                    "⚠️ <b>КАНАЛ УЖЕ СУЩЕСТВУЕТ</b>\n\n"
                    f"Канал с ID {channel_id} уже добавлен в систему.",
                    parse_mode="HTML"
                )
        
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID канала. Введите число:",
            reply_markup=CommonKeyboards.cancel()
        )


@router.callback_query(F.data == "admin_list_channels")
async def callback_list_channels(callback: CallbackQuery):
    """Список каналов"""
    async with AsyncSessionLocal() as session:
        from db.queries.channel_queries import ChannelQueries
        channels = await ChannelQueries.get_all_active_channels(session)
        
        if not channels:
            await callback.message.edit_text(
                "📋 <b>СПИСОК КАНАЛОВ</b>\n\n"
                "Каналы не добавлены.\n\n"
                "Используйте кнопку '➕ Добавить канал' для добавления.",
                reply_markup=AdminKeyboards.log_channel_management(),
                parse_mode="HTML"
            )
        else:
            text = "📋 <b>СПИСОК КАНАЛОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, channel in enumerate(channels, 1):
                channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
                text += f"{i}. 📢 <b>{channel_name}</b>\n"
                text += f"   🆔 ID: <code>{channel.channel_id}</code>\n"
                text += f"   📅 Добавлен: {channel.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            await callback.message.edit_text(
                text,
                reply_markup=AdminKeyboards.channel_list(channels),
                parse_mode="HTML"
            )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_channel_"))
async def callback_view_channel(callback: CallbackQuery):
    """Просмотр канала"""
    channel_db_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        from db.queries.channel_queries import ChannelQueries
        from sqlalchemy import select
        from db.models import Channel
        
        result = await session.execute(
            select(Channel).where(Channel.id == channel_db_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            await callback.answer("❌ Канал не найден", show_alert=True)
            return
        
        channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
        
        text = f"""
📢 <b>ИНФОРМАЦИЯ О КАНАЛЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Название:</b> {channel_name}
<b>ID канала:</b> <code>{channel.channel_id}</code>
<b>Статус:</b> {'✅ Активен' if channel.is_active else '❌ Неактивен'}
<b>Добавлен:</b> {channel.created_at.strftime('%d.%m.%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите действие:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.channel_actions(channel.channel_id, channel.id),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_channel_"))
async def callback_delete_channel(callback: CallbackQuery):
    """Удаление канала"""
    channel_db_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        from db.queries.channel_queries import ChannelQueries
        from sqlalchemy import select
        from db.models import Channel
        
        result = await session.execute(
            select(Channel).where(Channel.id == channel_db_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            await callback.answer("❌ Канал не найден", show_alert=True)
            return
        
        # Удаляем канал из БД
        success = await ChannelQueries.delete_channel(session, channel.channel_id)
        
        if success:
            # Удаляем из памяти LogChannel
            LogChannel.remove_channel(channel.channel_id)
            
            channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
            
            await callback.message.edit_text(
                f"✅ <b>КАНАЛ УДАЛЕН</b>\n\n"
                f"📢 {channel_name}\n"
                f"🆔 ID: {channel.channel_id}\n\n"
                f"Канал больше не будет получать уведомления о задачах.",
                reply_markup=AdminKeyboards.log_channel_management(),
                parse_mode="HTML"
            )
            
            logger.info(f"Канал {channel.channel_id} удален")
        else:
            await callback.answer("❌ Ошибка при удалении канала", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery):
    """Пустой callback для неактивных кнопок"""
    await callback.answer()


@router.callback_query(F.data == "stats_users")
async def callback_stats_users(callback: CallbackQuery):
    """Статистика по пользователям (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func as sql_func
        from db.models import Task
        
        # Быстрый подсчет пользователей
        buyers_count = await UserQueries.count_users_by_role(session, role=UserRole.BUYER, active_only=True)
        executors_count = await UserQueries.count_users_by_role(session, role=UserRole.EXECUTOR, active_only=True)
        
        # Загружаем только топ 10 байеров и исполнителей
        buyers = await UserQueries.get_all_users(session, role=UserRole.BUYER, active_only=True, page=1, per_page=10)
        executors = await UserQueries.get_all_users(session, role=UserRole.EXECUTOR, active_only=True, page=1, per_page=10)
        
        text = f"""
📊 <b>СТАТИСТИКА ПО ПОЛЬЗОВАТЕЛЯМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👔 <b>БАЙЕРЫ ({buyers_count}):</b>
"""
        
        for buyer in buyers:  # Топ 10
            tasks_count_result = await session.execute(
                select(sql_func.count(Task.id)).where(Task.created_by_id == buyer.id)
            )
            tasks_count = tasks_count_result.scalar()
            text += f"• {buyer.first_name} {buyer.last_name or ''}: {tasks_count} задач\n"
        
        text += f"\n🛠️ <b>ИСПОЛНИТЕЛИ ({executors_count}):</b>\n"
        
        for executor in executors:  # Топ 10
            tasks_count_result = await session.execute(
                select(sql_func.count(Task.id)).where(Task.executor_id == executor.id)
            )
            tasks_count = tasks_count_result.scalar()
            completed_result = await session.execute(
                select(sql_func.count(Task.id)).where(
                    Task.executor_id == executor.id,
                    Task.status == TaskStatus.APPROVED
                )
            )
            completed = completed_result.scalar()
            
            text += f"• {executor.first_name} {executor.last_name or ''}: "
            text += f"{tasks_count} всего, ✅ {completed} завершено\n"
        
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "stats_tasks")
async def callback_stats_tasks(callback: CallbackQuery):
    """Статистика по задачам"""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func as sql_func
        from db.models import Task
        
        # Подсчет по статусам
        total_result = await session.execute(select(sql_func.count(Task.id)))
        total = total_result.scalar()
        
        pending_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.PENDING)
        )
        pending = pending_result.scalar()
        
        in_progress_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.IN_PROGRESS)
        )
        in_progress = in_progress_result.scalar()
        
        completed_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.COMPLETED)
        )
        completed = completed_result.scalar()
        
        approved_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.APPROVED)
        )
        approved = approved_result.scalar()
        
        cancelled_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.status == TaskStatus.CANCELLED)
        )
        cancelled = cancelled_result.scalar()
        
        # Подсчет по приоритетам
        high_priority_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.priority >= 3)
        )
        high_priority = high_priority_result.scalar()
        
        text = f"""
📊 <b>СТАТИСТИКА ПО ЗАДАЧАМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Всего задач:</b> {total}

<b>По статусам:</b>
   ⏳ Ожидают: {pending}
   🟡 В работе: {in_progress}
   ✅ На проверке: {completed}
   🎉 Одобрено: {approved}
   🚫 Отменено: {cancelled}

<b>Приоритетные:</b>
   🔴 Высокий/Срочный: {high_priority}

<b>Процент выполнения:</b>
   {round(approved / total * 100) if total > 0 else 0}%

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "stats_directions")
async def callback_stats_directions(callback: CallbackQuery):
    """Статистика по направлениям"""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func as sql_func
        from db.models import Task
        
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
            
            # Исполнители
            executors = await UserQueries.get_executors_by_direction(session, direction)
            
            # Задачи
            tasks_result = await session.execute(
                select(sql_func.count(Task.id)).where(Task.direction == direction)
            )
            tasks_count = tasks_result.scalar()
            
            # В работе
            in_work_result = await session.execute(
                select(sql_func.count(Task.id)).where(
                    Task.direction == direction,
                    Task.status == TaskStatus.IN_PROGRESS
                )
            )
            in_work = in_work_result.scalar()
            
            # Завершено
            completed_result = await session.execute(
                select(sql_func.count(Task.id)).where(
                    Task.direction == direction,
                    Task.status == TaskStatus.APPROVED
                )
            )
            completed = completed_result.scalar()
            
            text += f"{emoji} <b>{name}</b>\n"
            text += f"   👥 Исполнителей: {len(executors)}\n"
            text += f"   📋 Задач всего: {tasks_count}\n"
            text += f"   🟡 В работе: {in_work}\n"
            text += f"   ✅ Завершено: {completed}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "stats_period")
async def callback_stats_period(callback: CallbackQuery):
    """Статистика за период"""
    await callback.message.edit_text(
        "📅 <b>СТАТИСТИКА ЗА ПЕРИОД</b>\n\n"
        "Выберите период:",
        reply_markup=AdminKeyboards.period_selector(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("period_"))
async def callback_period_selected(callback: CallbackQuery):
    """Обработка выбора периода"""
    period = callback.data.replace("period_", "")
    
    # Определяем даты
    now = datetime.now(timezone.utc)
    period_names = {
        "today": ("Сегодня", now.replace(hour=0, minute=0, second=0)),
        "week": ("Неделя", now - timedelta(days=7)),
        "month": ("Месяц", now - timedelta(days=30)),
        "quarter": ("Квартал", now - timedelta(days=90)),
        "year": ("Год", now - timedelta(days=365)),
        "all": ("Весь период", datetime(2020, 1, 1, tzinfo=timezone.utc))
    }
    
    period_name, start_date = period_names.get(period, ("Неизвестно", now))
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func as sql_func
        from db.models import Task
        
        # Задачи за период
        created_result = await session.execute(
            select(sql_func.count(Task.id)).where(Task.created_at >= start_date)
        )
        created = created_result.scalar()
        
        completed_result = await session.execute(
            select(sql_func.count(Task.id)).where(
                Task.completed_at >= start_date,
                Task.status == TaskStatus.APPROVED
            )
        )
        completed = completed_result.scalar()
        
        text = f"""
📊 <b>СТАТИСТИКА: {period_name.upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 <b>Период:</b> с {start_date.strftime("%d.%m.%Y")}

📋 <b>Создано задач:</b> {created}
✅ <b>Завершено задач:</b> {completed}

<b>Процент выполнения:</b>
   {round(completed / created * 100) if created > 0 else 0}%

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.statistics_menu(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.message(F.text == "📋 Все задачи")
async def admin_all_tasks(message: Message):
    """Все задачи в системе"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        from sqlalchemy import select
        from db.models import Task
        
        result = await session.execute(
            select(Task)
            .order_by(Task.created_at.desc())
            .limit(20)
        )
        tasks = result.scalars().all()
        
        if not tasks:
            await message.answer("📋 Задач пока нет")
            return
        
        text = "📋 <b>ВСЕ ЗАДАЧИ</b> (последние 20)\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await message.answer(
            text,
            reply_markup=AdminKeyboards.task_list(tasks),
            parse_mode="HTML"
        )
        logger.info(f"Админ {user.telegram_id} просматривает все задачи")


@router.callback_query(F.data.startswith("admin_view_task_"))
async def callback_admin_view_task(callback: CallbackQuery):
    """Просмотр задачи администратором"""
    task_id = int(callback.data.replace("admin_view_task_", ""))
    
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
        
        creator_name = f"{task.creator.first_name} {task.creator.last_name or ''}" if task.creator else "Не указан"
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

👤 <b>Создатель:</b> {creator_name}
🛠️ <b>Исполнитель:</b> {executor_name}
⏱️ <b>Дедлайн:</b> {deadline_str}

{execution_time}

📝 <b>Описание:</b>
{task.description}

📅 <b>Создана:</b> {task.created_at.strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_actions(task_id, task.status),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_task_details_"))
async def callback_admin_task_details(callback: CallbackQuery):
    """Детали задачи для администратора"""
    task_id = int(callback.data.replace("admin_task_details_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена")
            return
        
        from bot.utils.time_tracker import get_execution_time_display
        from db.models import FileType
        
        status_emoji = {
            TaskStatus.PENDING: "⏳ Ожидает",
            TaskStatus.IN_PROGRESS: "🟡 В работе",
            TaskStatus.COMPLETED: "✅ Завершена",
            TaskStatus.APPROVED: "🎉 Одобрена",
            TaskStatus.REJECTED: "❌ Отклонена",
            TaskStatus.CANCELLED: "🚫 Отменена"
        }
        
        priority_names = ["🟢 Низкий", "🟡 Средний", "🟠 Высокий", "🔴 Срочный"]
        
        creator_name = f"{task.creator.first_name} {task.creator.last_name or ''}" if task.creator else "Не указан"
        executor_name = f"{task.executor.first_name} {task.executor.last_name or ''}" if task.executor else "Не назначен"
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        # Получаем время выполнения
        execution_time = get_execution_time_display(task)
        
        # Получаем статистику файлов
        files = await FileQueries.get_task_files(session, task_id)
        initial_files = [f for f in files if f.file_type == FileType.INITIAL]
        result_files = [f for f in files if f.file_type == FileType.RESULT]
        message_files = [f for f in files if f.file_type == FileType.MESSAGE]
        total_files_size = await FileQueries.get_total_files_size(session, task_id)
        total_files_size_mb = total_files_size / (1024 * 1024) if total_files_size else 0
        
        # Получаем статистику сообщений
        messages = await MessageQueries.get_task_messages(session, task_id)
        messages_count = len(messages)
        
        # Получаем статистику правок
        from sqlalchemy import select, func
        from db.models import TaskCorrection
        corrections_result = await session.execute(
            select(func.count(TaskCorrection.id)).where(TaskCorrection.task_id == task_id)
        )
        corrections_count = corrections_result.scalar() or 0
        
        text = f"""
📊 <b>ДЕТАЛИ ЗАДАЧИ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 <b>Название:</b> {task.title}
🏷️ <b>Статус:</b> {status_emoji.get(task.status, task.status.value)}
📍 <b>Приоритет:</b> {priority_names[task.priority-1]}

👤 <b>Создатель:</b> {creator_name}
🛠️ <b>Исполнитель:</b> {executor_name}
⏱️ <b>Дедлайн:</b> {deadline_str}

{execution_time}

📝 <b>Описание:</b>
{task.description}

━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>СТАТИСТИКА:</b>

📎 <b>Файлы:</b>
  • Исходные: {len(initial_files)}
  • Результат: {len(result_files)}
  • В сообщениях: {len(message_files)}
  • Всего: {len(files)}
  • Общий размер: {total_files_size_mb:.2f} МБ

💬 <b>Сообщений:</b> {messages_count}

✏️ <b>Правок запрошено:</b> {corrections_count}

📅 <b>Создана:</b> {task.created_at.strftime("%d.%m.%Y %H:%M")}
"""
        
        if task.started_at:
            text += f"▶️ <b>Начата:</b> {task.started_at.strftime("%d.%m.%Y %H:%M")}\n"
        
        if task.completed_at:
            text += f"✅ <b>Завершена:</b> {task.completed_at.strftime("%d.%m.%Y %H:%M")}\n"
        
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_actions(task_id, task.status),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_files_"))
async def callback_admin_view_files(callback: CallbackQuery):
    """Просмотр файлов задачи администратором"""
    task_id = int(callback.data.replace("admin_view_files_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
        
        # Получаем файлы задачи
        files = await FileQueries.get_task_files(session, task_id)
        
        if not files:
            await callback.answer("📭 Нет файлов", show_alert=True)
            return
        
        # Группируем файлы по типам
        from db.models import FileType
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
            reply_markup=AdminKeyboards.task_files_actions(task_id, files),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_messages_"))
async def callback_admin_view_messages(callback: CallbackQuery):
    """Просмотр истории сообщений задачи администратором"""
    task_id = int(callback.data.replace("admin_view_messages_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
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
            sender_name = f"{msg.sender.first_name} {msg.sender.last_name or ''}".strip() if msg.sender else "Система"
            time_str = msg.created_at.strftime("%d.%m.%Y %H:%M")
            text += f"<b>[{time_str}] {sender_name}:</b>\n{msg.content}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_actions(task_id, task.status),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_download_file_"))
async def callback_admin_download_file(callback: CallbackQuery, bot: Bot):
    """Скачивание файла администратором"""
    file_id = int(callback.data.replace("admin_download_file_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        file_record = await FileQueries.get_file_by_id(session, file_id)
        
        if not file_record:
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
        
        try:
            # Проверяем, есть ли сохраненный file_id для больших файлов
            from db.queries.file_queries import FileQueries
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
                from bot.utils.file_handler import FileHandler
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
                from bot.utils.photo_handler import PhotoHandler
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


@router.callback_query(F.data == "admin_all_tasks")
async def callback_admin_all_tasks(callback: CallbackQuery):
    """Возврат к списку всех задач"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        from sqlalchemy import select
        from db.models import Task
        
        result = await session.execute(
            select(Task)
            .order_by(Task.created_at.desc())
            .limit(20)
        )
        tasks = result.scalars().all()
        
        if not tasks:
            await callback.message.edit_text("📋 Задач пока нет")
            await callback.answer()
            return
        
        text = "📋 <b>ВСЕ ЗАДАЧИ</b> (последние 20)\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_list(tasks),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "admin_refresh_tasks")
async def callback_admin_refresh_tasks(callback: CallbackQuery):
    """Обновление списка задач администратора"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        from sqlalchemy import select
        from db.models import Task
        
        result = await session.execute(
            select(Task)
            .order_by(Task.created_at.desc())
            .limit(20)
        )
        tasks = result.scalars().all()
        
        if not tasks:
            await callback.message.edit_text("📋 Задач пока нет")
            await callback.answer("Список обновлен")
            return
        
        text = "📋 <b>ВСЕ ЗАДАЧИ</b> (последние 20)\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_list(tasks),
            parse_mode="HTML"
        )
    
    await callback.answer("Список обновлен")


@router.callback_query(F.data.startswith("admin_tasks_page_"))
async def callback_admin_tasks_page(callback: CallbackQuery):
    """Пагинация списка задач администратора"""
    page = int(callback.data.replace("admin_tasks_page_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа")
            return
        
        from sqlalchemy import select
        from db.models import Task
        
        result = await session.execute(
            select(Task)
            .order_by(Task.created_at.desc())
        )
        tasks = result.scalars().all()
        
        if not tasks:
            await callback.answer("❌ Нет задач")
            return
        
        text = "📋 <b>ВСЕ ЗАДАЧИ</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.task_list(tasks, page=page),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "admin_main")
async def callback_admin_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню администратора"""
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        text = """
👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите действие:
"""
        
        # Удаляем inline-клавиатуру из текущего сообщения
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        
        # Отправляем новое сообщение с reply-клавиатурой
        await callback.message.answer(
            text,
            reply_markup=AdminKeyboards.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()
        logger.info(f"Админ {user.telegram_id} вернулся в главное меню")


# ============ РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЕЙ ============

@router.callback_query(F.data == "admin_edit_user")
async def callback_edit_user(callback: CallbackQuery, state: FSMContext):
    """Редактирование пользователя - показываем список (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        # Быстрый подсчет без загрузки данных
        total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
        
        if total_count == 0:
            await callback.message.edit_text("📋 Пользователей не найдено")
            await callback.answer()
            return
        
        # Загружаем только первую страницу
        page = 1
        per_page = 10
        users = await UserQueries.get_all_users(session, page=page, per_page=per_page)
        
        text = f"✏️ <b>РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n📊 Выберите пользователя из списка:\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_page_"))
async def callback_users_page(callback: CallbackQuery):
    """Навигация по страницам пользователей (оптимизировано)"""
    page = int(callback.data.replace("admin_users_page_", ""))
    per_page = 10
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        # Определяем контекст по тексту сообщения
        message_text = callback.message.text or ""
        
        if "РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ" in message_text:
            # Контекст редактирования
            total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
            if total_count == 0:
                await callback.message.edit_text("📋 Пользователей не найдено")
                await callback.answer()
                return
            users = await UserQueries.get_all_users(session, page=page, per_page=per_page)
            text = f"✏️ <b>РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n📊 Выберите пользователя из списка:\n\n"
            reply_markup = AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count)
        elif "УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ" in message_text:
            # Контекст удаления
            total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
            if total_count == 0:
                await callback.message.edit_text("📋 Пользователей не найдено")
                await callback.answer()
                return
            users = await UserQueries.get_all_users(session, page=page, per_page=per_page)
            text = f"🗑 <b>УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n⚠️ Выберите пользователя для удаления:\n\n"
            reply_markup = AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count)
        elif "НЕАКТИВНЫЕ ПОЛЬЗОВАТЕЛИ" in message_text:
            # Контекст неактивных пользователей
            total_count = await UserQueries.count_users_by_role(session, role=None, active_only=False)
            active_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
            inactive_count = total_count - active_count
            
            if inactive_count == 0:
                await callback.message.edit_text(
                    "✅ <b>ВСЕ ПОЛЬЗОВАТЕЛИ АКТИВНЫ</b>\n\n"
                    "Нет деактивированных пользователей.",
                    reply_markup=AdminKeyboards.user_management(),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
            
            # Загружаем всех неактивных (их обычно немного, можно не оптимизировать)
            all_users = await UserQueries.get_all_users(session, active_only=False, page=1, per_page=1000)
            inactive_users = [u for u in all_users if not u.is_active]
            
            text = f"🚫 <b>НЕАКТИВНЫЕ ПОЛЬЗОВАТЕЛИ</b>\n\n📊 Всего: {inactive_count} пользователей\n\n"
            reply_markup = AdminKeyboards.user_list(inactive_users, page=page, per_page=per_page, total_count=inactive_count)
        else:
            # Контекст списка пользователей (по умолчанию)
            total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
            if total_count == 0:
                await callback.message.edit_text("📋 Пользователей не найдено")
                await callback.answer()
                return
            users = await UserQueries.get_all_users(session, page=page, per_page=per_page)
            text = f"👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n📊 Всего: {total_count} пользователей\n\n"
            reply_markup = AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count)
        
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_user_"))
async def callback_view_user(callback: CallbackQuery):
    """Просмотр информации о пользователе"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Подготовка данных
        role_emoji = {
            UserRole.ADMIN: "👑",
            UserRole.BUYER: "👔",
            UserRole.EXECUTOR: "🛠️"
        }.get(user.role, "👤")
        
        role_names = {
            UserRole.ADMIN: "Администратор",
            UserRole.BUYER: "Байер",
            UserRole.EXECUTOR: "Исполнитель"
        }
        
        status = "✅ Активен" if user.is_active else "❌ Неактивен"
        
        text = f"""
{role_emoji} <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Имя:</b> {user.first_name or 'Не указано'} {user.last_name or ''}
🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>
📝 <b>Username:</b> @{user.username or 'Не указан'}
🎭 <b>Роль:</b> {role_names.get(user.role, 'Не назначена')}
"""
        
        if user.direction:
            direction_names = {
                DirectionType.DESIGN: "🎨 Дизайн",
                DirectionType.AGENCY: "🏢 Агенство",
                DirectionType.COPYWRITING: "✍️ Копирайтинг",
                DirectionType.MARKETING: "📱 Маркетинг"
            }
            text += f"📁 <b>Направление:</b> {direction_names.get(user.direction, user.direction.value)}\n"
        
        if user.role == UserRole.EXECUTOR:
            text += f"📊 <b>Текущая загрузка:</b> {user.current_load} задач\n"
            text += f"📈 <b>Завершено:</b> {user.completed_tasks} задач\n"
        
        text += f"🔘 <b>Статус:</b> {status}\n"
        text += f"📅 <b>Создан:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "\nВыберите действие:"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.user_actions(user.id, user.is_active, user.role),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_change_role_"))
async def callback_change_role(callback: CallbackQuery, state: FSMContext):
    """Изменение роли пользователя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        await state.update_data(edit_user_id=user_id)
        
        text = f"""
✏️ <b>ИЗМЕНЕНИЕ РОЛИ</b>

👤 Пользователь: {user.first_name} {user.last_name or ''}
🎭 Текущая роль: {user.role.value if user.role else 'Не назначена'}

Выберите новую роль:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.role_selector(),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_edit_value)
    
    await callback.answer()


@router.callback_query(F.data.startswith("role_"), AdminStates.waiting_edit_value)
async def process_role_change(callback: CallbackQuery, state: FSMContext):
    """Обработка изменения роли"""
    role_map = {
        "role_admin": UserRole.ADMIN,
        "role_buyer": UserRole.BUYER,
        "role_executor": UserRole.EXECUTOR
    }
    
    selected_role = role_map.get(callback.data)
    if not selected_role:
        await callback.answer("❌ Ошибка выбора роли")
        return
    
    data = await state.get_data()
    user_id = data.get('edit_user_id')
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            await state.clear()
            return
        
        # Если выбран исполнитель, нужно направление (если его еще нет)
        if selected_role == UserRole.EXECUTOR and not user.direction:
            await state.update_data(new_role=selected_role, edit_user_id=user_id)
            await callback.message.edit_text(
                f"✅ Роль выбрана: Исполнитель\n\n"
                f"👤 Пользователь: {user.first_name} {user.last_name or ''}\n\n"
                f"Теперь выберите направление:",
                reply_markup=AdminKeyboards.direction_selector(),
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_user_direction)
            await callback.answer()
            return
        
        # Обновляем роль
        old_role = user.role
        await UserQueries.update_user_role(session, user_id, selected_role)
        
        # Получаем обновленного пользователя из БД
        await session.refresh(user)
        
        # Логируем
        await LogQueries.create_action_log(
            session=session,
            user_id=admin.id,
            action_type="role_changed",
            entity_type="user",
            entity_id=user_id,
            details={
                "old_role": old_role.value if old_role else "None",
                "new_role": selected_role.value,
                "direction": user.direction.value if user.direction else None
            }
        )
        
        # Отправляем уведомление пользователю
        try:
            notification_sent = await notify_user_role_assigned(
                bot=callback.bot,
                user_telegram_id=user.telegram_id,
                role=selected_role,
                direction=user.direction
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю {user.telegram_id}: {e}")
            notification_sent = False
        
        role_names = {
            UserRole.ADMIN: "Администратор",
            UserRole.BUYER: "Байер",
            UserRole.EXECUTOR: "Исполнитель"
        }
        
        success_text = f"✅ <b>РОЛЬ ИЗМЕНЕНА</b>\n\n"
        success_text += f"👤 Пользователь: {user.first_name} {user.last_name or ''}\n"
        success_text += f"🎭 Новая роль: {role_names.get(selected_role, selected_role.value)}\n"
        
        if user.direction:
            direction_names = {
                DirectionType.DESIGN: "🎨 Дизайн",
                DirectionType.AGENCY: "🏢 Агенство",
                DirectionType.COPYWRITING: "✍️ Копирайтинг",
                DirectionType.MARKETING: "📱 Маркетинг"
            }
            success_text += f"📁 Направление: {direction_names.get(user.direction, user.direction.value)}\n"
        
        success_text += "\n"
        if notification_sent:
            success_text += "📨 <i>Пользователь получил уведомление</i>"
        else:
            success_text += "⚠️ <i>Не удалось отправить уведомление</i>"
        
        await callback.message.edit_text(success_text, parse_mode="HTML")
        
        await state.clear()
        logger.info(f"Админ {admin.telegram_id} изменил роль пользователя {user.telegram_id}")
    
    await callback.answer("✅ Роль успешно изменена")


@router.callback_query(F.data.startswith("admin_change_direction_"))
async def callback_change_direction(callback: CallbackQuery, state: FSMContext):
    """Изменение направления исполнителя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        if user.role != UserRole.EXECUTOR:
            await callback.answer("⚠️ Эта функция доступна только для исполнителей", show_alert=True)
            return
        
        await state.update_data(edit_user_id=user_id, edit_field="direction")
        
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        
        text = f"""
🔄 <b>ИЗМЕНЕНИЕ НАПРАВЛЕНИЯ</b>

👤 Исполнитель: {user.first_name} {user.last_name or ''}
📁 Текущее направление: {direction_names.get(user.direction, 'Не указано') if user.direction else 'Не указано'}

Выберите новое направление:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.direction_selector(),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_edit_value)
    
    await callback.answer()


@router.callback_query(F.data.startswith("direction_"), AdminStates.waiting_edit_value)
async def process_direction_update(callback: CallbackQuery, state: FSMContext):
    """Обработка обновления направления"""
    direction_map = {
        "direction_design": DirectionType.DESIGN,
        "direction_agency": DirectionType.AGENCY,
        "direction_copywriting": DirectionType.COPYWRITING,
        "direction_marketing": DirectionType.MARKETING
    }
    
    selected_direction = direction_map.get(callback.data)
    if not selected_direction:
        await callback.answer("❌ Ошибка выбора направления")
        return
    
    data = await state.get_data()
    user_id = data.get('edit_user_id')
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            await state.clear()
            return
        
        old_direction = user.direction
        await UserQueries.update_user_direction(session, user_id, selected_direction)
        
        # Логируем
        await LogQueries.create_action_log(
            session=session,
            user_id=admin.id,
            action_type="direction_changed",
            entity_type="user",
            entity_id=user_id,
            details={
                "old_direction": old_direction.value if old_direction else "None",
                "new_direction": selected_direction.value
            }
        )
        
        direction_names = {
            DirectionType.DESIGN: "🎨 Дизайн",
            DirectionType.AGENCY: "🏢 Агенство",
            DirectionType.COPYWRITING: "✍️ Копирайтинг",
            DirectionType.MARKETING: "📱 Маркетинг"
        }
        
        await callback.message.edit_text(
            f"✅ <b>НАПРАВЛЕНИЕ ИЗМЕНЕНО</b>\n\n"
            f"👤 Исполнитель: {user.first_name} {user.last_name or ''}\n"
            f"📁 Новое направление: {direction_names.get(selected_direction, selected_direction.value)}",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Админ {admin.telegram_id} изменил направление пользователя {user.telegram_id}")
    
    await callback.answer("✅ Направление изменено")


@router.callback_query(F.data.startswith("admin_change_name_"))
async def callback_change_name(callback: CallbackQuery, state: FSMContext):
    """Изменение имени пользователя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        await state.update_data(edit_user_id=user_id, edit_field="name")
        
        text = f"""
📝 <b>ИЗМЕНЕНИЕ ИМЕНИ ПОЛЬЗОВАТЕЛЯ</b>

👤 Пользователь: {user.first_name} {user.last_name or ''}
🆔 Telegram ID: <code>{user.telegram_id}</code>

Введите новое имя пользователя в формате:
<code>Имя</code> или <code>Имя Фамилия</code>

Пример:
• Иван
• Иван Петров
"""
        
        await callback.message.edit_text(text, parse_mode="HTML")
        await state.set_state(AdminStates.waiting_user_name)
    
    await callback.answer()


@router.message(AdminStates.waiting_user_name)
async def process_name_change(message: Message, state: FSMContext):
    """Обработка изменения имени пользователя"""
    name_parts = message.text.strip().split(maxsplit=1)
    
    if len(name_parts) == 0 or len(name_parts[0]) < 1:
        await message.answer(
            "❌ Имя не может быть пустым. Введите имя пользователя:",
            reply_markup=CommonKeyboards.cancel()
        )
        return
    
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else None
    
    data = await state.get_data()
    user_id = data.get('edit_user_id')
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        user = await UserQueries.update_user_name(session, user_id, first_name, last_name)
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return
        
        # Логируем
        await LogQueries.create_action_log(
            session=session,
            user_id=admin.id,
            action_type="user_name_changed",
            entity_type="user",
            entity_id=user_id,
            details={
                "new_first_name": first_name,
                "new_last_name": last_name
            }
        )
        
        await message.answer(
            f"✅ <b>ИМЯ ИЗМЕНЕНО</b>\n\n"
            f"👤 Пользователь: {user.first_name} {user.last_name or ''}\n"
            f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n\n"
            f"Имя пользователя успешно обновлено.",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Админ {admin.telegram_id} изменил имя пользователя {user.telegram_id} на '{first_name} {last_name or ''}'")



@router.callback_query(F.data.startswith("admin_deactivate_"))
async def callback_deactivate_user(callback: CallbackQuery):
    """Деактивация/активация пользователя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Переключаем статус
        if user.is_active:
            await UserQueries.deactivate_user(session, user_id)
            action = "деактивирован"
            status = "❌ Неактивен"
            action_type = "user_deactivated"
        else:
            await UserQueries.activate_user(session, user_id)
            action = "активирован"
            status = "✅ Активен"
            action_type = "user_activated"
        
        # Логируем
        await LogQueries.create_action_log(
            session=session,
            user_id=admin.id,
            action_type=action_type,
            entity_type="user",
            entity_id=user_id,
            details={"telegram_id": user.telegram_id}
        )
        
        await callback.message.edit_text(
            f"✅ <b>ПОЛЬЗОВАТЕЛЬ {action.upper()}</b>\n\n"
            f"👤 Пользователь: {user.first_name} {user.last_name or ''}\n"
            f"🔘 Статус: {status}",
            parse_mode="HTML"
        )
        
        logger.info(f"Админ {admin.telegram_id} {action} пользователя {user.telegram_id}")
    
    await callback.answer(f"✅ Пользователь {action}")


# ============ УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ============

@router.callback_query(F.data == "admin_delete_user")
async def callback_delete_user_list(callback: CallbackQuery):
    """Удаление пользователя - показываем список (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        # Быстрый подсчет без загрузки данных
        total_count = await UserQueries.count_users_by_role(session, role=None, active_only=True)
        
        if total_count == 0:
            await callback.message.edit_text("📋 Пользователей не найдено")
            await callback.answer()
            return
        
        # Загружаем только первую страницу
        page = 1
        per_page = 10
        users = await UserQueries.get_all_users(session, page=page, per_page=per_page)
        
        text = f"🗑 <b>УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n⚠️ Выберите пользователя для удаления:\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.user_list(users, page=page, per_page=per_page, total_count=total_count),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete_"))
async def callback_confirm_delete(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления пользователя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Создаем inline-клавиатуру для подтверждения
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, удалить", callback_data=f"delete_confirmed_{user_id}")
        builder.button(text="❌ Отменить", callback_data=f"admin_view_user_{user_id}")
        builder.adjust(2)
        
        role_names = {
            UserRole.ADMIN: "Администратор",
            UserRole.BUYER: "Байер",
            UserRole.EXECUTOR: "Исполнитель"
        }
        
        text = f"""
⚠️ <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Вы действительно хотите <b>УДАЛИТЬ</b> этого пользователя?

👤 <b>Имя:</b> {user.first_name} {user.last_name or ''}
🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>
🎭 <b>Роль:</b> {role_names.get(user.role, 'Не назначена')}

<b>⚠️ ВНИМАНИЕ!</b>
Это действие <b>необратимо</b>. Все данные пользователя будут удалены из базы данных.
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("delete_confirmed_"))
async def callback_delete_confirmed(callback: CallbackQuery, state: FSMContext):
    """Окончательное удаление пользователя"""
    user_id = int(callback.data.split("_")[-1])
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        user = await UserQueries.get_user_by_id(session, user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Сохраняем информацию для логирования
        user_info = {
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value if user.role else "None"
        }
        
        # Удаляем пользователя
        success = await UserQueries.delete_user(session, user_id)
        
        if success:
            # Логируем (пользователь уже удален, поэтому entity_id будет None)
            await LogQueries.create_action_log(
                session=session,
                user_id=admin.id,
                action_type="user_deleted",
                entity_type="user",
                entity_id=None,
                details=user_info
            )
            
            await callback.message.edit_text(
                f"✅ <b>ПОЛЬЗОВАТЕЛЬ УДАЛЕН</b>\n\n"
                f"👤 Удаленный пользователь: {user_info['first_name']} {user_info.get('last_name', '')}\n"
                f"🆔 Telegram ID: <code>{user_info['telegram_id']}</code>\n\n"
                f"Пользователь успешно удален из базы данных.",
                parse_mode="HTML"
            )
            
            logger.info(f"Админ {admin.telegram_id} удалил пользователя {user_info['telegram_id']}")
            await callback.answer("✅ Пользователь удален")
        else:
            await callback.message.edit_text("❌ Ошибка при удалении пользователя")
            await callback.answer("❌ Ошибка")
    
    await state.clear()


# ============ РАСПРЕДЕЛЕНИЕ ИСПОЛНИТЕЛЕЙ ============

@router.message(F.text == "🔗 Распределение исполнителей")
async def admin_executor_buyer_management(message: Message):
    """Меню управления распределением исполнителей"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.answer("❌ У вас нет доступа к этой функции")
            return
        
        text = """
🔗 <b>РАСПРЕДЕЛЕНИЕ ИСПОЛНИТЕЛЕЙ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Здесь вы можете управлять назначениями исполнителей баерам.

<b>Возможности:</b>
• Назначить исполнителя конкретному баеру
• Удалить назначение
• Просмотреть все назначения
• Просмотреть назначения по баерам или исполнителям

Выберите действие:
"""
        
        await message.answer(
            text,
            reply_markup=AdminKeyboards.executor_buyer_management(),
            parse_mode="HTML"
        )
        logger.info(f"Админ {user.telegram_id} открыл меню распределения исполнителей")


@router.callback_query(F.data == "admin_assignments_menu")
async def callback_assignments_menu(callback: CallbackQuery):
    """Возврат в меню распределения"""
    await callback.message.edit_text(
        """
🔗 <b>РАСПРЕДЕЛЕНИЕ ИСПОЛНИТЕЛЕЙ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Здесь вы можете управлять назначениями исполнителей баерам.

<b>Возможности:</b>
• Назначить исполнителя конкретному баеру
• Удалить назначение
• Просмотреть все назначения
• Просмотреть назначения по баерам или исполнителям

Выберите действие:
""",
        reply_markup=AdminKeyboards.executor_buyer_management(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_assign_executor")
async def callback_assign_executor(callback: CallbackQuery, state: FSMContext):
    """Начало процесса назначения исполнителя баеру (оптимизировано)"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        # Получаем всех баеров (максимум 100 для безопасности)
        buyers = await UserQueries.get_all_users(session, role=UserRole.BUYER, active_only=True, page=1, per_page=100)
        
        if not buyers:
            await callback.message.edit_text(
                "❌ <b>Нет доступных баеров</b>\n\n"
                "В системе нет зарегистрированных баеров.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = """
🔗 <b>НАЗНАЧЕНИЕ ИСПОЛНИТЕЛЯ БАЕРУ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 1/2: Выберите баера</b>

Выберите баера, которому хотите назначить исполнителя:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.buyer_list_for_assignment(buyers),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_buyer_selection)
        await callback.answer()


@router.callback_query(F.data.startswith("admin_select_buyer_"), AdminStates.waiting_buyer_selection)
async def callback_select_buyer(callback: CallbackQuery, state: FSMContext):
    """Выбор баера для назначения"""
    buyer_id = int(callback.data.replace("admin_select_buyer_", ""))
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not buyer or buyer.role != UserRole.BUYER:
            await callback.answer("❌ Баер не найден", show_alert=True)
            return
        
        # Получаем всех исполнителей (максимум 100 для безопасности)
        all_executors = await UserQueries.get_all_users(session, role=UserRole.EXECUTOR, active_only=True, page=1, per_page=100)
        
        if not all_executors:
            await callback.message.edit_text(
                "❌ <b>Нет доступных исполнителей</b>\n\n"
                "В системе нет зарегистрированных исполнителей.",
                parse_mode="HTML"
            )
            await callback.answer()
            await state.clear()
            return
        
        # Получаем уже назначенных исполнителей для этого баера
        assigned_executors = await UserQueries.get_executors_for_buyer(session, buyer_id)
        assigned_executor_ids = {executor.id for executor in assigned_executors}
        
        # Фильтруем: исключаем уже назначенных исполнителей
        available_executors = [executor for executor in all_executors if executor.id not in assigned_executor_ids]
        
        if not available_executors:
            buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
            await callback.message.edit_text(
                f"✅ <b>ВСЕ ИСПОЛНИТЕЛИ УЖЕ НАЗНАЧЕНЫ</b>\n\n"
                f"Все доступные исполнители уже назначены баеру <b>{buyer_name}</b>.\n\n"
                f"Нет доступных исполнителей для назначения.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            await state.clear()
            return
        
        # Сохраняем выбранного баера
        await state.update_data(selected_buyer_id=buyer_id, selected_buyer_name=f"{buyer.first_name} {buyer.last_name or ''}".strip())
        
        buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
        text = f"""
🔗 <b>НАЗНАЧЕНИЕ ИСПОЛНИТЕЛЯ БАЕРУ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Выбранный баер:</b> {buyer_name}

<b>Шаг 2/2: Выберите исполнителя</b>

Выберите исполнителя для назначения:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.executor_list_for_assignment(available_executors),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_executor_selection)
        await callback.answer()


@router.callback_query(F.data.startswith("admin_select_executor_"), AdminStates.waiting_executor_selection)
async def callback_select_executor(callback: CallbackQuery, state: FSMContext):
    """Выбор исполнителя для назначения"""
    executor_id = int(callback.data.replace("admin_select_executor_", ""))
    
    async with AsyncSessionLocal() as session:
        data = await state.get_data()
        buyer_id = data.get('selected_buyer_id')
        buyer_name = data.get('selected_buyer_name', 'Баер')
        
        executor = await UserQueries.get_user_by_id(session, executor_id)
        
        if not executor or executor.role != UserRole.EXECUTOR:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        # Сохраняем данные для подтверждения
        await state.update_data(selected_executor_id=executor_id)
        
        executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()
        direction = executor.direction.value if executor.direction else "не указано"
        
        text = f"""
🔗 <b>ПОДТВЕРЖДЕНИЕ НАЗНАЧЕНИЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Баер:</b> {buyer_name}
<b>Исполнитель:</b> {executor_name}
<b>Направление:</b> {direction}

После подтверждения исполнитель <b>{executor_name}</b> будет назначен баеру <b>{buyer_name}</b>.
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.confirm_assignment(executor_id, buyer_id),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_assignment_confirm)
        await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_assign_"), AdminStates.waiting_assignment_confirm)
async def callback_confirm_assignment(callback: CallbackQuery, state: FSMContext):
    """Подтверждение назначения"""
    parts = callback.data.replace("admin_confirm_assign_", "").split("_")
    executor_id = int(parts[0])
    buyer_id = int(parts[1])
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not admin or admin.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        executor = await UserQueries.get_user_by_id(session, executor_id)
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not executor or not buyer:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Создаем назначение
        success = await UserQueries.assign_executor_to_buyer(
            session,
            executor_id=executor_id,
            buyer_id=buyer_id,
            created_by_id=admin.id
        )
        
        if success:
            executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()
            buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
            
            await callback.message.edit_text(
                f"✅ <b>НАЗНАЧЕНИЕ СОЗДАНО</b>\n\n"
                f"Исполнитель <b>{executor_name}</b> успешно назначен баеру <b>{buyer_name}</b>.\n\n"
                f"Теперь исполнитель может получать задачи только от этого баера.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            
            logger.info(f"Админ {admin.telegram_id} назначил исполнителя {executor_id} баеру {buyer_id}")
            await callback.answer("✅ Назначение создано")
        else:
            await callback.message.edit_text(
                "❌ <b>ОШИБКА ПРИ СОЗДАНИИ НАЗНАЧЕНИЯ</b>\n\n"
                "Не удалось создать назначение. Возможно, оно уже существует.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer("❌ Ошибка", show_alert=True)
        
        await state.clear()


async def _show_assignments_list(callback: CallbackQuery, page: int = 1):
    """Вспомогательная функция для отображения списка назначений"""
    async with AsyncSessionLocal() as session:
        user = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        # Получаем все назначения
        assignments = await UserQueries.get_all_assignments(session)
        
        if not assignments:
            await callback.message.edit_text(
                "📋 <b>НЕТ НАЗНАЧЕНИЙ</b>\n\n"
                "В системе пока нет назначений исполнителей баерам.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем список назначений с именами
        assignments_list = []
        for assignment in assignments:
            executor = await UserQueries.get_user_by_id(session, assignment['executor_id'])
            buyer = await UserQueries.get_user_by_id(session, assignment['buyer_id'])
            
            if executor and buyer:
                assignments_list.append({
                    'executor_id': assignment['executor_id'],
                    'buyer_id': assignment['buyer_id'],
                    'executor_name': f"{executor.first_name} {executor.last_name or ''}".strip(),
                    'buyer_name': f"{buyer.first_name} {buyer.last_name or ''}".strip(),
                    'created_at': assignment['created_at']
                })
        
        # Формируем текст
        total_pages = (len(assignments_list) + 4) // 5  # per_page = 5
        text = f"""
📋 <b>ВСЕ НАЗНАЧЕНИЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Всего назначений:</b> {len(assignments_list)}
<b>Страница:</b> {page}/{total_pages}

Выберите назначение для просмотра:
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.assignment_list(assignments_list, page=page, per_page=5),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data == "admin_view_assignments")
async def callback_view_assignments(callback: CallbackQuery):
    """Просмотр всех назначений"""
    await _show_assignments_list(callback, page=1)


@router.callback_query(F.data.startswith("admin_assignments_page_"))
async def callback_assignments_page(callback: CallbackQuery):
    """Навигация по страницам назначений"""
    page = int(callback.data.replace("admin_assignments_page_", ""))
    await _show_assignments_list(callback, page=page)


@router.callback_query(F.data.startswith("admin_view_assignment_"))
async def callback_view_assignment(callback: CallbackQuery):
    """Просмотр конкретного назначения"""
    parts = callback.data.replace("admin_view_assignment_", "").split("_")
    executor_id = int(parts[0])
    buyer_id = int(parts[1])
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_id(session, executor_id)
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not executor or not buyer:
            await callback.answer("❌ Назначение не найдено", show_alert=True)
            return
        
        executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()
        buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
        direction = executor.direction.value if executor.direction else "не указано"
        
        text = f"""
📋 <b>НАЗНАЧЕНИЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Исполнитель:</b> {executor_name}
<b>Направление:</b> {direction}
<b>Баер:</b> {buyer_name}

Исполнитель может получать задачи только от этого баера.
"""
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.assignment_actions(executor_id, buyer_id),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data == "admin_remove_assignment")
async def callback_remove_assignment_menu(callback: CallbackQuery):
    """Меню удаления назначения - показываем список назначений"""
    await callback_view_assignments(callback)


@router.callback_query(F.data.startswith("admin_remove_assignment_"))
async def callback_remove_assignment(callback: CallbackQuery):
    """Удаление назначения"""
    try:
        # Извлекаем ID из callback_data: "admin_remove_assignment_1_2" -> ["1", "2"]
        data_str = callback.data.replace("admin_remove_assignment_", "")
        parts = data_str.split("_")
        
        if len(parts) < 2:
            await callback.answer("❌ Ошибка: неверный формат данных", show_alert=True)
            return
        
        executor_id = int(parts[0])
        buyer_id = int(parts[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга callback_data для удаления назначения: {callback.data}, ошибка: {e}")
        await callback.answer("❌ Ошибка при обработке запроса", show_alert=True)
        return
    
    async with AsyncSessionLocal() as session:
        admin = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        
        if not admin or admin.role != UserRole.ADMIN:
            await callback.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        executor = await UserQueries.get_user_by_id(session, executor_id)
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not executor or not buyer:
            await callback.answer("❌ Назначение не найдено", show_alert=True)
            return
        
        # Удаляем назначение
        success = await UserQueries.remove_executor_from_buyer(session, executor_id, buyer_id)
        
        if success:
            executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()
            buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
            
            await callback.message.edit_text(
                f"✅ <b>НАЗНАЧЕНИЕ УДАЛЕНО</b>\n\n"
                f"Назначение исполнителя <b>{executor_name}</b> баеру <b>{buyer_name}</b> удалено.\n\n"
                f"Теперь исполнитель может получать задачи от всех баеров.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            
            logger.info(f"Админ {admin.telegram_id} удалил назначение исполнителя {executor_id} баеру {buyer_id}")
            await callback.answer("✅ Назначение удалено")
        else:
            await callback.answer("❌ Ошибка при удалении. Назначение не найдено.", show_alert=True)


async def _show_buyers_list(callback: CallbackQuery, page: int = 1):
    """Вспомогательная функция для отображения списка баеров с пагинацией"""
    async with AsyncSessionLocal() as session:
        buyers = await UserQueries.get_all_users(session, role=UserRole.BUYER, active_only=True)
        
        if not buyers:
            await callback.message.edit_text(
                "❌ <b>НЕТ БАЕРОВ</b>\n\n"
                "В системе нет зарегистрированных баеров.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Получаем количество исполнителей для каждого баера
        buyers_with_counts = []
        for buyer in buyers:
            executors = await UserQueries.get_executors_for_buyer(session, buyer.id)
            buyers_with_counts.append((buyer, len(executors)))
        
        total_pages = (len(buyers_with_counts) + 4) // 5  # per_page = 5
        text = f"""
📋 <b>НАЗНАЧЕНИЯ ПО БАЕРАМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Всего баеров:</b> {len(buyers_with_counts)}
<b>Страница:</b> {page}/{total_pages}

Выберите баера для просмотра его исполнителей:
"""
        
        # Создаем список для клавиатуры (только баеры, без счетчиков в кнопках)
        buyers_list = [buyer for buyer, _ in buyers_with_counts]
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.buyers_list_with_pagination(buyers_list, page=page, per_page=5),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data == "admin_assignments_by_buyer")
async def callback_assignments_by_buyer(callback: CallbackQuery):
    """Просмотр назначений по баерам"""
    await _show_buyers_list(callback, page=1)


@router.callback_query(F.data.startswith("admin_buyers_list_page_"))
async def callback_buyers_list_page(callback: CallbackQuery):
    """Навигация по страницам списка баеров"""
    page = int(callback.data.replace("admin_buyers_list_page_", ""))
    await _show_buyers_list(callback, page=page)


@router.callback_query(F.data.startswith("admin_view_buyer_executors_"))
async def callback_view_buyer_executors(callback: CallbackQuery):
    """Просмотр исполнителей конкретного баера"""
    buyer_id = int(callback.data.replace("admin_view_buyer_executors_", ""))
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_id(session, buyer_id)
        
        if not buyer:
            await callback.answer("❌ Баер не найден", show_alert=True)
            return
        
        executors = await UserQueries.get_executors_for_buyer(session, buyer_id)
        buyer_name = f"{buyer.first_name} {buyer.last_name or ''}".strip()
        
        if not executors:
            text = f"""
📋 <b>ИСПОЛНИТЕЛИ БАЕРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Баер:</b> {buyer_name}

❌ У этого баера нет назначенных исполнителей.
"""
            await callback.message.edit_text(
                text,
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = f"""
📋 <b>ИСПОЛНИТЕЛИ БАЕРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Баер:</b> {buyer_name}
<b>Количество исполнителей:</b> {len(executors)}

<b>Список исполнителей:</b>
"""
        
        for executor in executors:
            direction = executor.direction.value if executor.direction else "не указано"
            text += f"• {executor.first_name} {executor.last_name or ''} ({direction})\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.executor_buyer_management(),
            parse_mode="HTML"
        )
        await callback.answer()


async def _show_executors_list(callback: CallbackQuery, page: int = 1):
    """Вспомогательная функция для отображения списка исполнителей с пагинацией"""
    async with AsyncSessionLocal() as session:
        executors = await UserQueries.get_all_users(session, role=UserRole.EXECUTOR, active_only=True)
        
        if not executors:
            await callback.message.edit_text(
                "❌ <b>НЕТ ИСПОЛНИТЕЛЕЙ</b>\n\n"
                "В системе нет зарегистрированных исполнителей.",
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Получаем количество баеров для каждого исполнителя
        executors_with_counts = []
        for executor in executors:
            buyers = await UserQueries.get_buyers_for_executor(session, executor.id)
            executors_with_counts.append((executor, len(buyers)))
        
        total_pages = (len(executors_with_counts) + 4) // 5  # per_page = 5
        text = f"""
📋 <b>НАЗНАЧЕНИЯ ПО ИСПОЛНИТЕЛЯМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Всего исполнителей:</b> {len(executors_with_counts)}
<b>Страница:</b> {page}/{total_pages}

Выберите исполнителя для просмотра его баеров:
"""
        
        # Создаем список для клавиатуры (только исполнители, без счетчиков в кнопках)
        executors_list = [executor for executor, _ in executors_with_counts]
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.executors_list_with_pagination(executors_list, page=page, per_page=5),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data == "admin_assignments_by_executor")
async def callback_assignments_by_executor(callback: CallbackQuery):
    """Просмотр назначений по исполнителям"""
    await _show_executors_list(callback, page=1)


@router.callback_query(F.data.startswith("admin_executors_list_page_"))
async def callback_executors_list_page(callback: CallbackQuery):
    """Навигация по страницам списка исполнителей"""
    page = int(callback.data.replace("admin_executors_list_page_", ""))
    await _show_executors_list(callback, page=page)


@router.callback_query(F.data.startswith("admin_view_executor_buyers_"))
async def callback_view_executor_buyers(callback: CallbackQuery):
    """Просмотр баеров конкретного исполнителя"""
    executor_id = int(callback.data.replace("admin_view_executor_buyers_", ""))
    
    async with AsyncSessionLocal() as session:
        executor = await UserQueries.get_user_by_id(session, executor_id)
        
        if not executor:
            await callback.answer("❌ Исполнитель не найден", show_alert=True)
            return
        
        buyers = await UserQueries.get_buyers_for_executor(session, executor_id)
        executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()
        
        if not buyers:
            text = f"""
📋 <b>БАЕРЫ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Исполнитель:</b> {executor_name}

❌ У этого исполнителя нет назначенных баеров.
Он может получать задачи от всех баеров.
"""
            await callback.message.edit_text(
                text,
                reply_markup=AdminKeyboards.executor_buyer_management(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = f"""
📋 <b>БАЕРЫ ИСПОЛНИТЕЛЯ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Исполнитель:</b> {executor_name}
<b>Количество баеров:</b> {len(buyers)}

<b>Список баеров:</b>
"""
        
        for buyer in buyers:
            text += f"• {buyer.first_name} {buyer.last_name or ''}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboards.executor_buyer_management(),
            parse_mode="HTML"
        )
        await callback.answer()
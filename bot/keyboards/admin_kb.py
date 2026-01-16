"""Клавиатуры для администратора"""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List
from db.models import User, UserRole


class AdminKeyboards:
    """Клавиатуры для администратора"""
    
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Главное меню администратора"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="📝 Заявки")
        builder.button(text="👥 Управление пользователями")
        builder.button(text="🔗 Распределение исполнителей")
        builder.button(text="📊 Статистика")
        builder.button(text="📋 Все задачи")
        builder.button(text="⚙️ Настройки каналов логов")
        builder.button(text="👤 Мой профиль")
        builder.adjust(2, 2, 2, 2, 1)
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def user_management() -> InlineKeyboardMarkup:
        """Управление пользователями"""
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить пользователя", callback_data="admin_add_user")
        builder.button(text="✏️ Редактировать пользователя", callback_data="admin_edit_user")
        builder.button(text="🗑 Удалить пользователя", callback_data="admin_delete_user")
        builder.button(text="📋 Список пользователей", callback_data="admin_list_users")
        builder.button(text="🚫 Неактивные пользователи", callback_data="admin_list_inactive_users")
        builder.button(text="◀️ Назад", callback_data="admin_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def role_selector() -> InlineKeyboardMarkup:
        """Выбор роли пользователя"""
        builder = InlineKeyboardBuilder()
        builder.button(text="👔 Байер (Buyer)", callback_data="role_buyer")
        builder.button(text="🛠️ Исполнитель (Executor)", callback_data="role_executor")
        builder.button(text="👑 Администратор", callback_data="role_admin")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def direction_selector() -> InlineKeyboardMarkup:
        """Выбор направления для исполнителя"""
        builder = InlineKeyboardBuilder()
        builder.button(text="🎨 Дизайн", callback_data="direction_design")
        builder.button(text="🏢 Агенство", callback_data="direction_agency")
        builder.button(text="✍️ Копирайтинг", callback_data="direction_copywriting")
        builder.button(text="📱 Маркетинг", callback_data="direction_marketing")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(2, 2, 1)
        return builder.as_markup()
    
    @staticmethod
    def user_list(users: List[User], page: int = 1, per_page: int = 10, total_count: int = None) -> InlineKeyboardMarkup:
        """Список пользователей с пагинацией (оптимизировано)"""
        builder = InlineKeyboardBuilder()
        
        # Теперь users - это уже только страница, не нужна нарезка
        for user in users:
            role_emoji = {
                UserRole.ADMIN: "👑",
                UserRole.BUYER: "👔",
                UserRole.EXECUTOR: "🛠️"
            }.get(user.role, "👤")
            
            status = "✅" if user.is_active else "❌"
            direction = f" ({user.direction.value})" if user.direction else ""
            
            text = f"{role_emoji} {status} {user.first_name or 'User'} {user.last_name or ''}{direction}"
            builder.button(text=text, callback_data=f"admin_view_user_{user.id}")
        
        # Пагинация - используем total_count если передан, иначе считаем по старому
        if total_count is not None:
            total_pages = (total_count + per_page - 1) // per_page
        else:
            total_pages = (len(users) + per_page - 1) // per_page
        
        nav_buttons = []
        
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_users_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page_{page+1}"))
        
        builder.adjust(1)
        builder.row(*nav_buttons)
        builder.button(text="❌ Закрыть", callback_data="cancel")
        
        return builder.as_markup()
    
    @staticmethod
    def user_actions(user_id: int, is_active: bool = True, role: UserRole = None) -> InlineKeyboardMarkup:
        """Действия с пользователем"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Изменить имя", callback_data=f"admin_change_name_{user_id}")
        builder.button(text="✏️ Изменить роль", callback_data=f"admin_change_role_{user_id}")
        
        # Показывать направление только для исполнителей
        if role == UserRole.EXECUTOR:
            builder.button(text="🔄 Изменить направление", callback_data=f"admin_change_direction_{user_id}")
        
        # Динамическая кнопка активации/деактивации
        if is_active:
            builder.button(text="🔴 Деактивировать", callback_data=f"admin_deactivate_{user_id}")
        else:
            builder.button(text="🟢 Активировать", callback_data=f"admin_deactivate_{user_id}")
        
        builder.button(text="🗑 Удалить", callback_data=f"admin_confirm_delete_{user_id}")
        builder.button(text="◀️ Назад", callback_data="admin_list_users")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def statistics_menu() -> InlineKeyboardMarkup:
        """Меню статистики"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Общая статистика", callback_data="stats_general")
        builder.button(text="👥 Статистика по пользователям", callback_data="stats_users")
        builder.button(text="📋 Статистика по задачам", callback_data="stats_tasks")
        builder.button(text="📈 По направлениям", callback_data="stats_directions")
        builder.button(text="📅 За период", callback_data="stats_period")
        builder.button(text="◀️ Назад", callback_data="admin_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def period_selector() -> InlineKeyboardMarkup:
        """Выбор периода для статистики"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Сегодня", callback_data="period_today")
        builder.button(text="📆 Неделя", callback_data="period_week")
        builder.button(text="📆 Месяц", callback_data="period_month")
        builder.button(text="📆 Квартал", callback_data="period_quarter")
        builder.button(text="📆 Год", callback_data="period_year")
        builder.button(text="📆 Весь период", callback_data="period_all")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(2, 2, 2, 1)
        return builder.as_markup()
    
    @staticmethod
    def log_channel_management() -> InlineKeyboardMarkup:
        """Управление каналами логов"""
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить канал", callback_data="admin_add_channel")
        builder.button(text="📋 Список каналов", callback_data="admin_list_channels")
        builder.button(text="◀️ Назад", callback_data="admin_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def channel_list(channels: List) -> InlineKeyboardMarkup:
        """Список каналов с возможностью удаления"""
        builder = InlineKeyboardBuilder()
        
        if not channels:
            builder.button(text="❌ Каналы не добавлены", callback_data="noop")
        else:
            for channel in channels:
                channel_name = channel.channel_name if channel.channel_name else f"Канал {channel.channel_id}"
                text = f"📢 {channel_name}"
                builder.button(text=text, callback_data=f"admin_view_channel_{channel.id}")
        
        builder.adjust(1)
        builder.button(text="◀️ Назад", callback_data="admin_channels_menu")
        
        return builder.as_markup()
    
    @staticmethod
    def channel_actions(channel_id: int, db_channel_id: int) -> InlineKeyboardMarkup:
        """Действия с каналом"""
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить канал", callback_data=f"admin_delete_channel_{db_channel_id}")
        builder.button(text="◀️ Назад к списку", callback_data="admin_list_channels")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def application_list(applications: List[User]) -> InlineKeyboardMarkup:
        """Список заявок (пользователей без роли)"""
        builder = InlineKeyboardBuilder()
        
        for user in applications:
            status = "✅" if user.is_active else "❌"
            username = f"@{user.username}" if user.username else "нет username"
            
            text = f"{status} {user.first_name or 'User'} {user.last_name or ''} ({username})"
            builder.button(text=text, callback_data=f"admin_view_application_{user.id}")
        
        builder.adjust(1)
        builder.button(text="🔄 Обновить", callback_data="admin_applications")
        builder.button(text="❌ Закрыть", callback_data="cancel")
        
        return builder.as_markup()
    
    @staticmethod
    def application_actions(user_id: int) -> InlineKeyboardMarkup:
        """Действия с заявкой"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Принять заявку", callback_data=f"admin_accept_application_{user_id}")
        builder.button(text="❌ Отклонить заявку", callback_data=f"admin_reject_application_{user_id}")
        builder.button(text="◀️ Назад к списку", callback_data="admin_applications")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def quick_application_actions(user_id: int) -> InlineKeyboardMarkup:
        """Быстрые действия с заявкой (для уведомлений)"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Принять", callback_data=f"admin_accept_application_{user_id}")
        builder.button(text="❌ Отклонить", callback_data=f"admin_reject_application_{user_id}")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def task_list(tasks: List, page: int = 1, per_page: int = 10) -> InlineKeyboardMarkup:
        """Список задач администратора"""
        builder = InlineKeyboardBuilder()
        
        start = (page - 1) * per_page
        end = start + per_page
        page_tasks = tasks[start:end]
        
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.IN_PROGRESS: "🟡",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.APPROVED: "🎉",
            TaskStatus.REJECTED: "❌",
            TaskStatus.CANCELLED: "🚫"
        }
        
        for task in page_tasks:
            emoji = status_emoji.get(task.status, "📋")
            
            builder.button(
                text=f"{emoji} {task.task_number}: {task.title[:30]}...",
                callback_data=f"admin_view_task_{task.id}"
            )
        
        # Пагинация
        total_pages = (len(tasks) + per_page - 1) // per_page
        nav_buttons = []
        
        from aiogram.types import InlineKeyboardButton
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_tasks_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_tasks_page_{page+1}"))
        
        builder.adjust(1)
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.button(text="🔄 Обновить", callback_data="admin_refresh_tasks")
        builder.button(text="❌ Закрыть", callback_data="cancel")
        
        return builder.as_markup()
    
    @staticmethod
    def task_actions(task_id: int, status) -> InlineKeyboardMarkup:
        """Действия с задачей для администратора"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Детали задачи", callback_data=f"admin_task_details_{task_id}")
        builder.button(text="📎 Файлы задачи", callback_data=f"admin_view_files_{task_id}")
        builder.button(text="💬 История сообщений", callback_data=f"admin_view_messages_{task_id}")
        builder.button(text="◀️ Назад к списку", callback_data="admin_all_tasks")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def task_files_actions(task_id: int, files: List) -> InlineKeyboardMarkup:
        """Действия с файлами задачи для администратора"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для скачивания файлов (первые 10)
        for file in files[:10]:
            file_name_short = file.file_name[:30] + "..." if len(file.file_name) > 30 else file.file_name
            builder.button(
                text=f"📥 {file_name_short}",
                callback_data=f"admin_download_file_{file.id}"
            )
        
        builder.button(text="◀️ Назад к задаче", callback_data=f"admin_view_task_{task_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def executor_buyer_management() -> InlineKeyboardMarkup:
        """Меню управления распределением исполнителей"""
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Назначить исполнителя баеру", callback_data="admin_assign_executor")
        builder.button(text="🗑 Удалить назначение", callback_data="admin_remove_assignment")
        builder.button(text="📋 Просмотр назначений", callback_data="admin_view_assignments")
        builder.button(text="👔 По баерам", callback_data="admin_assignments_by_buyer")
        builder.button(text="🛠️ По исполнителям", callback_data="admin_assignments_by_executor")
        builder.button(text="◀️ Назад", callback_data="admin_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def buyer_list_for_assignment(buyers: List[User], page: int = 1, per_page: int = 10) -> InlineKeyboardMarkup:
        """Список баеров для назначения исполнителя"""
        builder = InlineKeyboardBuilder()
        
        start = (page - 1) * per_page
        end = start + per_page
        page_buyers = buyers[start:end]
        
        for buyer in page_buyers:
            name = f"{buyer.first_name or 'User'} {buyer.last_name or ''}".strip()
            text = f"👔 {name}"
            builder.button(text=text, callback_data=f"admin_select_buyer_{buyer.id}")
        
        # Пагинация
        total_pages = (len(buyers) + per_page - 1) // per_page
        nav_buttons = []
        
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_buyers_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_buyers_page_{page+1}"))
        
        builder.adjust(1)
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.button(text="❌ Отменить", callback_data="admin_assignments_menu")
        
        return builder.as_markup()
    
    @staticmethod
    def executor_list_for_assignment(executors: List[User], page: int = 1, per_page: int = 10) -> InlineKeyboardMarkup:
        """Список исполнителей для назначения баеру"""
        builder = InlineKeyboardBuilder()
        
        start = (page - 1) * per_page
        end = start + per_page
        page_executors = executors[start:end]
        
        for executor in page_executors:
            name = f"{executor.first_name or 'User'} {executor.last_name or ''}".strip()
            direction = f" ({executor.direction.value})" if executor.direction else ""
            text = f"🛠️ {name}{direction}"
            builder.button(text=text, callback_data=f"admin_select_executor_{executor.id}")
        
        # Пагинация
        total_pages = (len(executors) + per_page - 1) // per_page
        nav_buttons = []
        
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_executors_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_executors_page_{page+1}"))
        
        builder.adjust(1)
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.button(text="❌ Отменить", callback_data="admin_assignments_menu")
        
        return builder.as_markup()
    
    @staticmethod
    def confirm_assignment(executor_id: int, buyer_id: int) -> InlineKeyboardMarkup:
        """Подтверждение назначения"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить", callback_data=f"admin_confirm_assign_{executor_id}_{buyer_id}")
        builder.button(text="❌ Отменить", callback_data="admin_assignments_menu")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def assignment_list(assignments: List[dict], page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список назначений для просмотра/удаления"""
        builder = InlineKeyboardBuilder()
        
        start = (page - 1) * per_page
        end = start + per_page
        page_assignments = assignments[start:end]
        
        for assignment in page_assignments:
            executor_name = assignment.get('executor_name', 'Исполнитель')
            buyer_name = assignment.get('buyer_name', 'Баер')
            text = f"🛠️ {executor_name} → 👔 {buyer_name}"
            builder.button(
                text=text,
                callback_data=f"admin_view_assignment_{assignment.get('executor_id')}_{assignment.get('buyer_id')}"
            )
        
        # Пагинация
        total_pages = (len(assignments) + per_page - 1) // per_page if assignments else 1
        nav_buttons = []
        
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_assignments_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_assignments_page_{page+1}"))
        
        builder.adjust(1)
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.button(text="◀️ Назад", callback_data="admin_assignments_menu")
        
        return builder.as_markup()
    
    @staticmethod
    def assignment_actions(executor_id: int, buyer_id: int) -> InlineKeyboardMarkup:
        """Действия с назначением"""
        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить назначение", callback_data=f"admin_remove_assignment_{executor_id}_{buyer_id}")
        builder.button(text="◀️ Назад", callback_data="admin_view_assignments")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def buyers_list_with_pagination(buyers: List[User], page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
        """
        Оптимизированный список баеров с пагинацией
        """
        builder = InlineKeyboardBuilder()

        # Пагинация
        start = (page - 1) * per_page
        end = start + per_page
        page_buyers = buyers[start:end]

        for buyer in page_buyers:
            name = f"{buyer.first_name or 'User'} {buyer.last_name or ''}".strip()
            text = f"👔 {name}"
            builder.button(text=text, callback_data=f"admin_view_buyer_executors_{buyer.id}")

        # Кнопки навигации
        total_pages = (len(buyers) + per_page - 1) // per_page if buyers else 1
        if page > 1:
            builder.button(text="◀️", callback_data=f"admin_buyers_list_page_{page-1}")
        builder.button(text=f"{page}/{total_pages}", callback_data="page_info")
        if page < total_pages:
            builder.button(text="▶️", callback_data=f"admin_buyers_list_page_{page+1}")

        builder.adjust(1)
        builder.button(text="◀️ Назад", callback_data="admin_assignments_menu")

        return builder.as_markup()
    
    @staticmethod
    def executors_list_with_pagination(executors: List[User], page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
        """
        Оптимизированный список исполнителей с пагинацией
        """
        builder = InlineKeyboardBuilder()

        # Пагинация
        start = (page - 1) * per_page
        end = start + per_page
        page_executors = executors[start:end]

        for executor in page_executors:
            name = f"{executor.first_name or 'User'} {executor.last_name or ''}".strip()
            text = f"🛠️ {name}"
            builder.button(text=text, callback_data=f"admin_view_executor_buyers_{executor.id}")

        # Кнопки навигации
        total_pages = (len(executors) + per_page - 1) // per_page if executors else 1
        if page > 1:
            builder.button(text="◀️", callback_data=f"admin_executors_list_page_{page-1}")
        builder.button(text=f"{page}/{total_pages}", callback_data="page_info")
        if page < total_pages:
            builder.button(text="▶️", callback_data=f"admin_executors_list_page_{page+1}")

        builder.adjust(1)
        builder.button(text="◀️ Назад", callback_data="admin_assignments_menu")

        return builder.as_markup()

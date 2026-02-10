"""Клавиатуры для байера"""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List, Dict
from db.models import User, Task, DirectionType, TaskStatus, TaskPriority


class BuyerKeyboards:
    """Клавиатуры для байера"""
    
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Главное меню байера"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="➕ Создать задачу")
        builder.button(text="📋 Мои задачи")
        builder.button(text="✅ На проверке")
        builder.button(text="📊 Статистика")
        builder.button(text="💬 Чаты")
        builder.button(text="👤 Мой профиль")
        builder.adjust(2, 2, 2)
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def direction_with_executors(executors_by_direction: Dict[DirectionType, List[User]]) -> InlineKeyboardMarkup:
        """Выбор направления с отображением исполнителей"""
        builder = InlineKeyboardBuilder()
        
        direction_emojis = {
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
        
        for direction, executors in executors_by_direction.items():
            emoji = direction_emojis.get(direction, "📁")
            name = direction_names.get(direction, direction.value)
            count = len(executors)
            
            builder.button(
                text=f"{emoji} {name} ({count} исп.)",
                callback_data=f"buyer_direction_{direction.value}"
            )
        
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def direction_with_executors_with_back(executors_by_direction: Dict[DirectionType, List[User]], task_id: int) -> InlineKeyboardMarkup:
        """Выбор направления с отображением исполнителей (при редактировании задачи)"""
        builder = InlineKeyboardBuilder()
        
        direction_emojis = {
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
        
        for direction, executors in executors_by_direction.items():
            emoji = direction_emojis.get(direction, "📁")
            name = direction_names.get(direction, direction.value)
            count = len(executors)
            
            builder.button(
                text=f"{emoji} {name} ({count} исп.)",
                callback_data=f"buyer_direction_{direction.value}"
            )
        
        builder.button(text="◀️ Назад", callback_data=f"buyer_view_task_{task_id}")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def executor_list(executors: List[User], direction: DirectionType = None, is_editing: bool = False, task_id: int = None) -> InlineKeyboardMarkup:
        """Список исполнителей"""
        builder = InlineKeyboardBuilder()
        
        for executor in executors:
            name = f"{executor.first_name or 'User'} {executor.last_name or ''}".strip()
            # Показываем количество задач
            tasks_count = executor.current_load or 0
            text = f"👤 {name} • задач: {tasks_count}"
            
            builder.button(
                text=text,
                callback_data=f"buyer_select_executor_{executor.id}"
            )
        
        # Если редактируем существующую задачу, кнопка "Назад" должна возвращать к задаче
        if is_editing and task_id:
            builder.button(text="◀️ Назад", callback_data=f"buyer_view_task_{task_id}")
        else:
            builder.button(text="◀️ Назад", callback_data="buyer_back_to_directions")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def executor_list_all(executors: List[User]) -> InlineKeyboardMarkup:
        """Список всех исполнителей (без группировки по направлениям)"""
        builder = InlineKeyboardBuilder()
        
        for executor in executors:
            name = f"{executor.first_name or 'User'} {executor.last_name or ''}".strip()
            # Показываем количество задач
            tasks_count = executor.current_load or 0
            text = f"👤 {name} • задач: {tasks_count}"
            
            builder.button(
                text=text,
                callback_data=f"buyer_select_executor_{executor.id}"
            )
        
        builder.button(text="◀️ Назад", callback_data="buyer_back_to_directions")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def executor_list_all_with_back(executors: List[User], task_id: int) -> InlineKeyboardMarkup:
        """Список всех исполнителей с кнопкой назад к задаче"""
        builder = InlineKeyboardBuilder()
        
        for executor in executors:
            name = f"{executor.first_name or 'User'} {executor.last_name or ''}".strip()
            # Показываем количество задач
            tasks_count = executor.current_load or 0
            text = f"👤 {name} • задач: {tasks_count}"
            
            builder.button(
                text=text,
                callback_data=f"buyer_select_executor_{executor.id}"
            )
        
        builder.button(text="◀️ Назад", callback_data=f"buyer_view_task_{task_id}")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def task_creation_confirm(task_data: dict) -> InlineKeyboardMarkup:
        """Подтверждение создания задачи"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ ОТПРАВИТЬ", callback_data="buyer_confirm_create")
        builder.button(text="✏️ ИЗМЕНИТЬ", callback_data="buyer_edit_task")
        builder.button(text="❌ ОТМЕНИТЬ", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def task_created_view(task_id: int) -> InlineKeyboardMarkup:
        """Кнопка для перехода к только что созданной задаче"""
        builder = InlineKeyboardBuilder()
        builder.button(text="👁 Просмотреть задачу", callback_data=f"buyer_view_task_{task_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def edit_task_field() -> InlineKeyboardMarkup:
        """Выбор поля для редактирования"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📌 Название", callback_data="edit_field_title")
        builder.button(text="📝 Описание", callback_data="edit_field_description")
        builder.button(text="⏱️ Дедлайн", callback_data="edit_field_deadline")
        builder.button(text="📍 Приоритет", callback_data="edit_field_priority")
        builder.button(text="👤 Исполнитель", callback_data="edit_field_executor")
        builder.button(text="📎 Файлы", callback_data="edit_field_files")
        builder.button(text="◀️ Назад", callback_data="buyer_back_to_confirm")
        builder.adjust(2, 2, 1, 1, 1)
        return builder.as_markup()
    
    @staticmethod
    def my_tasks_filter() -> InlineKeyboardMarkup:
        """Фильтр моих задач"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Все задачи", callback_data="filter_all")
        builder.button(text="🟡 В работе", callback_data="filter_in_progress")
        builder.button(text="✅ На проверке", callback_data="filter_completed")
        builder.button(text="🎉 Одобренные", callback_data="filter_approved")
        builder.button(text="❌ Отмененные", callback_data="filter_cancelled")
        builder.button(text="◀️ Назад", callback_data="buyer_main")
        builder.adjust(2, 2, 1, 1)
        return builder.as_markup()
    
    @staticmethod
    def task_list(tasks: List[Task], page: int = 1, per_page: int = 5, total_count: int = None) -> InlineKeyboardMarkup:
        """Список задач байера (оптимизировано - без подсчета длины массива)"""
        builder = InlineKeyboardBuilder()
        
        # tasks уже содержит только нужные задачи для текущей страницы
        page_tasks = tasks
        
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
            executor_name = task.executor.first_name if task.executor else "Не назначен"
            
            builder.button(
                text=f"{emoji} {task.task_number}: {task.title[:30]}...",
                callback_data=f"buyer_view_task_{task.id}"
            )
        
        # Пагинация (используем total_count вместо len(tasks))
        if total_count is None:
            total_count = len(tasks)
        
        total_pages = (total_count + per_page - 1) // per_page
        nav_buttons = []
        if total_pages > 1:
            from aiogram.types import InlineKeyboardButton
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"buyer_tasks_page_{page-1}"))
            nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="page_info"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"buyer_tasks_page_{page+1}"))
        
        # Настраиваем расположение: все кнопки задач по одной в ряд
        builder.adjust(1)
        
        # Если есть пагинация, добавляем её кнопки в один ряд
        if nav_buttons:
            builder.row(*nav_buttons)
        
        # Добавляем кнопки управления
        builder.button(text="❌ Закрыть", callback_data="cancel")
        builder.adjust(1)
        
        return builder.as_markup()
    
    @staticmethod
    def task_actions(task_id: int, task_status: TaskStatus, executor_id: int = None) -> InlineKeyboardMarkup:
        """Действия с задачей"""
        builder = InlineKeyboardBuilder()
        
        if task_status == TaskStatus.PENDING:
            builder.button(text="✏️ Редактировать", callback_data=f"buyer_edit_task_{task_id}")
            builder.button(text="🗑 Отменить задачу", callback_data=f"buyer_cancel_task_{task_id}")
        
        if task_status == TaskStatus.COMPLETED:
            builder.button(text="✅ ПРИНЯТЬ", callback_data=f"buyer_approve_{task_id}")
            builder.button(text="✏️ ЗАПРОСИТЬ ПРАВКИ", callback_data=f"buyer_request_correction_{task_id}")
            builder.button(text="💬 ОБСУДИТЬ", callback_data=f"buyer_discuss_{task_id}")
        
        builder.button(text="📎 Файлы задачи", callback_data=f"buyer_view_files_{task_id}")
        builder.button(text="➕ Добавить файл", callback_data=f"buyer_add_file_{task_id}")
        
        # Если задача на проверке, кнопка "Назад" ведет к списку задач на проверке
        if task_status == TaskStatus.COMPLETED:
            builder.button(text="◀️ Назад к списку", callback_data="buyer_tasks_on_review")
        else:
            builder.button(text="◀️ Назад к списку", callback_data="buyer_my_tasks")
        
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def task_files_actions(task_id: int, files: List) -> InlineKeyboardMarkup:
        """Действия с файлами задачи"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для скачивания файлов (первые 10)
        for file in files[:10]:
            file_name_short = file.file_name[:30] + "..." if len(file.file_name) > 30 else file.file_name
            builder.button(
                text=f"📥 {file_name_short}",
                callback_data=f"buyer_download_file_{file.id}"
            )
        
        builder.button(text="◀️ Назад к задаче", callback_data=f"buyer_view_task_{task_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def review_result() -> InlineKeyboardMarkup:
        """Проверка результата"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ ПРИНЯТЬ", callback_data="review_approve")
        builder.button(text="✏️ ЗАПРОСИТЬ ПРАВКИ", callback_data="review_request_correction")
        builder.button(text="💬 ОБСУДИТЬ", callback_data="review_discuss")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def statistics_menu() -> InlineKeyboardMarkup:
        """Меню статистики для байера"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Общая статистика", callback_data="buyer_stats_general")
        builder.button(text="📋 По статусам задач", callback_data="buyer_stats_status")
        builder.button(text="📁 По направлениям", callback_data="buyer_stats_directions")
        builder.button(text="👥 По исполнителям", callback_data="buyer_stats_executors")
        builder.button(text="📅 За период", callback_data="buyer_stats_period")
        builder.button(text="❌ Закрыть", callback_data="cancel")
        builder.adjust(2, 2, 1, 1)
        return builder.as_markup()
    
    @staticmethod
    def period_selector() -> InlineKeyboardMarkup:
        """Выбор периода для статистики"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Сегодня", callback_data="buyer_period_today")
        builder.button(text="📅 Неделя", callback_data="buyer_period_week")
        builder.button(text="📅 Месяц", callback_data="buyer_period_month")
        builder.button(text="📅 Квартал", callback_data="buyer_period_quarter")
        builder.button(text="📅 Год", callback_data="buyer_period_year")
        builder.button(text="📅 Все время", callback_data="buyer_period_all")
        builder.button(text="◀️ Назад", callback_data="buyer_stats_menu")
        builder.adjust(2, 2, 2, 1)
        return builder.as_markup()


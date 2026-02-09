"""Клавиатуры для исполнителя"""
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List
from db.models import Task, TaskStatus


class ExecutorKeyboards:
    """Клавиатуры для исполнителя"""
    
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Главное меню исполнителя"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="📋 Мои задачи")
        builder.button(text="🆕 Новые задачи")
        builder.button(text="📊 Моя статистика")
        builder.button(text="👤 Мой профиль")
        builder.adjust(2, 2)
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def profile_actions(is_available: bool) -> InlineKeyboardMarkup:
        """
        Кнопки под профилем исполнителя.
        Позволяют переключать статус "Работаю / Не работаю".
        """
        builder = InlineKeyboardBuilder()
        if is_available:
            builder.button(text="🟢 Работаю (принимаю задачи)", callback_data="executor_toggle_availability")
        else:
            builder.button(text="🔴 Не работаю (не принимать задачи)", callback_data="executor_toggle_availability")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def new_task_notification(task_id: int, can_reject: bool = True) -> InlineKeyboardMarkup:
        """Уведомление о новой задаче"""
        builder = InlineKeyboardBuilder()
        builder.button(text="▶️ ВЗЯТЬ В РАБОТУ", callback_data=f"executor_take_{task_id}")
        if can_reject:
            builder.button(text="❌ ОТКАЗАТЬСЯ", callback_data=f"executor_reject_{task_id}")
        builder.button(text="💬 УТОЧНИТЬ", callback_data=f"executor_clarify_{task_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def task_taken_actions(task_id: int) -> InlineKeyboardMarkup:
        """Действия после взятия задачи"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 ОТКРЫТЬ ЗАДАЧУ", callback_data=f"executor_open_{task_id}")
        builder.button(text="💬 НАПИСАТЬ БАЙЕРУ", callback_data=f"executor_message_{task_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def task_management(task_id: int, task_status: TaskStatus, can_reject: bool = True) -> InlineKeyboardMarkup:
        """Управление задачей"""
        builder = InlineKeyboardBuilder()
        
        if task_status == TaskStatus.PENDING:
            # Новая задача - нужно принять или отказаться
            builder.button(text="▶️ ВЗЯТЬ В РАБОТУ", callback_data=f"executor_take_{task_id}")
            if can_reject:
                builder.button(text="❌ ОТКАЗАТЬСЯ", callback_data=f"executor_reject_{task_id}")
            builder.button(text="💬 УТОЧНИТЬ", callback_data=f"executor_clarify_{task_id}")
            builder.adjust(1)
        elif task_status == TaskStatus.IN_PROGRESS:
            # Задача в работе - можно выполнить или отказаться
            builder.button(text="✅ ВЫПОЛНИТЬ", callback_data=f"executor_complete_{task_id}")
            if can_reject:
                builder.button(text="❌ ОТКАЗАТЬСЯ", callback_data=f"executor_reject_{task_id}")
            builder.button(text="💬 СООБЩЕНИЕ", callback_data=f"executor_message_{task_id}")
            builder.button(text="📎 ДОБАВИТЬ ФАЙЛ", callback_data=f"executor_add_file_{task_id}")
            builder.button(text="📂 ПРОСМОТР ФАЙЛОВ", callback_data=f"executor_view_files_{task_id}")
            builder.button(text="📜 История сообщений", callback_data=f"executor_history_{task_id}")
            builder.button(text="◀️ Назад к задачам", callback_data="executor_my_tasks")
            # adjust(1, 1, 2, 2, 1, 1) - первая строка 1 кнопка (ВЫПОЛНИТЬ), вторая 1 кнопка (ОТКАЗАТЬСЯ если can_reject), затем по 2 кнопки, потом по 1
            if can_reject:
                builder.adjust(1, 1, 2, 2, 1)
            else:
                builder.adjust(1, 2, 2)
        elif task_status == TaskStatus.COMPLETED:
            # Задача выполнена, ждет проверки
            builder.button(text="💬 СООБЩЕНИЕ", callback_data=f"executor_message_{task_id}")
            builder.button(text="📂 ПРОСМОТР ФАЙЛОВ", callback_data=f"executor_view_files_{task_id}")
            builder.button(text="📜 История сообщений", callback_data=f"executor_history_{task_id}")
            builder.button(text="◀️ Назад к задачам", callback_data="executor_my_tasks")
            builder.adjust(1)
        else:
            # Для остальных статусов (APPROVED, REJECTED, CANCELLED)
            builder.button(text="📜 История сообщений", callback_data=f"executor_history_{task_id}")
            builder.button(text="◀️ Назад к задачам", callback_data="executor_my_tasks")
            builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def reject_reason() -> InlineKeyboardMarkup:
        """Причины отказа от задачи"""
        builder = InlineKeyboardBuilder()
        builder.button(text="1️⃣ Не хватает информации в ТЗ", callback_data="reject_lack_info")
        builder.button(text="2️⃣ Задача вне моей компетенции", callback_data="reject_out_of_scope")
        builder.button(text="3️⃣ Технические ограничения", callback_data="reject_tech_limitations")
        builder.button(text="4️⃣ Перегрузка по задачам", callback_data="reject_overload")
        builder.button(text="5️⃣ Другая причина", callback_data="reject_other")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def complete_task_actions(task_id: int) -> InlineKeyboardMarkup:
        """Действия при завершении задачи"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Добавить комментарий", callback_data=f"complete_add_comment_{task_id}")
        builder.button(text="📎 Прикрепить файлы", callback_data=f"complete_add_files_{task_id}")
        builder.button(text="🚀 ОТПРАВИТЬ БАЙЕРУ", callback_data=f"complete_send_{task_id}")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def my_tasks_filter() -> InlineKeyboardMarkup:
        """Фильтр моих задач"""
        builder = InlineKeyboardBuilder()
        builder.button(text="🟡 В работе", callback_data="executor_filter_in_progress")
        builder.button(text="✅ Завершенные", callback_data="executor_filter_completed")
        builder.button(text="📋 Все задачи", callback_data="executor_filter_all")
        builder.button(text="❌ Закрыть", callback_data="cancel")
        builder.adjust(2, 1, 1)
        return builder.as_markup()
    
    @staticmethod
    def task_list(tasks: List[Task], page: int = 1, per_page: int = 5, total_count: int = None, is_new_tasks: bool = False) -> InlineKeyboardMarkup:
        """Список задач исполнителя (оптимизировано)"""
        builder = InlineKeyboardBuilder()
        
        # tasks уже содержит только нужные задачи для текущей страницы
        page_tasks = tasks
        
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.IN_PROGRESS: "🟡",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.APPROVED: "🎉"
        }
        
        priority_emoji = {
            1: "🟢",
            2: "🟡",
            3: "🟠",
            4: "🔴"
        }
        
        for task in page_tasks:
            status = status_emoji.get(task.status, "📋")
            priority = priority_emoji.get(task.priority, "")
            
            builder.button(
                text=f"{status} {priority} {task.task_number}: {task.title[:25]}...",
                callback_data=f"executor_view_task_{task.id}"
            )
        
        # Пагинация (используем total_count вместо len(tasks))
        if total_count is None:
            total_count = len(tasks)
        
        total_pages = (total_count + per_page - 1) // per_page
        nav_buttons = []
        if total_pages > 1:
            # Используем разные callback в зависимости от типа списка
            page_prefix = "executor_new_tasks_page_" if is_new_tasks else "executor_tasks_page_"
            if page > 1:
                nav_buttons.append(("◀️", f"{page_prefix}{page-1}"))
            nav_buttons.append((f"{page}/{total_pages}", "page_info"))
            if page < total_pages:
                nav_buttons.append(("▶️", f"{page_prefix}{page+1}"))
            
            for text, callback in nav_buttons:
                builder.button(text=text, callback_data=callback)
        
        builder.button(text="❌ Закрыть", callback_data="cancel")
        
        # Настраиваем расположение: задачи по 1 в строке, навигация в одну строку, закрыть отдельно
        num_task_buttons = len(page_tasks)
        num_nav_buttons = len(nav_buttons)
        # adjust принимает кортеж: количество кнопок в каждой строке
        # Задачи по 1 в строке, навигация в 1 строку, закрыть отдельно
        if num_nav_buttons > 0:
            builder.adjust(*(1,) * num_task_buttons, num_nav_buttons, 1)
        else:
            builder.adjust(*(1,) * num_task_buttons, 1)
        
        return builder.as_markup()
    
    @staticmethod
    def message_actions() -> InlineKeyboardMarkup:
        """Действия с сообщением"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📎 Прикрепить файл", callback_data="message_attach_file")
        builder.button(text="✅ Отправить", callback_data="message_send")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(2, 1)
        return builder.as_markup()
    
    @staticmethod
    def task_files_actions(task_id: int, files: List) -> InlineKeyboardMarkup:
        """Действия с файлами задачи для исполнителя"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для скачивания файлов (первые 10)
        for file in files[:10]:
            file_name_short = file.file_name[:30] + "..." if len(file.file_name) > 30 else file.file_name
            builder.button(
                text=f"📥 {file_name_short}",
                callback_data=f"executor_download_file_{file.id}"
            )
        
        builder.button(text="◀️ Назад к задаче", callback_data=f"executor_view_task_{task_id}")
        builder.adjust(1)
        return builder.as_markup()


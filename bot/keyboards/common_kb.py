"""Общие клавиатуры для всех ролей"""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List


class CommonKeyboards:
    """Общие клавиатуры"""
    
    @staticmethod
    def cancel() -> InlineKeyboardMarkup:
        """Кнопка отмены"""
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отменить", callback_data="cancel")
        return builder.as_markup()
    
    @staticmethod
    def back_and_cancel() -> InlineKeyboardMarkup:
        """Кнопки назад и отмена"""
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="back")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def confirm_action(action: str, data: str = "") -> InlineKeyboardMarkup:
        """Подтверждение действия"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить", callback_data=f"confirm_{action}:{data}")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def yes_no(callback_prefix: str) -> InlineKeyboardMarkup:
        """Да/Нет"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да", callback_data=f"{callback_prefix}_yes")
        builder.button(text="❌ Нет", callback_data=f"{callback_prefix}_no")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def priority_selector() -> InlineKeyboardMarkup:
        """Выбор приоритета задачи"""
        builder = InlineKeyboardBuilder()
        builder.button(text="🟢 Низкий", callback_data="priority_1")
        builder.button(text="🟡 Средний", callback_data="priority_2")
        builder.button(text="🟠 Высокий", callback_data="priority_3")
        builder.button(text="🔴 Срочный", callback_data="priority_4")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def rating_selector() -> InlineKeyboardMarkup:
        """Выбор оценки (1-5 звезд)"""
        builder = InlineKeyboardBuilder()
        builder.button(text="⭐️", callback_data="rating_1")
        builder.button(text="⭐️⭐️", callback_data="rating_2")
        builder.button(text="⭐️⭐️⭐️", callback_data="rating_3")
        builder.button(text="⭐️⭐️⭐️⭐️", callback_data="rating_4")
        builder.button(text="⭐️⭐️⭐️⭐️⭐️", callback_data="rating_5")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def skip_and_cancel() -> InlineKeyboardMarkup:
        """Пропустить и отменить"""
        builder = InlineKeyboardBuilder()
        builder.button(text="⏭ Пропустить", callback_data="skip")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def file_actions() -> InlineKeyboardMarkup:
        """Действия с файлами"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Завершить загрузку", callback_data="files_done")
        builder.button(text="❌ Отменить", callback_data="cancel")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def file_list_with_actions(files: List[dict], context: str = "initial") -> InlineKeyboardMarkup:
        """Список файлов с кнопками для просмотра"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для каждого файла
        for idx, file_info in enumerate(files):
            file_icon = "📷" if file_info.get('is_photo') else "📎"
            file_name = file_info['file_name']
            # Обрезаем длинные имена
            if len(file_name) > 25:
                file_name = file_name[:22] + "..."
            
            builder.button(
                text=f"{file_icon} {file_name}",
                callback_data=f"view_file_{context}:{idx}"
            )
        
        # Кнопка добавления файлов
        builder.button(text="➕ Добавить еще файлы", callback_data=f"add_more_files_{context}")
        builder.button(text="✅ Завершить", callback_data="files_done")
        builder.button(text="❌ Отменить", callback_data="cancel")
        
        builder.adjust(1)  # По одной кнопке в ряд
        return builder.as_markup()
    
    @staticmethod
    def file_list_view_only(files: List[dict], context: str = "initial") -> InlineKeyboardMarkup:
        """Список файлов только для просмотра (без дополнительных кнопок)"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для каждого файла
        for idx, file_info in enumerate(files):
            file_icon = "📷" if file_info.get('is_photo') else "📎"
            file_name = file_info['file_name']
            # Обрезаем длинные имена
            if len(file_name) > 25:
                file_name = file_name[:22] + "..."
            
            builder.button(
                text=f"{file_icon} {file_name}",
                callback_data=f"view_file_{context}:{idx}"
            )
        
        builder.adjust(1)  # По одной кнопке в ряд
        return builder.as_markup()
    
    @staticmethod
    def chat_task_complete(task_id: int) -> InlineKeyboardMarkup:
        """Кнопка "Выполнить" для задач в чате"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ ВЫПОЛНИТЬ", callback_data=f"chat_task_complete_{task_id}")
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def pagination(page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
        """
        Оптимизированная пагинация
        """
        builder = InlineKeyboardBuilder()

        # Добавляем кнопки "Назад" и "Вперед" только при необходимости
        if page > 1:
            builder.button(text="◀️ Назад", callback_data=f"{prefix}_page_{page-1}")

        builder.button(text=f"📄 {page}/{total_pages}", callback_data="page_info")

        if page < total_pages:
            builder.button(text="Вперед ▶️", callback_data=f"{prefix}_page_{page+1}")

        # Добавляем кнопку "Закрыть"
        builder.button(text="❌ Закрыть", callback_data="cancel")
        builder.adjust(3, 1)  # Устанавливаем количество кнопок в строке

        return builder.as_markup()

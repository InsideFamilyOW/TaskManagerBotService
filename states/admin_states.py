"""FSM состояния для администратора"""
from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния для работы администратора"""
    
    # Управление пользователями
    waiting_user_action = State()  # Выбор действия с пользователем
    waiting_telegram_id = State()  # Ввод Telegram ID
    waiting_user_role = State()  # Выбор роли пользователя
    waiting_user_direction = State()  # Выбор направления для исполнителя
    waiting_user_name = State()  # Изменение имени пользователя
    
    # Удаление пользователя
    waiting_user_delete_confirm = State()  # Подтверждение удаления
    
    # Редактирование пользователя
    waiting_edit_user_id = State()  # Выбор пользователя для редактирования
    waiting_edit_field = State()  # Выбор поля для редактирования
    waiting_edit_value = State()  # Ввод нового значения
    
    # Статистика
    waiting_statistics_period = State()  # Выбор периода статистики
    waiting_statistics_user = State()  # Выбор пользователя для статистики
    
    # Настройки канала логов
    waiting_channel_id = State()  # Ввод ID канала
    waiting_channel_delete_confirm = State()  # Подтверждение удаления канала
    
    # Распределение исполнителей
    waiting_buyer_selection = State()  # Выбор баера для назначения
    waiting_executor_selection = State()  # Выбор исполнителя для назначения
    waiting_assignment_confirm = State()  # Подтверждение назначения


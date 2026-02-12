"""FSM состояния для администратора"""
from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния для работы администратора"""
    
    waiting_user_action = State()
    waiting_telegram_id = State()
    waiting_user_role = State()
    waiting_user_direction = State()
    waiting_user_name = State()
    
    waiting_user_delete_confirm = State()
    
    waiting_edit_user_id = State()
    waiting_edit_field = State()
    waiting_edit_value = State()
    
    waiting_statistics_period = State()
    waiting_statistics_user = State()
    
    waiting_channel_id = State()
    waiting_channel_delete_confirm = State()
    
    waiting_buyer_selection = State()
    waiting_executor_selection = State()
    waiting_assignment_confirm = State()
    
    waiting_chat_selection = State()
    waiting_chat_message = State()
    waiting_chat_task_executor = State()
    waiting_chat_task_selection = State()
    waiting_chat_title = State()

    waiting_chat_access_buyer = State()
    waiting_chat_access_chat = State()
    
    waiting_channel_selection = State()
    waiting_channel_message = State()

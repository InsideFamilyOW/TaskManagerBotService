"""FSM состояния для байера"""
from aiogram.fsm.state import State, StatesGroup


class BuyerStates(StatesGroup):
    """Состояния для работы байера"""
    
    waiting_direction = State()
    waiting_executor = State()
    waiting_task_title = State()
    waiting_task_description = State()
    waiting_task_priority = State()
    waiting_task_deadline = State()
    waiting_task_files = State()
    waiting_task_confirmation = State()
    
    waiting_edit_task_id = State()
    waiting_edit_field = State()
    waiting_edit_value = State()
    
    waiting_review_decision = State()
    waiting_review_comment = State()
    waiting_task_rating = State()
    
    waiting_correction_description = State()
    
    waiting_message_to_executor = State()
    waiting_message_file = State()
    
    waiting_file_to_task = State()
    
    waiting_task_filter = State()
    waiting_task_view = State()

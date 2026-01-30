"""FSM состояния для исполнителя"""
from aiogram.fsm.state import State, StatesGroup


class ExecutorStates(StatesGroup):
    """Состояния для работы исполнителя"""
    
    waiting_task_action = State()
    waiting_take_confirm = State()
    waiting_reject_reason = State()
    waiting_reject_custom = State()
    
    waiting_completion_comment = State()
    waiting_completion_files = State()
    waiting_completion_confirm = State()
    
    waiting_message_to_buyer = State()
    waiting_clarification = State()
    waiting_message_file = State()
    waiting_file_to_task = State()
    
    waiting_correction_complete = State()
    waiting_correction_files = State()
    
    waiting_my_tasks_filter = State()
    waiting_task_detail = State()

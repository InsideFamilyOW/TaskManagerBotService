"""FSM состояния для исполнителя"""
from aiogram.fsm.state import State, StatesGroup


class ExecutorStates(StatesGroup):
    """Состояния для работы исполнителя"""
    
    # Управление задачами
    waiting_task_action = State()  # Выбор действия с задачей
    waiting_take_confirm = State()  # Подтверждение взятия в работу
    waiting_reject_reason = State()  # Выбор причины отказа
    waiting_reject_custom = State()  # Ввод своей причины отказа
    
    # Выполнение задачи
    waiting_completion_comment = State()  # Комментарий к выполнению
    waiting_completion_files = State()  # Файлы результата
    waiting_completion_confirm = State()  # Подтверждение отправки
    
    # Коммуникация
    waiting_message_to_buyer = State()  # Сообщение байеру
    waiting_clarification = State()  # Запрос уточнения
    waiting_message_file = State()  # Файл к сообщению
    waiting_file_to_task = State()  # Добавление файла к задаче
    
    # Управление правками
    waiting_correction_complete = State()  # Завершение правок
    waiting_correction_files = State()  # Файлы после правок
    
    # Просмотр задач
    waiting_my_tasks_filter = State()  # Фильтр своих задач
    waiting_task_detail = State()  # Детали задачи


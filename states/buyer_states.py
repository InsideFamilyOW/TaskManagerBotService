"""FSM состояния для байера"""
from aiogram.fsm.state import State, StatesGroup


class BuyerStates(StatesGroup):
    """Состояния для работы байера"""
    
    # Создание задачи
    waiting_direction = State()  # Выбор направления
    waiting_executor = State()  # Выбор исполнителя
    waiting_task_title = State()  # Ввод названия задачи
    waiting_task_description = State()  # Ввод описания задачи
    waiting_task_priority = State()  # Выбор приоритета
    waiting_task_deadline = State()  # Ввод дедлайна
    waiting_task_files = State()  # Загрузка файлов
    waiting_task_confirmation = State()  # Подтверждение создания
    
    # Редактирование задачи
    waiting_edit_task_id = State()  # Выбор задачи для редактирования
    waiting_edit_field = State()  # Выбор поля для редактирования
    waiting_edit_value = State()  # Ввод нового значения
    
    # Проверка результата
    waiting_review_decision = State()  # Принять/Отклонить/Обсудить
    waiting_review_comment = State()  # Комментарий к решению
    waiting_task_rating = State()  # Оценка работы (1-5)
    
    # Запрос правок
    waiting_correction_description = State()  # Описание правок
    
    # Коммуникация
    waiting_message_to_executor = State()  # Сообщение исполнителю
    waiting_message_file = State()  # Файл к сообщению
    
    # Загрузка файлов к задаче
    waiting_file_to_task = State()  # Загрузка файлов к существующей задаче
    
    # Просмотр задач
    waiting_task_filter = State()  # Фильтр для просмотра задач
    waiting_task_view = State()  # Просмотр конкретной задачи


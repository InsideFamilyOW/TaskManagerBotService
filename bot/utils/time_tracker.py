"""Утилиты для отслеживания времени выполнения задач"""
from datetime import datetime, timezone
from typing import Tuple


def format_timedelta(seconds: int) -> str:
    """Форматировать временной интервал в читаемый вид (ЧЧ:ММ:СС)"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def calculate_task_execution_time(task) -> Tuple[int, str]:
    """
    Вычислить время выполнения задачи
    
    Args:
        task: Объект задачи с полями created_at, started_at, completed_at, status
        
    Returns:
        Tuple[int, str]: (секунды, форматированная строка)
    """
    from db.models import TaskStatus
    
    current_time = datetime.now(timezone.utc)
    
    # Если задача еще не начата (PENDING) - считаем с момента создания
    if task.status == TaskStatus.PENDING:
        elapsed_seconds = int((current_time - task.created_at).total_seconds())
        return elapsed_seconds, format_timedelta(elapsed_seconds)
    
    # Если задача в работе (IN_PROGRESS) - считаем с момента начала
    elif task.status == TaskStatus.IN_PROGRESS:
        start_time = task.started_at if task.started_at else task.created_at
        elapsed_seconds = int((current_time - start_time).total_seconds())
        return elapsed_seconds, format_timedelta(elapsed_seconds)
    
    # Если задача завершена (COMPLETED, APPROVED, REJECTED, CANCELLED)
    else:
        # Используем completed_at если есть, иначе текущее время
        end_time = task.completed_at if task.completed_at else current_time
        start_time = task.started_at if task.started_at else task.created_at
        elapsed_seconds = int((end_time - start_time).total_seconds())
        return elapsed_seconds, format_timedelta(elapsed_seconds)


def get_execution_time_display(task) -> str:
    """
    Получить отформатированное отображение времени выполнения для задачи
    
    Args:
        task: Объект задачи
        
    Returns:
        str: Строка вида "⏱ Время выполнения: 00:12:34"
    """
    _, formatted_time = calculate_task_execution_time(task)
    return f"⏱ Время выполнения: {formatted_time}"


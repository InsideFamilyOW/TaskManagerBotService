"""
Запросы к базе данных

DEPRECATED: Этот файл сохранен для обратной совместимости.
Используйте импорты из db.queries вместо этого файла.

Новая структура:
    from db.queries import UserQueries, TaskQueries, MessageQueries, FileQueries, LogQueries

Подробная документация: db/queries/README.md
"""

# Импорты для обратной совместимости
from db.queries.user_queries import UserQueries
from db.queries.task_queries import TaskQueries
from db.queries.message_queries import MessageQueries
from db.queries.file_queries import FileQueries
from db.queries.log_queries import LogQueries

__all__ = [
    "UserQueries",
    "TaskQueries", 
    "MessageQueries",
    "FileQueries",
    "LogQueries"
]

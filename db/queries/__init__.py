"""Модуль запросов к базе данных"""

from .user_queries import UserQueries
from .task_queries import TaskQueries
from .message_queries import MessageQueries
from .file_queries import FileQueries
from .log_queries import LogQueries
from .channel_queries import ChannelQueries
from .chat_queries import ChatQueries
from .chat_access_queries import ChatAccessQueries
from .chat_request_queries import ChatRequestQueries

__all__ = [
    "UserQueries",
    "TaskQueries",
    "MessageQueries",
    "FileQueries",
    "LogQueries",
    "ChannelQueries",
    "ChatQueries",
    "ChatAccessQueries",
    "ChatRequestQueries",
]


# database/models_optimized.py
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, ForeignKey,
    Enum, DECIMAL, Index, UniqueConstraint, CheckConstraint, SmallInteger,
    Table, JSON, Computed, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()


# === ОПТИМИЗИРОВАННЫЕ ENUMS ===
class UserRole(enum.Enum):
    ADMIN = "admin"
    BUYER = "buyer"
    EXECUTOR = "executor"


class TaskStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class TaskPriority(enum.IntEnum):  # Изменено на IntEnum для производительности
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class DirectionType(enum.Enum):
    DESIGN = "design"
    AGENCY = "agency"
    COPYWRITING = "copywriting"
    MARKETING = "marketing"


class RejectionReason(enum.Enum):
    LACK_INFO = "lack_info"
    OUT_OF_SCOPE = "out_of_scope"
    TECH_LIMITATIONS = "tech_limitations"
    OVERLOAD = "overload"
    OTHER = "other"


class FileType(enum.Enum):
    INITIAL = "initial"
    RESULT = "result"
    MESSAGE = "message"
    CORRECTION = "correction"


class MessageType(enum.Enum):
    TEXT = "text"
    SYSTEM = "system"
    FILE = "file"


# === ДОПОЛНИТЕЛЬНЫЕ ENUMS ===
class NotificationChannel(enum.Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"


class ExecutorLoad(enum.IntEnum):
    FREE = 0  # 0 задач
    LIGHT = 1  # 1-2 задачи
    MEDIUM = 2  # 3-4 задачи
    HEAVY = 3  # 5+ задач


# === МНОГИЕ-КО-МНОГИМ ТАБЛИЦА (добавлена) ===
executor_skills = Table(
    'executor_skills',
    Base.metadata,
    Column('executor_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('skill_id', Integer, ForeignKey('skills.id'), primary_key=True),
    Column('level', SmallInteger, default=1),  # 1-10 уровень навыка
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

# Таблица связи исполнителей и баеров
executor_buyer_assignments = Table(
    'executor_buyer_assignments',
    Base.metadata,
    Column('executor_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('buyer_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now()),
    Column('created_by_id', Integer, ForeignKey('users.id'), nullable=True),  # Кто создал назначение (админ)
    UniqueConstraint('executor_id', 'buyer_id', name='uq_executor_buyer')
)


# === ОПТИМИЗИРОВАННЫЕ МОДЕЛИ ===
class User(Base):
    __tablename__ = "users"

    # Основные поля оптимизированы
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)  # BigInteger вместо String
    username = Column(String(32), nullable=True)  # Ограничение по длине
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    role = Column(Enum(UserRole, name='user_role'), nullable=True, index=True)  # Nullable для незарегистрированных

    # Для исполнителей (оптимизировано)
    direction = Column(Enum(DirectionType, name='direction_type'), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    current_load = Column(SmallInteger, default=0)  # Текущая загрузка
    load_level = Column(Enum(ExecutorLoad, name='executor_load'),
                        default=ExecutorLoad.FREE, index=True)

    # Статистика (добавлено)
    completed_tasks = Column(Integer, default=0)
    avg_rating = Column(DECIMAL(3, 2), default=0.00)  # Средняя оценка
    response_time = Column(Integer, default=0)  # Среднее время отклика в минутах

    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_activity = Column(DateTime(timezone=True), default=func.now(), index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete

    # Отношения
    created_tasks = relationship("Task", foreign_keys="Task.created_by_id",
                                 back_populates="creator", lazy="dynamic")
    assigned_tasks = relationship("Task", foreign_keys="Task.executor_id",
                                  back_populates="executor", lazy="dynamic")
    action_logs = relationship("ActionLog", back_populates="user", lazy="dynamic")
    messages = relationship("Message", back_populates="sender", lazy="dynamic")
    skills = relationship("Skill", secondary=executor_skills, back_populates="executors")
    notifications = relationship("NotificationQueue", back_populates="user", lazy="dynamic")
    
    # Связи исполнителей и баеров
    assigned_buyers = relationship(
        "User",
        secondary=executor_buyer_assignments,
        primaryjoin="User.id == executor_buyer_assignments.c.executor_id",
        secondaryjoin="User.id == executor_buyer_assignments.c.buyer_id",
        lazy="dynamic",
        backref="assigned_executors"
    )

    __table_args__ = (
        Index("idx_users_telegram_active", "telegram_id", "is_active"),
        Index("idx_users_direction_load", "direction", "load_level"),
        CheckConstraint("current_load >= 0", name="check_load_min"),
    )


class Skill(Base):
    """Новая таблица для навыков исполнителей"""
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    direction = Column(Enum(DirectionType), nullable=False, index=True)
    is_active = Column(Boolean, default=True)

    executors = relationship("User", secondary=executor_skills, back_populates="skills")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_number = Column(String(20), unique=True, index=True, nullable=False)  # Сократил длину

    # Основные поля оптимизированы
    title = Column(String(200), nullable=False)  # Сократил длину
    description = Column(Text, nullable=True)
    direction = Column(Enum(DirectionType), nullable=False, index=True)
    priority = Column(SmallInteger, default=2, index=True)  # Используем IntEnum
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)

    # Связи
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Сроки и время (оптимизировано)
    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Время выполнения (добавлено)
    estimated_hours = Column(DECIMAL(4, 1), nullable=True)  # Оценка времени
    actual_hours = Column(DECIMAL(4, 1), nullable=True)  # Фактическое время

    # Исполнение
    completion_comment = Column(Text, nullable=True)
    rating = Column(SmallInteger, nullable=True)  # 1-5

    # Метаданные (добавлено)
    tags = Column(JSON, nullable=True)  # Теги для поиска
    requirements = Column(JSON, nullable=True)  # JSON с требованиями

    # Отношения
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_tasks")
    executor = relationship("User", foreign_keys=[executor_id], back_populates="assigned_tasks")
    files = relationship("TaskFile", back_populates="task", lazy="dynamic")
    messages = relationship("Message", back_populates="task", lazy="dynamic", order_by="Message.created_at")
    logs = relationship("TaskLog", back_populates="task", lazy="dynamic", order_by="TaskLog.created_at.desc()")
    corrections = relationship("TaskCorrection", back_populates="task", lazy="dynamic")

    __table_args__ = (
        # Оптимизированные составные индексы для частых запросов
        Index("idx_tasks_active", "status", "priority", "deadline"),
        Index("idx_tasks_executor_active", "executor_id", "status"),
        Index("idx_tasks_creator_date", "created_by_id", "created_at"),
        # Новые индексы для оптимизации пагинации
        Index("idx_tasks_creator_status_date", "created_by_id", "status", "created_at"),  # Для фильтрации + сортировки
        Index("idx_tasks_executor_status_date", "executor_id", "status", "created_at"),  # Для фильтрации + сортировки
        Index("idx_tasks_status_creator_date", "status", "created_by_id", "created_at"),  # Для PENDING задач от баеров
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
        CheckConstraint("priority >= 1 AND priority <= 4", name="check_priority_range"),
    )


class TaskFile(Base):
    __tablename__ = "task_files"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    file_type = Column(Enum(FileType), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)  # Устаревшее поле, оставлено для совместимости
    file_size = Column(Integer, nullable=False, default=0)
    mime_type = Column(String(100), nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete
    
    # Поля для хранения файлов в БД (base64 формат)
    photo_base64 = Column(Text, nullable=True)  # Устаревшее, заменено на file_data
    file_data = Column(Text, nullable=True)  # Все файлы хранятся здесь в base64 формате

    # Отношения
    task = relationship("Task", back_populates="files")
    uploader = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Для файлов в сообщениях
    file_id = Column(Integer, ForeignKey("task_files.id"), nullable=True)

    # Отношения
    task = relationship("Task", back_populates="messages")
    sender = relationship("User", back_populates="messages")
    file = relationship("TaskFile")


class TaskCorrection(Base):
    """Новая таблица для правок по задаче"""
    __tablename__ = "task_corrections"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    description = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="corrections")


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)  # Сократил длину
    old_status = Column(Enum(TaskStatus), nullable=True)
    new_status = Column(Enum(TaskStatus), nullable=True)
    details = Column(JSON, nullable=True)  # Изменил на JSON для гибкости
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    task = relationship("Task", back_populates="logs")
    user = relationship("User")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False)  # Сократил длину
    entity_id = Column(Integer, nullable=True, index=True)
    details = Column(JSON, nullable=True)  # JSON вместо Text
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Индекс для быстрого поиска по времени
    __table_args__ = (
        Index('idx_action_logs_time', 'created_at'),
    )

    user = relationship("User", back_populates="action_logs")


class TaskRejection(Base):
    __tablename__ = "task_rejections"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(Enum(RejectionReason), nullable=False)
    custom_reason = Column(String(500), nullable=True)  # Ограничил длину
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task")
    executor = relationship("User")


class NotificationQueue(Base):
    """Новая таблица для очереди уведомлений"""
    __tablename__ = "notification_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(String(50), nullable=False, index=True)
    channel = Column(Enum(NotificationChannel), default=NotificationChannel.TELEGRAM)
    content = Column(JSON, nullable=False)  # JSON с данными уведомления
    priority = Column(SmallInteger, default=1, index=True)
    attempts = Column(SmallInteger, default=0)
    max_attempts = Column(SmallInteger, default=3)
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")


class UserSettings(Base):
    """Новая таблица для настроек пользователей"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # Настройки уведомлений
    notify_new_task = Column(Boolean, default=True)
    notify_status_change = Column(Boolean, default=True)
    notify_messages = Column(Boolean, default=True)
    notify_deadline = Column(Boolean, default=True)

    # Рабочие часы
    work_start_time = Column(String(5), default="09:00")  # HH:MM
    work_end_time = Column(String(5), default="18:00")
    timezone = Column(String(50), default="UTC")

    # Язык и интерфейс
    language = Column(String(10), default="ru")
    theme = Column(String(20), default="light")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="settings")


class TaskStatistics(Base):
    """Новая таблица для кэширования статистики"""
    __tablename__ = "task_statistics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # Статистика за всё время
    total_created = Column(Integer, default=0)
    total_completed = Column(Integer, default=0)
    total_in_time = Column(Integer, default=0)
    avg_completion_time = Column(Integer, default=0)  # в минутах
    avg_rating = Column(DECIMAL(3, 2), default=0.00)

    # Статистика за месяц
    monthly_created = Column(Integer, default=0)
    monthly_completed = Column(Integer, default=0)
    monthly_avg_time = Column(Integer, default=0)

    # Последнее обновление
    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="statistics")


class Channel(Base):
    """Таблица для хранения каналов, куда бот отправляет уведомления о задачах"""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)  # Telegram ID канала
    channel_name = Column(String(255), nullable=True)  # Название канала (опционально)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Отношения
    creator = relationship("User")
    
    __table_args__ = (
        Index("idx_channels_active", "is_active", "channel_id"),
    )
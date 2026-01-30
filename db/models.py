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


class TaskPriority(enum.IntEnum):
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


class NotificationChannel(enum.Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"


class ExecutorLoad(enum.IntEnum):
    FREE = 0
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3


executor_skills = Table(
    'executor_skills',
    Base.metadata,
    Column('executor_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('skill_id', Integer, ForeignKey('skills.id'), primary_key=True),
    Column('level', SmallInteger, default=1),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

executor_buyer_assignments = Table(
    'executor_buyer_assignments',
    Base.metadata,
    Column('executor_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('buyer_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now()),
    Column('created_by_id', Integer, ForeignKey('users.id'), nullable=True),
    UniqueConstraint('executor_id', 'buyer_id', name='uq_executor_buyer')
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(32), nullable=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    role = Column(Enum(UserRole, name='user_role'), nullable=True, index=True)

    direction = Column(Enum(DirectionType, name='direction_type'), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_available = Column(Boolean, default=True, nullable=False, index=True)
    current_load = Column(SmallInteger, default=0)
    load_level = Column(Enum(ExecutorLoad, name='executor_load'),
                        default=ExecutorLoad.FREE, index=True)

    completed_tasks = Column(Integer, default=0)
    avg_rating = Column(DECIMAL(3, 2), default=0.00)
    response_time = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_activity = Column(DateTime(timezone=True), default=func.now(), index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_tasks = relationship("Task", foreign_keys="Task.created_by_id",
                                 back_populates="creator", lazy="dynamic")
    assigned_tasks = relationship("Task", foreign_keys="Task.executor_id",
                                  back_populates="executor", lazy="dynamic")
    action_logs = relationship("ActionLog", back_populates="user", lazy="dynamic")
    messages = relationship("Message", back_populates="sender", lazy="dynamic")
    skills = relationship("Skill", secondary=executor_skills, back_populates="executors")
    notifications = relationship("NotificationQueue", back_populates="user", lazy="dynamic")
    
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
        Index("idx_users_role_available", "role", "is_available"),
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
    task_number = Column(String(20), unique=True, index=True, nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    direction = Column(Enum(DirectionType), nullable=False, index=True)
    priority = Column(SmallInteger, default=2, index=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    executor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    estimated_hours = Column(DECIMAL(4, 1), nullable=True)
    actual_hours = Column(DECIMAL(4, 1), nullable=True)

    completion_comment = Column(Text, nullable=True)
    rating = Column(SmallInteger, nullable=True)

    tags = Column(JSON, nullable=True)
    requirements = Column(JSON, nullable=True)

    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_tasks")
    executor = relationship("User", foreign_keys=[executor_id], back_populates="assigned_tasks")
    files = relationship("TaskFile", back_populates="task", lazy="dynamic")
    messages = relationship("Message", back_populates="task", lazy="dynamic", order_by="Message.created_at")
    logs = relationship("TaskLog", back_populates="task", lazy="dynamic", order_by="TaskLog.created_at.desc()")
    corrections = relationship("TaskCorrection", back_populates="task", lazy="dynamic")

    __table_args__ = (
        Index("idx_tasks_active", "status", "priority", "deadline"),
        Index("idx_tasks_executor_active", "executor_id", "status"),
        Index("idx_tasks_creator_date", "created_by_id", "created_at"),
        Index("idx_tasks_creator_status_date", "created_by_id", "status", "created_at"),
        Index("idx_tasks_executor_status_date", "executor_id", "status", "created_at"),
        Index("idx_tasks_status_creator_date", "status", "created_by_id", "created_at"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
        CheckConstraint("priority >= 1 AND priority <= 4", name="check_priority_range"),
    )


class TaskFile(Base):
    __tablename__ = "task_files"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    file_type = Column(Enum(FileType), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=False, default=0)
    mime_type = Column(String(100), nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, default=False, index=True)
    
    photo_base64 = Column(Text, nullable=True)
    file_data = Column(Text, nullable=True)

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

    file_id = Column(Integer, ForeignKey("task_files.id"), nullable=True)

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
    action = Column(String(50), nullable=False, index=True)
    old_status = Column(Enum(TaskStatus), nullable=True)
    new_status = Column(Enum(TaskStatus), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    task = relationship("Task", back_populates="logs")
    user = relationship("User")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='SET NULL'), nullable=True, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=True, index=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

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
    custom_reason = Column(String(500), nullable=True)
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
    content = Column(JSON, nullable=False)
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

    notify_new_task = Column(Boolean, default=True)
    notify_status_change = Column(Boolean, default=True)
    notify_messages = Column(Boolean, default=True)
    notify_deadline = Column(Boolean, default=True)

    work_start_time = Column(String(5), default="09:00")
    work_end_time = Column(String(5), default="18:00")
    timezone = Column(String(50), default="UTC")

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

    total_created = Column(Integer, default=0)
    total_completed = Column(Integer, default=0)
    total_in_time = Column(Integer, default=0)
    avg_completion_time = Column(Integer, default=0)
    avg_rating = Column(DECIMAL(3, 2), default=0.00)

    monthly_created = Column(Integer, default=0)
    monthly_completed = Column(Integer, default=0)
    monthly_avg_time = Column(Integer, default=0)

    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="statistics")


class Channel(Base):
    """Таблица для хранения каналов, куда бот отправляет уведомления о задачах"""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)
    channel_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Статус бота в канале (для автоматического отслеживания)
    bot_status = Column(String(20), nullable=True, index=True)  # member, administrator, left, kicked
    
    # Права бота (если статус administrator)
    can_post_messages = Column(Boolean, default=False, nullable=True)
    can_edit_messages = Column(Boolean, default=False, nullable=True)
    can_delete_messages = Column(Boolean, default=False, nullable=True)
    can_restrict_members = Column(Boolean, default=False, nullable=True)
    can_promote_members = Column(Boolean, default=False, nullable=True)
    can_change_info = Column(Boolean, default=False, nullable=True)
    can_invite_users = Column(Boolean, default=False, nullable=True)
    can_pin_messages = Column(Boolean, default=False, nullable=True)
    can_manage_chat = Column(Boolean, default=False, nullable=True)
    can_manage_video_chats = Column(Boolean, default=False, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Может быть NULL для автоматически добавленных
    
    creator = relationship("User")
    
    __table_args__ = (
        Index("idx_channels_active", "is_active", "channel_id"),
        Index("idx_channels_status", "bot_status", "channel_id"),
    )


class Chat(Base):
    """Таблица для хранения чатов, в которые добавлен бот"""
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    chat_type = Column(String(20), nullable=False)
    chat_title = Column(String(255), nullable=True)
    bot_status = Column(String(20), nullable=False, index=True)
    
    can_post_messages = Column(Boolean, default=False)
    can_edit_messages = Column(Boolean, default=False)
    can_delete_messages = Column(Boolean, default=False)
    can_restrict_members = Column(Boolean, default=False)
    can_promote_members = Column(Boolean, default=False)
    can_change_info = Column(Boolean, default=False)
    can_invite_users = Column(Boolean, default=False)
    can_pin_messages = Column(Boolean, default=False)
    can_manage_chat = Column(Boolean, default=False)
    can_manage_video_chats = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_chats_status", "bot_status", "chat_id"),
        Index("idx_chats_type", "chat_type", "bot_status"),
    )

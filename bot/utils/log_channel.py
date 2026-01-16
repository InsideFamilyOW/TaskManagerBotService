"""Система логирования действий в каналы"""
from aiogram import Bot
from typing import Optional, List
from datetime import datetime
from db.models import User, Task, DirectionType, TaskStatus
from log import logger


class LogChannel:
    """Управление логами в каналах"""
    
    # Список ID каналов
    CHANNELS: List[int] = []
    
    @classmethod
    def set_channels(cls, channel_ids: List[int]):
        """Установить список каналов"""
        cls.CHANNELS = channel_ids
        logger.info(f"Установлены каналы логов: {channel_ids}")
    
    @classmethod
    def add_channel(cls, channel_id: int):
        """Добавить канал в список"""
        if channel_id not in cls.CHANNELS:
            cls.CHANNELS.append(channel_id)
            logger.info(f"Добавлен канал логов: {channel_id}")
    
    @classmethod
    def remove_channel(cls, channel_id: int):
        """Удалить канал из списка"""
        if channel_id in cls.CHANNELS:
            cls.CHANNELS.remove(channel_id)
            logger.info(f"Удален канал логов: {channel_id}")
    
    @classmethod
    def get_all_channels(cls) -> List[int]:
        """Получить все каналы"""
        return cls.CHANNELS
    
    @classmethod
    async def log_task_created(cls, bot: Bot, task: Task, creator: User, executor: User):
        """Лог создания задачи"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        priority_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
        priority = priority_emoji.get(task.priority, "")
        
        direction_emoji = {
            DirectionType.DESIGN: "🎨",
            DirectionType.AGENCY: "🏢",
            DirectionType.COPYWRITING: "✍️",
            DirectionType.MARKETING: "📱"
        }
        dir_emoji = direction_emoji.get(task.direction, "📁")
        
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        message = f"""
🆕 <b>НОВАЯ ЗАДАЧА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}
{dir_emoji} <b>Направление:</b> {task.direction.value.upper()}
{priority} <b>Приоритет:</b> {['Низкий', 'Средний', 'Высокий', 'Срочный'][task.priority-1]}

👤 <b>От:</b> {creator.first_name} {creator.last_name or ''}
🛠️ <b>Исполнитель:</b> {executor.first_name} {executor.last_name or ''}

⏱️ <b>Срок:</b> {deadline_str}
📅 <b>Создана:</b> {datetime.now().strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем во все каналы
        for channel_id in channels:
            try:
                await bot.send_message(channel_id, message, parse_mode="HTML")
                logger.info(f"Отправлен лог создания задачи {task.task_number} в канал {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки лога в канал {channel_id}: {e}")
    
    @classmethod
    async def log_task_status_change(cls, bot: Bot, task: Task, old_status: TaskStatus, new_status: TaskStatus, user: User):
        """Лог изменения статуса задачи"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.IN_PROGRESS: "🟡",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.APPROVED: "🎉",
            TaskStatus.REJECTED: "❌",
            TaskStatus.CANCELLED: "🚫"
        }
        
        status_names = {
            TaskStatus.PENDING: "Ожидает",
            TaskStatus.IN_PROGRESS: "В работе",
            TaskStatus.COMPLETED: "Завершена",
            TaskStatus.APPROVED: "Одобрена",
            TaskStatus.REJECTED: "Отклонена",
            TaskStatus.CANCELLED: "Отменена"
        }
        
        old_emoji = status_emoji.get(old_status, "")
        new_emoji = status_emoji.get(new_status, "")
        old_name = status_names.get(old_status, old_status.value)
        new_name = status_names.get(new_status, new_status.value)
        
        message = f"""
🔄 <b>ИЗМЕНЕНИЕ СТАТУСА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}

{old_emoji} <b>Было:</b> {old_name}
{new_emoji} <b>Стало:</b> {new_name}

👤 <b>Изменил:</b> {user.first_name} {user.last_name or ''}
📅 <b>Время:</b> {datetime.now().strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем во все каналы
        for channel_id in channels:
            try:
                await bot.send_message(channel_id, message, parse_mode="HTML")
                logger.info(f"Отправлен лог изменения статуса задачи {task.task_number} в канал {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки лога в канал {channel_id}: {e}")
    
    @classmethod
    async def log_task_completed(cls, bot: Bot, task: Task, executor: User, completion_time: str):
        """Лог завершения задачи"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        # Форматируем даты
        created_date = task.created_at.strftime("%d.%m.%Y %H:%M") if task.created_at else "Не указана"
        completed_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        message = f"""
✅ <b>ЗАДАЧА УСПЕШНО ВЫПОЛНЕНА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача №{task.task_number}</b>

📅 <b>Дата создания задачи:</b> {created_date}
📅 <b>Дата выполнения задачи:</b> {completed_date}

🛠️ <b>Исполнитель:</b> {executor.first_name} {executor.last_name or ''}
⏱️ <b>Время выполнения:</b> {completion_time}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем во все каналы
        for channel_id in channels:
            try:
                await bot.send_message(channel_id, message, parse_mode="HTML")
                logger.info(f"Отправлен лог завершения задачи {task.task_number} в канал {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки лога в канал {channel_id}: {e}")
    
    @classmethod
    async def log_task_approved(cls, bot: Bot, task: Task, buyer: User, rating: int = None):
        """Лог одобрения задачи"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        rating_str = f"{'⭐️' * rating}" if rating else "Без оценки"
        
        message = f"""
🎉 <b>ЗАДАЧА ОДОБРЕНА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}

👤 <b>Одобрил:</b> {buyer.first_name} {buyer.last_name or ''}
⭐️ <b>Оценка:</b> {rating_str}

📅 <b>Одобрена:</b> {datetime.now().strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем во все каналы
        for channel_id in channels:
            try:
                await bot.send_message(channel_id, message, parse_mode="HTML")
                logger.info(f"Отправлен лог одобрения задачи {task.task_number} в канал {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки лога в канал {channel_id}: {e}")
    
    @classmethod
    async def log_task_rejected(cls, bot: Bot, task: Task, executor_or_buyer: User, reason: str):
        """Лог отклонения задачи"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        # Форматируем даты
        created_date = task.created_at.strftime("%d.%m.%Y %H:%M") if task.created_at else "Не указана"
        rejected_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        message = f"""
❌ <b>ЗАДАЧА ОТКЛОНЕНА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача №{task.task_number}</b>

📅 <b>Дата создания задачи:</b> {created_date}
📅 <b>Дата отклонения задачи:</b> {rejected_date}

👤 <b>Отклонил:</b> {executor_or_buyer.first_name} {executor_or_buyer.last_name or ''}
💬 <b>Причина:</b> {reason}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем во все каналы
        for channel_id in channels:
            try:
                await bot.send_message(channel_id, message, parse_mode="HTML")
                logger.info(f"Отправлен лог отклонения задачи {task.task_number} в канал {channel_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки лога в канал {channel_id}: {e}")
    
    @classmethod
    async def log_file_uploaded(cls, bot: Bot, task: Task, file_id: str, file_name: str, file_type: str, uploaded_by: User, mime_type: str = None):
        """Отправка файла в каналы"""
        channels = cls.get_all_channels()
        if not channels:
            return
        
        # Определяем тип файла для заголовка
        file_type_emoji = {
            "INITIAL": "📤",
            "RESULT": "📥",
            "MESSAGE": "💬"
        }
        type_emoji = file_type_emoji.get(file_type, "📎")
        
        file_type_names = {
            "INITIAL": "Исходный файл",
            "RESULT": "Файл результата",
            "MESSAGE": "Файл из сообщения"
        }
        type_name = file_type_names.get(file_type, "Файл")
        
        caption = f"""
{type_emoji} <b>{type_name.upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}
👤 <b>Загрузил:</b> {uploaded_by.first_name} {uploaded_by.last_name or ''}
📅 <b>Время:</b> {datetime.now().strftime("%d.%m.%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Отправляем файл во все каналы
        for channel_id in channels:
            try:
                # Определяем тип файла
                is_photo = mime_type and mime_type.startswith('image/')
                is_video = mime_type and mime_type.startswith('video/')
                
                if is_photo:
                    await bot.send_photo(
                        channel_id,
                        photo=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                elif is_video:
                    await bot.send_video(
                        channel_id,
                        video=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_document(
                        channel_id,
                        document=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                
                logger.info(f"Отправлен файл {file_name} в канал {channel_id} для задачи {task.task_number}")
            except Exception as e:
                logger.error(f"Ошибка отправки файла в канал {channel_id}: {e}")


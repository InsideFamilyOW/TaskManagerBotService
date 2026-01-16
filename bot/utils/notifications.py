"""Система уведомлений"""
from aiogram import Bot
from typing import List, Optional
from Data.config import ADMIN_TG_ID
from log import logger


class NotificationService:
    """Сервис уведомлений"""
    
    @staticmethod
    async def notify_admins_on_start(bot: Bot):
        """Уведомление админов о запуске бота"""
        message = """
🚀 <b>Task Manager Bot запущен!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Бот успешно инициализирован
✅ База данных подключена
✅ Все системы работают

━━━━━━━━━━━━━━━━━━━━━━━━━━

Бот готов к работе! /start
"""
        
        for admin_id in ADMIN_TG_ID:
            try:
                await bot.send_message(admin_id, message, parse_mode="HTML")
                logger.info(f"Отправлено уведомление о запуске админу {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    
    @staticmethod
    async def notify_user(bot: Bot, user_id: int, message: str, parse_mode: str = "HTML"):
        """Отправить уведомление пользователю"""
        try:
            await bot.send_message(user_id, message, parse_mode=parse_mode)
            logger.info(f"Отправлено уведомление пользователю {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
            return False
    
    @staticmethod
    async def notify_admins(bot: Bot, message: str, parse_mode: str = "HTML"):
        """Отправить уведомление всем админам"""
        success_count = 0
        for admin_id in ADMIN_TG_ID:
            if await NotificationService.notify_user(bot, admin_id, message, parse_mode):
                success_count += 1
        
        logger.info(f"Уведомление отправлено {success_count}/{len(ADMIN_TG_ID)} админам")
        return success_count
    
    @staticmethod
    async def notify_about_new_task(bot: Bot, task, creator, executor):
        """Уведомление о новой задаче"""
        priority_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
        priority_names = ["Низкий", "Средний", "Высокий", "Срочный"]
        
        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Не указан"
        
        message = f"""
🆕 <b>НОВАЯ ЗАДАЧА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Номер:</b> {task.task_number}
📌 <b>Название:</b> {task.title}
👤 <b>От:</b> {creator.first_name} {creator.last_name or ''}
⏱️ <b>Дедлайн:</b> {deadline_str}
📍 <b>Приоритет:</b> {priority_emoji[task.priority]} {priority_names[task.priority-1]}

━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Описание:</b>
{task.description[:200]}...

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        return await NotificationService.notify_user(bot, executor.telegram_id, message)
    
    @staticmethod
    async def notify_about_task_status_change(bot: Bot, task, old_status, new_status, user_id: int):
        """Уведомление об изменении статуса задачи"""
        status_names = {
            "pending": "⏳ Ожидает",
            "in_progress": "🟡 В работе",
            "completed": "✅ Завершена",
            "approved": "🎉 Одобрена",
            "rejected": "❌ Отклонена",
            "cancelled": "🚫 Отменена"
        }
        
        message = f"""
🔄 <b>ИЗМЕНЕНИЕ СТАТУСА ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
📌 <b>Название:</b> {task.title}

<b>Статус изменен:</b>
{status_names.get(old_status.value, old_status.value)} → {status_names.get(new_status.value, new_status.value)}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        return await NotificationService.notify_user(bot, user_id, message)
    
    @staticmethod
    async def notify_about_message(bot: Bot, task, sender, recipient_id: int, message_content: str):
        """Уведомление о новом сообщении"""
        message = f"""
💬 <b>НОВОЕ СООБЩЕНИЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
👤 <b>От:</b> {sender.first_name} {sender.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

{message_content}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Используйте /start для ответа
"""
        
        return await NotificationService.notify_user(bot, recipient_id, message)


# Для обратной совместимости
async def notify_admins_on_start(bot: Bot):
    """Уведомить админов о запуске бота"""
    await NotificationService.notify_admins_on_start(bot)

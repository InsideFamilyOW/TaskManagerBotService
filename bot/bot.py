"""Модуль для создания и настройки бота"""
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from Data.config import BOT_TOKEN


def create_bot() -> Bot:
    """Создает и возвращает экземпляр бота"""
    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


def create_dispatcher() -> Dispatcher:
    """Создает и возвращает экземпляр диспетчера"""
    return Dispatcher()


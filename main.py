"""Главный файл запуска бота"""
import asyncio
import os
from aiogram import Bot

from bot.bot import create_bot, create_dispatcher
from bot.handlers import register_handlers
from bot.utils.notifications import notify_admins_on_start
from bot.utils.log_channel import LogChannel
from db.engine import engine, AsyncSessionLocal
from db.init_db import create_tables
from db.queries.channel_queries import ChannelQueries
from log import logger


async def load_channels_from_db():
    """Загрузка каналов из БД при старте бота"""
    try:
        async with AsyncSessionLocal() as session:
            channels = await ChannelQueries.get_all_active_channels(session)
            channel_ids = [channel.channel_id for channel in channels]
            LogChannel.set_channels(channel_ids)
            logger.info(f"Загружено {len(channel_ids)} каналов: {channel_ids}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке каналов из БД: {e}")


async def main():
    """Основная функция запуска бота"""
    bot = None
    try:
        logger.info("=" * 50)
        logger.info("🚀 Запуск Task Manager Bot...")
        logger.info("=" * 50)
        print("🚀 Запуск Task Manager Bot...")
        
        os.makedirs("uploads", exist_ok=True)
        logger.info("📁 Директория для загрузок создана")
        
        bot = create_bot()
        dp = create_dispatcher()
        
        register_handlers(dp)
        logger.info("✅ Обработчики зарегистрированы")
        
        await create_tables()
        logger.info("✅ Таблицы базы данных проверены")
        
        await load_channels_from_db()
        logger.info("✅ Каналы загружены из базы данных")
        
        await notify_admins_on_start(bot)
        
        logger.info("✅ Бот успешно инициализирован и запущен")
        print("✅ Бот успешно инициализирован и запущен")
        print("📱 Бот работает...")
        print("")
        print("=" * 50)
        print("🎯 Task Manager Bot v2.0")
        print("=" * 50)
        print("📋 Функционал:")
        print("  • Управление задачами")
        print("  • Ролевая система (Админ, Байер, Исполнитель)")
        print("  • Коммуникация через бота")
        print("  • Каналы логов действий")
        print("  • Файловая система")
        print("=" * 50)
        print("")
        
        await dp.start_polling(bot, skip_updates=True)
        
    except KeyboardInterrupt:
        logger.info("⚠️ Получен сигнал остановки (Ctrl+C)")
        print("\n⚠️ Остановка бота...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {type(e).__name__}: {str(e)}")
        print(f"❌ Критическая ошибка: {type(e).__name__}: {str(e)}")
        raise
    finally:
        if bot:
            await bot.session.close()
            logger.info("🔌 Сессия бота закрыта")
        
        await engine.dispose()
        logger.info("🔌 Соединение с базой данных закрыто")
        print("🔌 Соединение с базой данных закрыто")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Программа остановлена пользователем")
        print("\n⚠️ Программа остановлена")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {type(e).__name__}: {str(e)}")
        print(f"❌ Фатальная ошибка: {type(e).__name__}: {str(e)}")

